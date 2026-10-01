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
