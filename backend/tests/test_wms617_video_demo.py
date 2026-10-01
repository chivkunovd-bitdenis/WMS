from __future__ import annotations

import argparse
import uuid

import pytest
from sqlalchemy import event, func, select

from app.cli import wms617_video_demo as demo
from app.core.settings import settings
from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder
from app.models.inventory_count import InventoryCountLine
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse


async def prepare(session, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "staging")
    monkeypatch.setattr(settings, "wildberries_marketplace_api_base", demo.EMULATOR_BASE)
    session.add(Tenant(id=demo.TENANT_ID, name="WMS Staging", slug="wms-staging"))
    await session.flush()
    warehouse = Warehouse(tenant_id=demo.TENANT_ID, name="Existing", code="11")
    actor = User(tenant_id=demo.TENANT_ID, full_name="Existing author", role="fulfillment_admin",
                 password_hash="unused-test-placeholder")
    session.add_all([warehouse, actor])
    await session.commit()
    return argparse.Namespace(tenant_id=demo.TENANT_ID, warehouse_id=warehouse.id,
                              actor_id=actor.id, apply=True)


@pytest.mark.asyncio
async def test_seed_repeat_audit_preserves_operator_and_unrelated_rows(db_session, monkeypatch):
    args = await prepare(db_session, monkeypatch)
    foreign = Tenant(name="Other tenant", slug="other")
    db_session.add(foreign)
    await db_session.flush()
    unrelated = Product(tenant_id=demo.TENANT_ID, sku_code="KURTKA-VIDEO-01", name="Existing")
    foreign_product = Product(tenant_id=foreign.id, sku_code="WMS617-01", name="Foreign")
    db_session.add_all([unrelated, foreign_product])
    await db_session.commit()
    result = await demo.run(args)
    assert result["created"] is True
    assert result["decision"] == "additive_scope"
    legacy = result["before"]["legacy_audit"]
    assert legacy["counts"]["products"] == 1
    assert "six_skus_two_barcodes_primary_stock" in legacy["gaps"]
    assert legacy["products"][0]["id"] == str(unrelated.id)
    assert legacy["products"][0]["barcodes"] == []
    assert legacy["products"][0]["stock"] == legacy["products"][0]["reserved"] == 0
    assert result["after"]["legacy_audit"] == legacy
    after = result["after"]
    assert len(after["products"]) == 6
    assert len(after["orders"]) == 12
    assert len(after["supplies"]) == 4
    assert len(after["inventory_counts"]) == 2
    assert all(len(p["barcodes"]) == 2 and p["stock"] == 30 for p in after["products"])
    assert all(p["primary_print_barcode"] in p["barcodes"] for p in after["products"])
    assert {o["marketplace"] for o in after["orders"]} == {"wb", "ozon"}
    assert all(p["id"] != str(foreign_product.id) for p in after["products"])
    async with SessionLocal() as session:
        line = await session.get(InventoryCountLine, demo.demo_id("count-line/partial/1/WMS617-01"))
        line.actual_quantity = 7
        order = await session.get(FbsOrder, demo.demo_id("order/3"))
        order.status = "packed"
        product = await session.get(Product, demo.demo_id("product/1"))
        product.primary_print_barcode = demo.barcode(1)
        await session.commit()
    statements = []

    def capture(_conn, _cursor, sql, _params, _ctx, _many):
        statements.append(sql.strip().split()[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        repeated = await demo.run(args)
        args.apply = False
        audit = await demo.run(args)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert not repeated["created"]
    assert audit["before"] == repeated["after"]
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}
    async with SessionLocal() as session:
        line = await session.get(InventoryCountLine, demo.demo_id("count-line/partial/1/WMS617-01"))
        assert line.actual_quantity == 7
        assert (await session.get(FbsOrder, demo.demo_id("order/3"))).status == "packed"
        assert (await session.get(Product, unrelated.id)).primary_print_barcode is None
        movements = list((await session.scalars(select(InventoryMovement).where(
            InventoryMovement.tenant_id == demo.TENANT_ID,
        ))).all())
        assert len(movements) == 7
        assert sum(row.quantity_delta for row in movements) == 180
        assert all(row.inbound_intake_line_id and row.actor_user_id == args.actor_id
                   for row in movements)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["env", "tenant", "name", "warehouse", "actor", "provider"])
async def test_guards_reject_wrong_destination_without_seed(db_session, monkeypatch, invalid):
    args = await prepare(db_session, monkeypatch)
    if invalid == "env":
        monkeypatch.setattr(settings, "app_env", "production")
    elif invalid == "tenant":
        args.tenant_id = uuid.uuid4()
    elif invalid == "name":
        (await db_session.get(Tenant, demo.TENANT_ID)).name = "Production copy"
        await db_session.commit()
    elif invalid == "warehouse":
        args.warehouse_id = uuid.uuid4()
    elif invalid == "actor":
        args.actor_id = uuid.uuid4()
    else:
        monkeypatch.setattr(settings, "wildberries_marketplace_api_base",
                            "https://marketplace-api.wildberries.ru")
    with pytest.raises(ValueError):
        await demo.run(args)
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 0


@pytest.mark.asyncio
async def test_seed_failure_rolls_back_everything(db_session, monkeypatch):
    args = await prepare(db_session, monkeypatch)

    async def fail(*_args, **_kwargs):
        raise ValueError("injected late failure")

    monkeypatch.setattr(demo, "_invoice", fail)
    with pytest.raises(ValueError, match="injected late failure"):
        await demo.run(args)
    for model in (Seller, Product, FbsOrder, InventoryMovement):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_identity_collision_does_not_overwrite(db_session, monkeypatch):
    args = await prepare(db_session, monkeypatch)
    db_session.add(Product(id=demo.demo_id("product/1"), tenant_id=demo.TENANT_ID,
                           sku_code="UNRELATED", name="Do not replace"))
    await db_session.commit()
    with pytest.raises(ValueError, match="identity collision"):
        await demo.run(args)
    assert await db_session.scalar(select(func.count()).select_from(Seller)) == 0
    assert (await db_session.get(Product, demo.demo_id("product/1"))).name == "Do not replace"


@pytest.mark.asyncio
async def test_seed_is_readable_by_existing_workspace_catalog_and_invoice(db_session, monkeypatch):
    from app.api.fbs_supplies import FbsWorkspaceOut
    from app.services.billing_invoice_v2_service import get_invoice_v2
    from app.services.billing_seller_rates_service import list_seller_billing_rates
    from app.services.fbs_workspace_service import get_supply_workspace
    from app.services.inbound_intake_service import get_request, resolve_scanned_product_id
    from app.services.inventory_count_service import get_count, print_sheet_data
    from app.services.seller_fulfillment_catalog_service import list_seller_catalog_page

    args = await prepare(db_session, monkeypatch)
    await demo.run(args)
    async with SessionLocal() as session:
        for key in ("normal", "assembly-a", "assembly-b", "ozon"):
            workspace = await get_supply_workspace(session, demo.TENANT_ID,
                                                   demo.demo_id(f"supply/{key}"))
            parsed = FbsWorkspaceOut.model_validate(workspace)
            assert parsed.orders
        for n in range(1, 7):
            part = 1 if n < 3 else 3 if n == 3 else 2
            req = await get_request(session, demo.TENANT_ID, demo.demo_id(f"intake/{part}"))
            for alias in (0, 1):
                resolved = await resolve_scanned_product_id(
                    session, demo.TENANT_ID, req, demo.barcode(n, alias),
                )
                assert resolved == demo.demo_id(f"product/{n}")
        for mp in ("wildberries", "ozon"):
            items, total, _, _ = await list_seller_catalog_page(
                session, demo.TENANT_ID, demo.demo_id("seller/1"), marketplace=mp,
            )
            assert total >= 3
            assert items
        count = await get_count(session, demo.TENANT_ID, demo.demo_id("count/draft"))
        sheet = await print_sheet_data(session, demo.TENANT_ID, count)
        assert len(sheet.rows) == 6
        assert all(row.barcode and row.total == 30 for row in sheet.rows)
        assert sum(row.reserved for row in sheet.rows) == 14
        invoice = await get_invoice_v2(session, tenant_id=demo.TENANT_ID,
                                       invoice_id=demo.demo_id("invoice"))
        assert invoice.total_amount_kopecks == 75000
        assert len(invoice.lines_v2) == 2
        rates = await list_seller_billing_rates(
            session, tenant_id=demo.TENANT_ID, seller_id=demo.demo_id("seller/1"),
        )
        assert any(row.rate_kopecks == 500 for row in rates)


@pytest.mark.asyncio
async def test_seed_supports_cell_box_product_pick_and_inventory_source(db_session, monkeypatch):
    from app.services.fbs_picking_service import pick_scan
    from app.services.inventory_service import physical_on_hand_in_container

    args = await prepare(db_session, monkeypatch)
    (await db_session.get(Tenant, demo.TENANT_ID)).address_storage_enabled = True
    await db_session.commit()
    await demo.run(args)
    async with SessionLocal() as session:
        actor = await session.get(User, args.actor_id)
        product_id = demo.demo_id("product/1")
        supply_id = demo.demo_id("supply/normal")
        location_id = demo.demo_id("location/1")
        box_id = demo.demo_id("box")
        assert await physical_on_hand_in_container(
            session, demo.TENANT_ID, product_id, location_id, "box", box_id,
        ) == 20
        count_line = await session.get(
            InventoryCountLine, demo.demo_id("count-line/draft/1/WMS617-01"),
        )
        assert (count_line.container_kind, count_line.container_id) == ("box", box_id)
        location = await pick_scan(
            session, demo.TENANT_ID, supply_id, barcode="WMS617-CELL-1",
            product_id_hint=None, storage_location_id=None, idempotency_key="demo-cell",
            actor=actor,
        )
        assert location.kind == "location" and location.storage_location_id == location_id
        container = await pick_scan(
            session, demo.TENANT_ID, supply_id, barcode="WMS617-BOX-01",
            product_id_hint=None, storage_location_id=location_id,
            idempotency_key="demo-box", actor=actor,
        )
        assert container.kind == "container" and container.container_id == box_id
        result = await pick_scan(
            session, demo.TENANT_ID, supply_id, barcode=demo.barcode(1, 1),
            product_id_hint=None, storage_location_id=location_id,
            container_kind="box", container_id=box_id,
            idempotency_key="demo-product", actor=actor,
        )
        assert result.kind == "product"
        assert await physical_on_hand_in_container(
            session, demo.TENANT_ID, product_id, location_id, "box", box_id,
        ) == 19
        assert (await session.get(FbsOrder, demo.demo_id("order/3"))).pick_status == "picked"


@pytest.mark.asyncio
@pytest.mark.parametrize("extraneous", [False, True])
async def test_complete_legacy_dataset_is_reused_without_mutations(
    db_session, monkeypatch, extraneous,
):
    args = await prepare(db_session, monkeypatch)
    await demo.run(args)
    async with SessionLocal() as session:
        for n in range(1, 7):
            product = await session.get(Product, demo.demo_id(f"product/{n}"))
            product.sku_code = f"FBS-VIDEO-EXISTING-{n}"
        if extraneous:
            session.add(Product(tenant_id=demo.TENANT_ID, sku_code="EMU-INCOMPLETE-OTHER",
                                name="Unrelated old fixture"))
        await session.commit()
    statements = []

    def capture(_conn, _cursor, sql, _params, _ctx, _many):
        statements.append(sql.strip().split()[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        result = await demo.run(args)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    legacy = result["before"]["legacy_audit"]
    assert result["decision"] == "reuse_local_scope", legacy["gaps"]
    assert result["created"] is False
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}
    assert all(legacy["local_readiness_checks"].values())
    assert legacy["counts"]["products"] == (7 if extraneous else 6)
    assert len(legacy["candidate"]["product_ids"]) == 6
    assert len(legacy["excluded_product_ids"]) == (1 if extraneous else 0)
    assert len(legacy["candidate"]["seller_ids"]) == 2
    assert legacy["counts"]["orders"] == 12
    assert sum(p["reserved"] for p in legacy["products"]) == 14
    assert len(legacy["intake_ids"]) == 3
    assert len(legacy["inventory_documents"]) == 2
    assert len(legacy["supplies"]) == 4
    assert all(p["document_movements"] for p in legacy["products"]
               if p["id"] in legacy["candidate"]["product_ids"])
    assert all(o["wb_order_id"] for o in legacy["orders"] if o["marketplace"] == "wb")
    assert legacy["provider_verification"].startswith("unverified")
    assert result["after"]["legacy_audit"] == legacy


@pytest.mark.asyncio
@pytest.mark.parametrize("defect,expected_gap", [
    ("wrong_marking_sku", "marking_pool"),
    ("one_seller_billing", "billing_each_seller"),
    ("invoice_cross_seller", "billing_each_seller"),
    ("rate_cross_seller", "billing_each_seller"),
    ("rate_snapshot", "billing_each_seller"),
])
async def test_legacy_relationship_gaps_prevent_reuse(
    db_session, monkeypatch, defect, expected_gap,
):
    from app.models.billing import BillingInvoiceV2, BillingLedgerEntry
    from app.models.marking_code import MarkingCode

    args = await prepare(db_session, monkeypatch)
    await demo.run(args)
    async with SessionLocal() as session:
        for n in range(1, 7):
            product = await session.get(Product, demo.demo_id(f"product/{n}"))
            product.sku_code = f"FBS-VIDEO-EXISTING-{n}"
        if defect == "wrong_marking_sku":
            for code in (await session.scalars(select(MarkingCode))).all():
                code.product_id = demo.demo_id("product/1")
        elif defect == "one_seller_billing":
            charge = await session.get(BillingLedgerEntry, demo.demo_id("charge/3"))
            charge.seller_id = demo.demo_id("seller/1")
        elif defect == "invoice_cross_seller":
            invoice = await session.get(BillingInvoiceV2, demo.demo_id("invoice"))
            invoice.seller_id = demo.demo_id("seller/2")
        elif defect == "rate_snapshot":
            charge = await session.get(BillingLedgerEntry, demo.demo_id("charge/3"))
            charge.rate = 1
        else:
            charge = await session.get(BillingLedgerEntry, demo.demo_id("charge/3"))
            charge.tariff_version_v2_id = demo.demo_id("rate/1")
        await session.commit()
    args.apply = False
    result = await demo.run(args)
    legacy = result["before"]["legacy_audit"]
    assert result["decision"] == "additive_scope"
    assert legacy["gaps"] == [expected_gap]
    assert len(legacy["candidate"]["product_ids"]) == 6
    if defect == "wrong_marking_sku":
        assert legacy["counts"]["available_marking"] == 20
        assert legacy["candidate"]["marking_by_product"] == {str(demo.demo_id("product/2")): 0}
    elif defect in {"one_seller_billing", "rate_cross_seller", "rate_snapshot"}:
        second = legacy["candidate"]["billing_by_seller"][str(demo.demo_id("seller/2"))]
        assert second["profile"] and second["rate_ids"] and not second["charge_ids"]
    else:
        assert legacy["candidate"]["invoice_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", [
    "invoice_total", "line_total", "source_snapshot", "source_sign", "unit_price",
    "duplicate_source", "missing_source",
])
async def test_legacy_invoice_arithmetic_must_reconcile(db_session, monkeypatch, defect):
    from app.models.billing import BillingInvoiceV2, BillingInvoiceV2Line, BillingInvoiceV2Source

    args = await prepare(db_session, monkeypatch)
    await demo.run(args)
    async with SessionLocal() as session:
        for n in range(1, 7):
            product = await session.get(Product, demo.demo_id(f"product/{n}"))
            product.sku_code = f"FBS-VIDEO-EXISTING-{n}"
        invoice = await session.get(BillingInvoiceV2, demo.demo_id("invoice"))
        line = await session.get(BillingInvoiceV2Line, demo.demo_id("invoice-line/1"))
        source = await session.get(BillingInvoiceV2Source, demo.demo_id("invoice-source/1"))
        if defect == "invoice_total":
            invoice.total_amount_kopecks = 1
        elif defect == "line_total":
            line.total_amount_kopecks = 1
            invoice.total_amount_kopecks = 45001
        elif defect in {"source_snapshot", "source_sign"}:
            # Preserve upper-level sums: only the comparison with the charge catches this.
            source.signed_amount_kopecks_snapshot = 1 if defect == "source_snapshot" else -30000
            line.total_amount_kopecks = source.signed_amount_kopecks_snapshot
            invoice.total_amount_kopecks = 45000 + line.total_amount_kopecks
        elif defect == "unit_price":
            line.unit_price_kopecks = 1
        elif defect == "duplicate_source":
            session.add(BillingInvoiceV2Source(
                tenant_id=demo.TENANT_ID, invoice_line_id=line.id,
                billing_ledger_entry_id=demo.demo_id("charge/1"),
                signed_amount_kopecks_snapshot=30000,
            ))
            line.total_amount_kopecks = 60000
            invoice.total_amount_kopecks = 105000
        else:
            await session.delete(source)
            line.total_amount_kopecks = 0
            invoice.total_amount_kopecks = 45000
        await session.commit()
    args.apply = False
    result = await demo.run(args)
    legacy = result["before"]["legacy_audit"]
    assert result["decision"] == "additive_scope"
    assert legacy["gaps"] == ["billing_each_seller"]
    assert legacy["candidate"]["invoice_ids"] == []
