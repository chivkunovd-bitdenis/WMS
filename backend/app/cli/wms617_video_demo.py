"""Explicit, additive WMS Staging video fixture. No credentials or provider calls."""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.wms617_legacy_audit import legacy_audit
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.billing import (
    BillingInvoiceV2,
    BillingInvoiceV2Line,
    BillingInvoiceV2Source,
    BillingLedgerEntry,
    BillingProfile,
    BillingTariffVersionV2,
)
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_count import InventoryCount, InventoryCountLine
from app.models.marking_code import MarkingCode, MarkingPool
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service
from app.services.fbs_stock_publish_service import _PENDING_KEY

TENANT_ID = uuid.UUID("9c31f3f4-ce62-4c1f-891a-295b278f1e69")
NAMESPACE = uuid.UUID("61700000-0000-4000-8000-000000000001")
MARKER = "WMS617:v1 video fixture"
EMULATOR_BASE = "http://wb-emulator.railway.internal:8000"
WB_WAREHOUSE = 617001
PRODUCT_NAMES = (
    "Футболка без ЧЗ", "Куртка с ЧЗ", "Пиджак второго селлера",
    "Ozon кружка", "Ozon плед с двумя ШК", "WB/Ozon сумка",
)


def demo_id(key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, key)


def barcode(index: int, alias: int = 0) -> str:
    base = f"206170{index:04d}{alias:02d}"
    check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3)
                      for i, c in enumerate(base)) % 10) % 10
    return base + str(check)


def seller_index(index: int) -> int:
    return 2 if index == 3 else 1


async def guard(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID,
    actor_id: uuid.UUID, *, lock: bool = False,
) -> None:
    if settings.app_env != "staging" or tenant_id != TENANT_ID:
        raise ValueError("requires exact WMS Staging tenant and APP_ENV=staging")
    if settings.wildberries_marketplace_api_base.rstrip("/") != EMULATOR_BASE:
        raise ValueError("requires exact staging WB emulator endpoint")
    tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
    tenant = await session.scalar(tenant_stmt.with_for_update() if lock else tenant_stmt)
    if tenant is None or tenant.name != "WMS Staging":
        raise ValueError("WMS Staging identity mismatch")
    warehouse = await session.get(Warehouse, warehouse_id)
    actor = (await session.execute(select(User.tenant_id, User.role).where(
        User.id == actor_id,
    ))).one_or_none()
    if warehouse is None or warehouse.tenant_id != tenant_id or not warehouse.is_operational:
        raise ValueError("warehouse must be operational and belong to WMS Staging")
    if actor is None or actor.tenant_id != tenant_id or actor.role != "fulfillment_admin":
        raise ValueError("actor must be an existing WMS Staging administrator")


async def audit(session: AsyncSession) -> dict[str, Any]:
    """Allowlisted fields only: never serialize ORM objects/settings/credentials."""
    products = list((await session.scalars(select(Product).where(
        Product.tenant_id == TENANT_ID,
        Product.id.in_([demo_id(f"product/{i}") for i in range(1, 7)]),
    ).order_by(Product.sku_code))).all())
    product_ids = [p.id for p in products]
    aliases = list((await session.scalars(select(ProductBarcode).where(
        ProductBarcode.tenant_id == TENANT_ID, ProductBarcode.product_id.in_(product_ids),
    ))).all())
    balances = list((await session.scalars(select(InventoryBalance).where(
        InventoryBalance.tenant_id == TENANT_ID, InventoryBalance.product_id.in_(product_ids),
    ))).all())
    sellers = [demo_id(f"seller/{i}") for i in (1, 2)]
    orders = list((await session.scalars(select(FbsOrder).where(
        FbsOrder.tenant_id == TENANT_ID, FbsOrder.seller_id.in_(sellers),
    ).order_by(FbsOrder.wb_order_id))).all())
    supplies = list((await session.scalars(select(FbsSupply).where(
        FbsSupply.tenant_id == TENANT_ID, FbsSupply.seller_id.in_(sellers),
    ))).all())
    counts = list((await session.scalars(select(InventoryCount).where(
        InventoryCount.tenant_id == TENANT_ID,
        InventoryCount.id.in_([demo_id("count/draft"), demo_id("count/partial")]),
    ))).all())
    count_lines = list((await session.scalars(select(InventoryCountLine).where(
        InventoryCountLine.count_id.in_([c.id for c in counts]),
    ))).all())
    marking = list((await session.scalars(select(MarkingCode).where(
        MarkingCode.tenant_id == TENANT_ID, MarkingCode.pool_id == demo_id("marking-pool"),
    ).order_by(MarkingCode.cis_code))).all())
    legacy_supplies = (await session.execute(select(
        FbsSupply.id, FbsSupply.name, FbsSupply.wb_supply_id, FbsSupply.status,
    ).where(FbsSupply.tenant_id == TENANT_ID, FbsSupply.seller_id.not_in(sellers),
            FbsSupply.status == "in_delivery"))).all()
    legacy = (await session.execute(select(Product.id, Product.sku_code).where(
        Product.tenant_id == TENANT_ID,
        (Product.sku_code.like("%VIDEO%") | Product.sku_code.like("FBS-TEST-%")
         | Product.sku_code.like("EMU-%")),
    ).order_by(Product.sku_code))).all()
    return {
        "schema": MARKER, "tenant_id": str(TENANT_ID),
        "totals": {model.__tablename__: await session.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == TENANT_ID),
        ) for model in (Product, Seller, Warehouse)},
        "legacy_not_modified": [{"id": str(row.id), "sku": row.sku_code} for row in legacy],
        "sellers": [{"id": str(sid), "present": await session.get(Seller, sid) is not None}
                    for sid in sellers],
        "products": [{"id": str(p.id), "seller_id": str(p.seller_id), "sku": p.sku_code,
                      "name": p.name, "primary_print_barcode": p.primary_print_barcode,
                      "barcodes": sorted(a.barcode for a in aliases if a.product_id == p.id),
                      "stock": sum(b.quantity for b in balances if b.product_id == p.id),
                      "locations": [{"id": str(b.storage_location_id), "quantity": b.quantity,
                                     "container_kind": b.container_kind,
                                     "container_id": (
                                         str(b.container_id) if b.container_id else None)}
                                    for b in balances if b.product_id == p.id]}
                     for p in products],
        "orders": [{"id": str(o.id), "marketplace": o.marketplace,
                    "external_order_id": o.external_order_id, "wb_order_id": o.wb_order_id,
                    "seller_id": str(o.seller_id), "product_id": str(o.product_id),
                    "supply_id": str(o.supply_id) if o.supply_id else None,
                    "status": o.status, "deadline_at": o.deadline_at.isoformat(),
                    "deadline_expired": o.deadline_at.replace(tzinfo=UTC) < datetime.now(UTC),
                    "sticker": o.sticker_barcode} for o in orders],
        "supplies": [{"id": str(s.id), "marketplace": s.marketplace,
                      "wb_supply_id": s.wb_supply_id, "status": s.status} for s in supplies],
        "inventory_counts": [{"id": str(c.id), "status": c.status,
                              "lines": [{"id": str(line.id), "product_id": str(line.product_id),
                                         "expected": line.expected_quantity,
                                         "actual": line.actual_quantity}
                                        for line in count_lines if line.count_id == c.id]}
                             for c in counts],
        "marking_codes": [{"id": str(code.id), "cis": code.cis_code, "status": code.status}
                          for code in marking],
        "legacy_delivery_unverified": [{"id": str(s.id), "name": s.name,
                                         "wb_supply_id": s.wb_supply_id, "status": s.status}
                                        for s in legacy_supplies],
        "intake_ids": [str(demo_id(f"intake/{i}")) for i in (1, 2, 3)],
        "cell_barcodes": ["WMS617-CELL-1", "WMS617-CELL-2"],
        "box_barcode": "WMS617-BOX-01",
        "structural_complete": len(products) == 6 and len(orders) == 12
                               and len(supplies) == 4 and len(counts) == 2,

        "assembly_id": str(demo_id("assembly")), "invoice_id": str(demo_id("invoice")),
        "provider_verification": "not verified: no provider calls or credentials in this seed",
        "wb_emulator_manifest": {
            "note": "IDs for separate emulator preparation; no emulator writes performed",
            "orders": [{"wb_order_id": o.wb_order_id, "seller_id": str(o.seller_id),
                        "nm_id": o.wb_nm_id, "chrt_id": o.wb_chrt_id,
                        "barcode": o.wb_barcode, "supply_id": o.wb_supply_id}
                       for o in orders if o.marketplace == "wb"],
        },
        "limitations": ["No new users or permissions", "No physical print or mobile proof",
                        "No implementation of WMS-494/498/499", "Deadlines frozen at first apply"],
    }


async def _add(session: AsyncSession, model: Any, key: str, **values: Any) -> Any:
    identity = demo_id(key)
    if await session.get(model, identity) is not None:
        raise ValueError(f"fixture identity collision: {key}")
    row = model(id=identity, **values)
    session.add(row)
    await session.flush()
    return row


async def seed(
    session: AsyncSession, *, warehouse_id: uuid.UUID, actor_id: uuid.UUID, now: datetime,
) -> bool:
    """Caller owns one transaction; never reset a fixture already used by an operator."""
    anchor = await session.get(InboundIntakeRequest, demo_id("intake/1"))
    if anchor is not None:
        if anchor.tenant_id != TENANT_ID or anchor.comment != MARKER:
            raise ValueError("fixture anchor identity mismatch")
        if anchor.warehouse_id != warehouse_id:
            raise ValueError("fixture already belongs to a different warehouse")
        return False
    scope = {"tenant_id": TENANT_ID}
    sellers = {}
    for n in (1, 2):
        sellers[n] = await _add(session, Seller, f"seller/{n}", **scope,
                                name=f"WMS617 · Видео селлер {n}")
        await _add(session, BillingProfile, f"profile/{n}", **scope,
                   seller_id=sellers[n].id, legal_name=f"СИНТЕТИЧЕСКИЙ WMS617 селлер {n}",
                   inn=f"000000061{n}", bank_name="ДЕМО — НЕ ДЛЯ ОПЛАТЫ")
        await _add(session, BillingTariffVersionV2, f"rate/{n}", **scope,
                   seller_id=sellers[n].id, service_code="inbound", unit="item", rate=500,
                   enabled=True, valid_from_at=now - timedelta(days=1))
    locations = [await _add(session, StorageLocation, f"location/{n}", **scope,
                           warehouse_id=warehouse_id, code=f"WMS617-{n:02d}",
                           barcode=f"WMS617-CELL-{n}") for n in (1, 2)]
    await _add(session, WarehouseBox, "box", **scope, warehouse_id=warehouse_id,
               storage_location_id=locations[0].id, internal_barcode="WMS617-BOX-01")
    bindings = {}
    for n, mp in ((1, "wb"), (2, "wb"), (1, "ozon")):
        bindings[n, mp] = await _add(
            session, FbsWarehouseBinding, f"binding/{n}/{mp}", **scope,
            seller_id=sellers[n].id, marketplace=mp, wb_warehouse_id=WB_WAREHOUSE,
            external_warehouse_id=str(WB_WAREHOUSE), wms_warehouse_id=warehouse_id,
            is_active=True, served=True, stock_sync_enabled=False,
        )
    if await session.scalar(select(TenantWbMpWarehouse.id).where(
        TenantWbMpWarehouse.tenant_id == TENANT_ID,
        TenantWbMpWarehouse.wb_warehouse_id == WB_WAREHOUSE,
    )) is None:
        await _add(session, TenantWbMpWarehouse, "wb-warehouse", **scope,
                   wb_warehouse_id=WB_WAREHOUSE, name="WMS617 тестовый маршрут", is_active=True)
    products = {}
    for n, name in enumerate(PRODUCT_NAMES, 1):
        sid = sellers[seller_index(n)].id
        mp = "ozon" if n in (4, 5) else "wb"
        codes = [barcode(n, alias) for alias in (0, 1)]
        products[n] = await _add(
            session, Product, f"product/{n}", **scope, seller_id=sid,
            name=f"WMS617 · {name}", sku_code=f"WMS617-{n:02d}", category="Видео WMS617",
            wb_nm_id=617000 + n if mp == "wb" else None,
            wb_chrt_id=617100 + n if mp == "wb" else None,
            wb_vendor_code=f"WMS617-{n:02d}", wb_barcode=codes[0],
            primary_print_barcode=codes[1], wb_size="M", weight_g=300,
            length_mm=200, width_mm=150, height_mm=30, volume_liters=0.9,
            requires_honest_sign=n == 2, fbs_stock_limit=20,
            fbs_stock_sync_enabled=False, fbs_ozon_stock_sync_enabled=False,
        )
        for alias, code in enumerate(codes):
            await _add(session, ProductBarcode, f"barcode/{n}/{alias}", **scope,
                       seller_id=sid, product_id=products[n].id, barcode=code, source=mp)
        for provider in (["wb", "ozon"] if n == 6 else [mp]):
            await _catalog(session, n, sid, provider, products[n].id)
            await _add(session, FbsBindingStockPool, f"stock-pool/{n}/{provider}", **scope,
                       binding_id=bindings[seller_index(n), provider].id,
                       product_id=products[n].id, quantity=20, units_configured=True,
                       publish_enabled=False)
    # Full seller catalog includes unselected cards on both providers.
    await _catalog(session, 7, sellers[1].id, "wb", None)
    await _catalog(session, 8, sellers[1].id, "ozon", None)
    for part, indices in enumerate(((1, 2), (4, 5, 6), (3,)), 1):
        sid = sellers[2 if part == 3 else 1].id
        intake = await _add(session, InboundIntakeRequest, f"intake/{part}", **scope,
                            seller_id=sid, warehouse_id=warehouse_id, status="done",
                            operation_type="inbound", comment=MARKER,
                            document_number=f"WMS617-IN-{part}", posted_at=now,
                            completed_by_user_id=actor_id, distribution_completed_at=now)
        for n in indices:
            line = await _add(session, InboundIntakeLine, f"intake-line/{n}",
                              request_id=intake.id, product_id=products[n].id,
                              expected_qty=30, actual_qty=30, posted_qty=30,
                              storage_location_id=locations[0].id)
            for loc, qty in ([(locations[0], 20), (locations[1], 10)] if n == 1
                             else [(locations[0], 30)]):
                await inventory_service.record_movement_and_adjust_balance(
                    session, tenant_id=TENANT_ID, product_id=products[n].id,
                    storage_location_id=loc.id, quantity_delta=qty,
                    movement_type="inbound_intake", inbound_intake_line_id=line.id,
                    actor_user_id=actor_id,
                    container_kind="box" if n == 1 and loc.id == locations[0].id else None,
                    container_id=demo_id("box") if n == 1 and loc.id == locations[0].id else None,
                )
        await _add(session, BillingLedgerEntry, f"charge/{part}", **scope,
                   seller_id=sid, warehouse_id=warehouse_id, performer_id=actor_id,
                   source="wms617_demo", source_type="inbound_intake", source_id=intake.id,
                   service_code="inbound", unit="item", quantity=Decimal(30 * len(indices)),
                   rate=500, amount=500 * 30 * len(indices), occurred_at=now,
                   tariff_version_v2_id=demo_id(f"rate/{2 if part == 3 else 1}"))
    await _orders(session, sellers, products, warehouse_id, now, actor_id)
    for kind in ("draft", "partial"):
        count = await _add(session, InventoryCount, f"count/{kind}", **scope,
                           warehouse_id=warehouse_id, status="draft", source="planned",
                           created_by_user_id=actor_id, comment=f"{MARKER} {kind}",
                           selected_product_ids=[str(p.id) for p in products.values()])
        for n, product in products.items():
            for loc, qty in ([(locations[0], 20), (locations[1], 10)] if n == 1
                             else [(locations[0], 30)]):
                await _add(session, InventoryCountLine, f"count-line/{kind}/{n}/{loc.code}",
                           count_id=count.id, product_id=product.id, storage_location_id=loc.id,
                           expected_quantity=qty,
                           container_kind="box" if n == 1 and loc.id == locations[0].id else None,
                           container_id=(demo_id("box")
                                         if n == 1 and loc.id == locations[0].id else None),
                           actual_quantity=qty - 1 if kind == "partial" and n == 1 else None)
    pool = await _add(session, MarkingPool, "marking-pool", **scope,
                      seller_id=sellers[1].id, gtin="0" + barcode(2), title=MARKER)
    for n in range(20):
        await _add(session, MarkingCode, f"marking/{n}", **scope, seller_id=sellers[1].id,
                   pool_id=pool.id, product_id=products[2].id, gtin=pool.gtin,
                   cis_code=f"01{pool.gtin}21WMS617{n:07d}", source="pool", status="available")
    await _invoice(session, sellers[1].id, actor_id, now)
    # This maintenance session is exclusively the synthetic fixture: do not enqueue
    # stock publication from its document-backed balance writes, even to an emulator.
    session.info[_PENDING_KEY] = set()
    return True


async def _catalog(
    session: AsyncSession, n: int, sid: uuid.UUID, mp: str, product_id: uuid.UUID | None,
) -> None:
    scope = {"tenant_id": TENANT_ID, "seller_id": sid}
    name, offer = f"WMS617 demo catalog {n}", f"WMS617-{n:02d}"
    codes = [barcode(n, a) for a in (0, 1)]
    if mp == "wb":
        raw = {"nmID": 617000 + n, "vendorCode": offer, "title": name,
               "brand": "WMS617", "subjectName": "Демо",
               "sizes": [{"chrtID": 617100 + n, "techSize": "M", "skus": codes}]}
        await _add(session, SellerWildberriesImportedCard, f"card/{mp}/{n}", **scope,
                   nm_id=617000 + n, vendor_code=offer, title=name, raw_json=raw)
    else:
        raw = {"id": 617000 + n, "sku": 617100 + n, "offer_id": offer,
               "name": name, "barcodes": codes, "barcode": codes[0]}
        await _add(session, SellerOzonImportedCard, f"card/{mp}/{n}", **scope,
                   ozon_product_id=str(617000 + n), sku=str(617100 + n),
                   offer_id=offer, name=name, raw_json=raw)
    if product_id is not None:
        await _add(session, ProductMarketplaceLink, f"link/{mp}/{n}", **scope,
                   product_id=product_id, marketplace=mp, external_product_id=str(617000 + n),
                   external_sku=str(617100 + n), external_offer_id=offer,
                   external_barcodes=codes, provider_data=raw)


async def _orders(
    session: AsyncSession, sellers: dict[int, Any], products: dict[int, Any],
    warehouse_id: uuid.UUID, now: datetime, actor_id: uuid.UUID,
) -> None:
    scope = {"tenant_id": TENANT_ID, "warehouse_id": warehouse_id}
    specs = [("normal", 1, "wb", "warehouse_sc"), ("assembly-a", 1, "wb", "warehouse_sc"),
             ("assembly-b", 2, "wb", "pvz"), ("ozon", 1, "ozon", "warehouse_sc")]
    supplies = {}
    for key, sn, mp, route in specs:
        supplies[key] = await _add(
            session, FbsSupply, f"supply/{key}", **scope, seller_id=sellers[sn].id,
            marketplace=mp, name=f"WMS617 {key}", status="assembling", delivery_type=route,
            wb_supply_id=f"WB-GI-WMS617-{key.upper()}" if mp == "wb" else None,
            planned_shipment_date=now.date(),
        )
    # Two new WB orders remain available; six form normal/common assembly.
    for n, (pn, supply_key) in enumerate(
        [(1, None), (2, None), (1, "normal"), (2, "normal"),
         (2, "assembly-a"), (6, "assembly-a"), (3, "assembly-b"), (3, "assembly-b"),
         (4, None), (5, "ozon"), (6, "ozon"), (4, "ozon")], 1,
    ):
        product = products[pn]
        mp = "wb" if n <= 8 else "ozon"
        supply = supplies.get(supply_key) if supply_key else None
        order = await _add(
            session, FbsOrder, f"order/{n}", **scope, seller_id=product.seller_id,
            product_id=product.id, marketplace=mp, external_order_id=f"WMS617-{n:06d}",
            wb_order_id=617000000 + n, wb_nm_id=617000 + pn, wb_chrt_id=617100 + pn,
            wb_article=product.sku_code, wb_barcode=barcode(pn), wb_warehouse_id=WB_WAREHOUSE,
            cargo_type="mgt", can_pvz=n in (7, 8),
            supply_id=supply.id if supply else None,
            wb_supply_id=supply.wb_supply_id if supply else None,
            status="in_supply" if supply else "new", supplier_status="confirm" if supply else "new",
            wb_status="waiting", created_at_wb=now - timedelta(hours=1),
            deadline_at=now + timedelta(hours=-1 if n == 2 else n * 2),
            mapping_status="mapped", reserve_status="reserved",
            required_meta_json=["sgtin"] if pn == 2 else [],
            sticker_barcode=f"WMS617-QR-{n}", sticker_code=f"WMS617 {n:04d}",
            meta_details_json={"ozon_delivery_method_id": "617001"} if mp == "ozon" else None,
        )
        if mp == "wb":
            await _add(session, FbsOrderReservation, f"reservation/{n}", **scope,
                       fbs_order_id=order.id, product_id=product.id, quantity=1)
        else:
            position = await _add(session, FbsOrderProduct, f"position/{n}",
                                  order_id=order.id, product_id=product.id,
                                  ozon_sku=617100 + pn, offer_id=product.sku_code,
                                  name=product.name,
                                  quantity=3 if n == 10 else 1, position_index=0,
                                  reserved_quantity=3 if n == 10 else 1)
            await _add(session, FbsOrderProductReservation, f"reservation/{n}", **scope,
                       order_product_id=position.id, product_id=product.id,
                       quantity=position.quantity)
    task = await _add(session, FbsAssemblyTask, "assembly", tenant_id=TENANT_ID,
                      number="W61701", idempotency_key=MARKER, created_by_user_id=actor_id)
    for key in ("assembly-a", "assembly-b"):
        session.add(FbsAssemblyTaskSupply(task_id=task.id, supply_id=supplies[key].id))
    await session.flush()


async def _invoice(
    session: AsyncSession, sid: uuid.UUID, actor_id: uuid.UUID, now: datetime,
) -> None:
    await _add(session, BillingInvoiceV2, "invoice", tenant_id=TENANT_ID,
               seller_id=sid, number="WMS617-DEMO-001", creation_mode="selected_operations",
               status="issued", issued_at=now, issued_by_user_id=actor_id,
               ff_profile_snapshot={"legal_name": "WMS Staging — ДЕМО", "inn": "0000000000"},
               seller_profile_snapshot={"legal_name": "WMS617 Видео селлер 1", "inn": "0000000611"},
               total_amount_kopecks=75000)
    for n, qty in ((1, 60), (2, 90)):
        line = await _add(session, BillingInvoiceV2Line, f"invoice-line/{n}",
                          tenant_id=TENANT_ID, invoice_id=demo_id("invoice"),
                          description_snapshot=f"ДЕМО приёмка WMS617-IN-{n}: {qty} шт.",
                          unit_price_kopecks=500, total_amount_kopecks=qty * 500, sort_order=n)
        await _add(session, BillingInvoiceV2Source, f"invoice-source/{n}", tenant_id=TENANT_ID,
                   invoice_line_id=line.id, billing_ledger_entry_id=demo_id(f"charge/{n}"),
                   signed_amount_kopecks_snapshot=qty * 500)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    async with SessionLocal() as session, session.begin():
        await guard(session, args.tenant_id, args.warehouse_id, args.actor_id, lock=args.apply)
        before = await audit(session)
        existing = await legacy_audit(session, TENANT_ID, args.warehouse_id)
        before["legacy_audit"] = existing
        created = await seed(session, warehouse_id=args.warehouse_id, actor_id=args.actor_id,
                             now=datetime.now(UTC)) if (
                                 args.apply and existing["decision"] == "additive_scope"
                             ) else False
        after = await audit(session) if args.apply else before
        after["legacy_audit"] = existing
        result = {"decision": existing["decision"], "mode": "apply" if args.apply else "audit",
                  "created": created,
                  "before": before, "after": after}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--warehouse-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-id", type=uuid.UUID, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    # Reserve a new writable evidence file before touching the database.
    with args.manifest.open("x") as output:
        result = asyncio.run(run(args))
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"manifest": str(args.manifest), "created": result["created"]}))


if __name__ == "__main__":
    main()
