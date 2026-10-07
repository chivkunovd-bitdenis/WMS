"""Independent process fixtures, restricted to the disposable browser stack."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.db.session import SessionLocal
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.models.warehouse_box import WarehouseBox
from app.services.inventory_service import record_movement_and_adjust_balance
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.fbs_browser_e2e_seed import _main as base_seed
from tests.inventory_actor_helpers import resolve_test_actor_user_id

CASES = [
    "sources",
    "auto",
    "ambiguous",
    "wrong",
    "change",
    "burst",
    "number-scan",
    "layout",
    "manual",
    "early-exit",
    "replay",
    "lost",
    "get-failure",
    "network",
    "last-unit",
    "manual-conflict",
    "print",
    "tabs",
    "group",
    "ozon",
    "ozon-group",
    "empty",
    "no-stock",
    "partial",
    "suffix",
    "focus",
    "group-sellers",
    "ozon-null",
    "packing-flag",
]


def guard() -> None:
    db = make_url(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("FBS_PICK_DISPOSABLE") != "1" or db.host != "db" or db.database != "wms":
        raise RuntimeError("Only disposable compose db/wms is permitted")


async def main() -> None:
    guard()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        await base_seed()
    seed = json.loads(out.getvalue())
    tenant, warehouse, seller = [
        uuid.UUID(seed[k]) for k in ("tenant_id", "warehouse_id", "seller_id")
    ]
    manifest = {}
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        actor_id = await resolve_test_actor_user_id(session, tenant)
        sellers = (
            await session.scalars(
                select(Seller).where(Seller.tenant_id == tenant, Seller.id != seller)
            )
        ).all()
        seller2 = sellers[0].id
        warehouse2 = Warehouse(
            id=uuid.uuid4(), tenant_id=tenant, name="CI second warehouse", code="CI-SECOND"
        )
        session.add(warehouse2)
        await session.flush()
        await get_or_create_sorting_location(session, tenant, warehouse2.id)
        for index, name in enumerate(CASES):
            f = {
                "name": name,
                "products": [],
                "sources": [],
                "supplies": [],
                "orders": [],
                "positions": [],
            }
            product_count = (
                16
                if name == "burst"
                else 2
                if name in ("ozon", "ozon-group", "wrong", "group-sellers")
                else 1
            )
            for pi in range(product_count):
                barcode = str(2900000000000 + index * 100 + (0 if name == "group-sellers" else pi))
                product_seller = seller2 if name == "group-sellers" and pi == 1 else seller
                sku = f"PICK-{index:02d}-{pi:02d}"
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    seller_id=product_seller,
                    name=f"Browser picking {name} product {pi}",
                    sku_code=sku,
                    wb_barcode=barcode,
                    wb_vendor_code=f"ART-{index}-{pi}",
                )
                session.add(product)
                await session.flush()
                alt = str(3900000000000 + index * 100 + pi)
                session.add(
                    ProductBarcode(
                        tenant_id=tenant,
                        seller_id=product_seller,
                        product_id=product.id,
                        barcode=alt,
                        source="wb",
                    )
                )
                f["products"].append(
                    {
                        "id": str(product.id),
                        "sku": sku,
                        "barcode": barcode,
                        "alt": alt,
                        "name": product.name,
                        "offer": f"OZ-ART-{index}-{pi}",
                    }
                )
                if name in ("ozon", "ozon-group"):
                    product.wb_barcode = None
                    product.wb_vendor_code = None
                    session.add(
                        ProductMarketplaceLink(
                            tenant_id=tenant,
                            seller_id=seller,
                            product_id=product.id,
                            marketplace="ozon",
                            external_sku=str(770000 + index * 10 + pi),
                            external_offer_id=f"OZ-ART-{index}-{pi}",
                            external_barcodes=[barcode],
                            is_active=True,
                        )
                    )
            locs = []
            for li in range(
                2 if name in ("sources", "ambiguous", "wrong", "change", "group-sellers") else 1
            ):
                loc = StorageLocation(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    warehouse_id=warehouse2.id
                    if name == "group-sellers" and li == 1
                    else warehouse,
                    code=f"A-{index:02d}-{li + 1}",
                    barcode=f"LOC-{index:02d}-{li + 1}",
                )
                session.add(loc)
                locs.append(loc)
            await session.flush()
            # Two boxes on one cell are separate sources; loose goods in both cells.
            sources = [(locs[0], None, None)]
            if len(locs) > 1:
                sources.append((locs[1], None, None))
            if name == "sources":
                for bi in range(2):
                    box = WarehouseBox(
                        id=uuid.uuid4(),
                        tenant_id=tenant,
                        warehouse_id=warehouse,
                        storage_location_id=locs[0].id,
                        internal_barcode=f"BOX-{index}-{bi}",
                    )
                    session.add(box)
                    sources.append((locs[0], "box", box))
                await session.flush()
            for loc, kind, box in sources:
                sf = {
                    "location_id": str(loc.id),
                    "code": loc.code,
                    "barcode": loc.barcode,
                    "container_kind": kind,
                    "container_id": str(box.id) if box else None,
                    "scan": box.internal_barcode if box else loc.barcode,
                    "initial": {},
                }
                for pi, p in enumerate(f["products"]):
                    qty = 0 if name in ("empty", "no-stock") else 1 if name == "last-unit" else 30
                    if name in ("wrong", "group-sellers") and (
                        (loc == locs[0] and pi == 1) or (loc == locs[1] and pi == 0)
                    ):
                        qty = 0
                    if qty:
                        await record_movement_and_adjust_balance(
                            session,
                            tenant_id=tenant,
                            storage_location_id=loc.id,
                            product_id=uuid.UUID(p["id"]),
                            container_kind=kind,
                            container_id=box.id if box else None,
                            quantity_delta=qty,
                            quantity_packed_delta=qty if name == "packing-flag" else 0,
                            movement_type="inbound_intake",
                            actor_user_id=actor_id,
                        )
                    else:
                        session.add(
                            InventoryBalance(
                                tenant_id=tenant,
                                storage_location_id=loc.id,
                                product_id=uuid.UUID(p["id"]),
                                container_kind=kind,
                                container_id=box.id if box else None,
                                quantity=0,
                                quantity_unpacked=0,
                                quantity_packed=0,
                            )
                        )
                    sf["initial"][p["id"]] = qty
                f["sources"].append(sf)
            count_supplies = (
                2 if name in ("group", "ozon-group", "last-unit", "group-sellers") else 1
            )
            is_ozon = name in ("ozon", "ozon-group", "ozon-null")
            for si in range(count_supplies):
                supply_seller = seller2 if name == "group-sellers" and si == 1 else seller
                supply_warehouse = (
                    warehouse2.id if name == "group-sellers" and si == 1 else warehouse
                )
                supply = FbsSupply(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    seller_id=supply_seller,
                    warehouse_id=supply_warehouse,
                    marketplace="ozon" if is_ozon else "wb",
                    wb_supply_id=None if is_ozon else f"WB-PICK-CI-{index}-{si}",
                    name=f"Picking CI {name} {si}",
                    status="assembling",
                    delivery_type="warehouse_sc",
                )
                session.add(supply)
                await session.flush()
                f["supplies"].append(str(supply.id))
                if name == "empty":
                    continue
                ozon_order = None
                for pi, p in enumerate(f["products"]):
                    if name == "group-sellers" and pi != si:
                        continue
                    plan = (
                        14
                        if name in ("manual", "early-exit", "manual-conflict")
                        else 6
                        if name in ("burst", "number-scan") and pi == 0
                        else 3
                    )
                    if name == "last-unit":
                        plan = 1
                    if is_ozon:
                        plan = 2 + pi
                    for oi in range(1 if is_ozon else plan):
                        order = FbsOrder(
                            id=uuid.uuid4(),
                            tenant_id=tenant,
                            seller_id=supply_seller,
                            warehouse_id=supply_warehouse,
                            supply_id=supply.id,
                            product_id=uuid.UUID(p["id"]),
                            marketplace="ozon" if is_ozon else "wb",
                            external_order_id=f"OZ-PICK-{index}-{si}-{pi}" if is_ozon else None,
                            wb_order_id=990000000 + index * 1000 + si * 100 + pi * 10 + oi,
                            wb_barcode=p["barcode"],
                            wb_article=p["sku"],
                            wb_warehouse_id=501001,
                            created_at_wb=now - timedelta(hours=1),
                            deadline_at=now + timedelta(days=2),
                            mapping_status="mapped",
                            reserve_status="reserved",
                            status="in_supply",
                        )
                        if is_ozon and ozon_order is not None:
                            order = ozon_order
                        else:
                            session.add(order)
                            await session.flush()
                            if is_ozon:
                                ozon_order = order
                        f["orders"].append(
                            {"id": str(order.id), "supply": str(supply.id), "product": p["id"]}
                        )
                        if is_ozon:
                            position = FbsOrderProduct(
                                id=uuid.uuid4(),
                                order_id=order.id,
                                product_id=uuid.UUID(p["id"]),
                                ozon_sku=770000 + index * 10 + pi,
                                offer_id=f"OZ-ART-{index}-{pi}",
                                name=p["name"],
                                quantity=plan,
                                reserved_quantity=plan,
                                position_index=pi,
                            )
                            session.add(position)
                            await session.flush()
                            session.add(
                                FbsOrderProductReservation(
                                    tenant_id=tenant,
                                    order_product_id=position.id,
                                    product_id=position.product_id,
                                    warehouse_id=supply_warehouse,
                                    quantity=plan,
                                )
                            )
                            f["positions"].append(
                                {
                                    "id": str(position.id),
                                    "order": str(order.id),
                                    "product": p["id"],
                                    "supply": str(supply.id),
                                    "warehouse": str(supply_warehouse),
                                    "quantity": plan,
                                }
                            )
                        else:
                            session.add(
                                FbsOrderReservation(
                                    tenant_id=tenant,
                                    fbs_order_id=order.id,
                                    product_id=uuid.UUID(p["id"]),
                                    warehouse_id=supply_warehouse,
                                    quantity=1,
                                )
                            )
            if name in ("group", "ozon-group", "group-sellers"):
                task = FbsAssemblyTask(
                    id=uuid.uuid4(),
                    tenant_id=tenant,
                    number=f"CI-{index}",
                    idempotency_key=f"ci-{index}",
                )
                session.add(task)
                await session.flush()
                for sid in f["supplies"]:
                    session.add(FbsAssemblyTaskSupply(task_id=task.id, supply_id=uuid.UUID(sid)))
                f["task"] = str(task.id)
            manifest[name] = f
        await session.commit()
        balances = (
            await session.scalars(
                select(InventoryBalance).where(InventoryBalance.tenant_id == tenant)
            )
        ).all()
        stock = {}
        for b in balances:
            assert b.quantity == b.quantity_unpacked + b.quantity_packed, (
                "Fixture physical split must be coherent"
            )
            stock[str(b.product_id)] = stock.get(str(b.product_id), 0) + b.quantity
    seed["picking"] = manifest
    seed["stock_by_product"] = stock
    for key in ("seller_token", "emulator_admin_token"):
        seed.pop(key, None)
    sys.stdout.write(json.dumps(seed, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
