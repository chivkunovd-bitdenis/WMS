"""Create this synthetic QA in an empty, named local DB; never reset a DB."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

from runtime import DB_NAME, QA
from sqlalchemy import text
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.models.product import Product
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.fbs_supply import FbsSupply
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderReservation,
    FbsOrderProduct,
    FbsOrderProductPick,
    FbsOrderProductReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.stock_direction import StockDirection
from app.models.marketplace_unload import (
    MarketplaceUnloadRequest,
    MarketplaceUnloadLine,
)
from app.services.passwords import hash_password
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.fbs_picking_service import manual_pick_product


def uid(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, "wms058-browser-5c371f39/" + name)


async def main():
    async with engine.begin() as connection:
        assert await connection.scalar(text("select current_database()")) == DB_NAME
        assert (
            await connection.scalar(
                text(
                    "select count(*) from information_schema.tables where table_schema='public'"
                )
            )
            == 0
        ), "Refusing to overwrite existing QA"
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    t, seller, wh, user = uid("tenant"), uid("seller"), uid("warehouse"), uid("user")
    info = {
        "email": "qa058@example.com",
        "password": "password123",
        "tenant": str(t),
        "seller": str(seller),
        "warehouse": str(wh),
    }
    async with SessionLocal() as s:
        s.add(
            Tenant(
                id=t,
                name="QA058 availability",
                slug="qa058-availability",
                address_storage_enabled=True,
            )
        )
        await s.flush()
        actor = User(
            id=user,
            tenant_id=t,
            email=info["email"],
            password_hash=hash_password(info["password"]),
            role="fulfillment_admin",
        )
        s.add_all(
            [
                actor,
                Seller(id=seller, tenant_id=t, name="QA058 Seller"),
                Warehouse(id=wh, tenant_id=t, name="QA058 Warehouse", code="QA058-WH"),
            ]
        )
        await s.flush()
        loc_a = StorageLocation(
            id=uid("A"), tenant_id=t, warehouse_id=wh, code="QA058-A", barcode="QA058-A"
        )
        loc_b = StorageLocation(
            id=uid("B"), tenant_id=t, warehouse_id=wh, code="QA058-B", barcode="QA058-B"
        )
        s.add_all([loc_a, loc_b])
        sorting = await get_or_create_sorting_location(s, t, wh)
        await s.flush()
        box = WarehouseBox(
            id=uid("box"),
            tenant_id=t,
            warehouse_id=wh,
            storage_location_id=loc_b.id,
            internal_barcode="WHB-QA058-BOX",
        )
        legacy_box = WarehouseBox(
            id=uid("legacy-box"),
            tenant_id=t,
            warehouse_id=wh,
            storage_location_id=sorting.id,
            internal_barcode="WHB-QA058-LEGACY",
        )
        s.add_all([box, legacy_box])
        binding = FbsWarehouseBinding(
            id=uid("binding"),
            tenant_id=t,
            seller_id=seller,
            wms_warehouse_id=wh,
            wb_warehouse_id=958058,
            marketplace="wb",
            stock_sync_enabled=False,
        )
        s.add(binding)
        for name, market in [("own", "wb"), ("foreign", "wb"), ("legacy", "ozon")]:
            s.add(
                FbsSupply(
                    id=uid("supply-" + name),
                    tenant_id=t,
                    seller_id=seller,
                    warehouse_id=wh,
                    marketplace=market,
                    status="assembling",
                    name="QA058 " + name,
                    delivery_type="warehouse_sc",
                    wb_supply_id="QA058-" + name,
                )
            )
        products = {}
        for key, name, units in [
            ("P", "QA058 Percentage — FBO 5", False),
            ("U", "QA058 Units — FBO 3", True),
            ("Z", "QA058 Own reserve — FBO 0", False),
            ("L", "QA058 Legacy NULL source", False),
        ]:
            p = Product(
                id=uid("product-" + key),
                tenant_id=t,
                seller_id=seller,
                name=name,
                sku_code="QA058-" + key,
                wb_barcode="95805800" + str(len(products)),
                fbs_units_mode=units,
            )
            s.add(p)
            products[key] = p
        await s.flush()
        for key, p in products.items():
            sources = (
                [(loc_a.id, None, 4), (sorting.id, None, 2), (loc_b.id, box.id, 4)]
                if key in ["P", "U"]
                else [
                    (
                        sorting.id,
                        legacy_box.id if key == "L" else None,
                        2 if key == "L" else 1,
                    )
                ]
            )
            for index, (loc, container, qty) in enumerate(sources):
                s.add(
                    InventoryBalance(
                        id=uid(f"balance-{key}-{index}"),
                        tenant_id=t,
                        product_id=p.id,
                        storage_location_id=loc,
                        container_kind="box" if container else None,
                        container_id=container,
                        quantity=qty,
                        quantity_unpacked=qty,
                        quantity_packed=0,
                    )
                )
                s.add(
                    InventoryMovement(
                        id=uid(f"movement-{key}-{index}"),
                        tenant_id=t,
                        seller_id=seller,
                        warehouse_id=wh,
                        product_id=p.id,
                        storage_location_id=loc,
                        container_kind="box" if container else None,
                        container_id=container,
                        quantity_delta=qty,
                        movement_type="inbound_intake",
                    )
                )
            if key in ["P", "U"]:
                s.add(
                    StockDirection(
                        tenant_id=t,
                        product_id=p.id,
                        name="QA058 Other direction",
                        quantity=2,
                        is_fbs=False,
                    )
                )
                s.add(
                    FbsBindingStockPool(
                        tenant_id=t, binding_id=binding.id, product_id=p.id, quantity=2
                    )
                )
            if key == "L":
                continue
            for index in range(3 if key in ["P", "U"] else 1):
                other = index > 0
                order = FbsOrder(
                    id=uid(f"order-{key}-{index}"),
                    tenant_id=t,
                    seller_id=seller,
                    warehouse_id=wh,
                    product_id=p.id,
                    supply_id=uid("supply-foreign" if other else "supply-own"),
                    marketplace="wb",
                    wb_order_id=958058000 + len(products) + ord(key) * 10 + index,
                    wb_warehouse_id=958058,
                    status="assembling",
                    mapping_status="mapped",
                    reserve_status="reserved",
                    pick_status="pending",
                    pack_status="pending",
                    created_at_wb=now,
                    deadline_at=now + timedelta(days=1),
                )
                s.add(order)
                await s.flush()
                s.add(
                    FbsOrderReservation(
                        tenant_id=t,
                        fbs_order_id=order.id,
                        product_id=p.id,
                        warehouse_id=wh,
                        quantity=1,
                    )
                )
        await s.commit()
        # Existing real WB service records foreign assignments; no physical movement.
        for key in ["P", "U"]:
            for index, location, container in [
                (1, loc_a.id, None),
                (2, loc_b.id, box.id),
            ]:
                await manual_pick_product(
                    s,
                    t,
                    uid("supply-foreign"),
                    location_id=location,
                    product_id=products[key].id,
                    order_id=uid(f"order-{key}-{index}"),
                    container_kind="box" if container else None,
                    container_id=container,
                    actor=actor,
                    idempotency_key=f"qa058-{key}-{index}",
                )
        await s.commit()
        # A historic NULL fact has no evidence of its source box. Preserve it as NULL.
        order = FbsOrder(
            id=uid("order-legacy"),
            tenant_id=t,
            seller_id=seller,
            warehouse_id=wh,
            product_id=products["L"].id,
            supply_id=uid("supply-legacy"),
            marketplace="ozon",
            wb_order_id=958058999,
            external_order_id="QA058-LEGACY-1",
            status="assembling",
            mapping_status="mapped",
            reserve_status="reserved",
            pick_status="picked",
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
        )
        s.add(order)
        await s.flush()
        position = FbsOrderProduct(
            id=uid("position-legacy"),
            order_id=order.id,
            product_id=products["L"].id,
            ozon_sku=958058999,
            quantity=1,
            position_index=0,
        )
        s.add(position)
        await s.flush()
        s.add(
            FbsOrderProductReservation(
                tenant_id=t,
                order_product_id=position.id,
                product_id=products["L"].id,
                warehouse_id=wh,
                quantity=1,
            )
        )
        s.add(
            FbsOrderProductPick(
                id=uid("pick-legacy"),
                tenant_id=t,
                order_product_id=position.id,
                fbs_supply_id=uid("supply-legacy"),
                source_storage_location_id=sorting.id,
                sorting_storage_location_id=sorting.id,
                product_id=products["L"].id,
                picked_at=now,
                picked_by_user_id=user,
                scan_idempotency_key="qa058-historical-null",
                inventory_movement_id=None,
                source_container_kind=None,
                source_container_id=None,
            )
        )
        for label, status in [("draft", "draft"), ("sources", "confirmed")]:
            req = MarketplaceUnloadRequest(
                id=uid("mp-" + label),
                tenant_id=t,
                seller_id=seller,
                warehouse_id=wh,
                marketplace="wb",
                status=status,
                document_number="QA058-" + label,
                display_number="QA058-" + label,
            )
            s.add(req)
            await s.flush()
            if label == "sources":
                for key, qty in [("P", 5), ("U", 3), ("Z", 1)]:
                    s.add(
                        MarketplaceUnloadLine(
                            request_id=req.id, product_id=products[key].id, quantity=qty
                        )
                    )
        await s.commit()
        info.update(
            {
                "products": {k: str(v.id) for k, v in products.items()},
                "supplies": {
                    k: str(uid("supply-" + k)) for k in ["own", "foreign", "legacy"]
                },
                "mp": {k: str(uid("mp-" + k)) for k in ["draft", "sources"]},
                "locations": {
                    "A": str(loc_a.id),
                    "B": str(loc_b.id),
                    "sorting": str(sorting.id),
                },
                "box": str(box.id),
                "legacy_box": str(legacy_box.id),
            }
        )
    (QA / "seed.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
    print(json.dumps(info, ensure_ascii=False))
    await engine.dispose()


asyncio.run(main())
