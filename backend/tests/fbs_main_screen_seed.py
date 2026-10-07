"""Isolated main-screen fixture; reuse the real WB/Celery browser seed.

Manifest expectations describe inserted records, never a worklist calculation.
Run only in the disposable compose stack used by run_fbs_main_screen.sh.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from tests.fbs_browser_e2e_seed import _main as seed_browser


async def main() -> None:
    database = make_url(os.environ.get("DATABASE_URL", ""))
    api = urlparse(os.environ.get("FBS_E2E_API_BASE", "http://127.0.0.1:8000"))
    if (
        os.environ.get("FBS_MAIN_DISPOSABLE") != "1"
        or database.host != "db"
        or database.database != "wms"
        or api.hostname != "127.0.0.1"
    ):
        raise RuntimeError(
            "Seed requires the explicit disposable compose database db/wms and loopback API"
        )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        await seed_browser()
    seed = json.loads(output.getvalue())
    tenant = uuid.UUID(seed["tenant_id"])
    warehouse = uuid.UUID(seed["warehouse_id"])
    now = datetime.now(UTC)
    fixture: dict[str, Any] = {"orders": {}, "supplies": {}, "positions": []}
    async with SessionLocal() as session:
        sellers = list(
            (await session.scalars(select(Seller).where(Seller.tenant_id == tenant))).all()
        )
        sellers.sort(key=lambda seller: seller.name)
        fixture["sellers"] = [{"id": str(s.id), "name": s.name} for s in sellers]
        original = await session.get(
            FbsOrder, uuid.UUID(seed["orders"]["warehouse_sc"][0]["wms_order_id"])
        )
        assert original is not None
        products = {
            seller.id: await session.scalar(
                select(Product)
                .where(Product.tenant_id == tenant, Product.seller_id == seller.id)
                .order_by(Product.id)
            )
            for seller in sellers
        }
        assert all(products.values()), "Every seller needs their own seeded product"
        products[original.seller_id] = await session.get(Product, original.product_id)
        # Explicit records on both sides of deadline/status boundaries.
        specs = [
            ("wb_new", "wb", "new", "new", 2, 0),
            ("wb_other_seller", "wb", "new", None, 3, 1),
            ("wb_expired", "wb", "new", "new", -2, 0),
            ("wb_external", "wb", "new", "confirm", 2, 0),
            ("wb_cancelled", "wb", "cancelled", "cancel", 2, 0),
            ("wb_defect", "wb", "defect", "cancel", 2, 0),
            ("ozon_new", "ozon", "new", "new", -2, 0),
            ("ozon_cancelled", "ozon", "cancelled", "cancel", -2, 0),
            ("wb_unpublished", "wb", "new", "new", 2, 0),
        ]
        for index, (key, marketplace, status, supplier, days, seller_index) in enumerate(specs):
            product = products[sellers[seller_index].id]
            assert product is not None
            order = FbsOrder(
                id=uuid.uuid4(),
                tenant_id=tenant,
                seller_id=sellers[seller_index].id,
                warehouse_id=warehouse,
                product_id=product.id,
                marketplace=marketplace,
                wb_order_id=880000001 + index,
                external_order_id=f"MAIN-{key}" if marketplace == "ozon" else None,
                wb_article=f"MAIN-{key}",
                wb_barcode=product.wb_barcode,
                wb_chrt_id=product.wb_chrt_id,
                wb_nm_id=product.wb_nm_id,
                wb_warehouse_id=501001,
                status=status,
                supplier_status=supplier,
                mapping_status="mapped",
                reserve_status="not_published" if key == "wb_unpublished" else "reserved",
                created_at_wb=now - timedelta(hours=1),
                deadline_at=now + timedelta(days=days),
            )
            session.add(order)
            fixture["orders"][key] = {
                "id": str(order.id),
                "number": order.external_order_id or str(order.wb_order_id),
            }
            if marketplace == "ozon":
                for position, quantity in enumerate((2, 3)):
                    values: dict[str, Any] = {
                        "name": f"Ozon main position {position + 1}",
                        "article": f"OZ-MAIN-{position + 1}",
                        "sku": str(770001 + position),
                        "quantity": quantity,
                    }
                    session.add(
                        FbsOrderProduct(
                            order_id=order.id,
                            product_id=original.product_id,
                            name=values["name"],
                            offer_id=values["article"],
                            ozon_sku=int(values["sku"]),
                            quantity=quantity,
                            position_index=position,
                            reserved_quantity=quantity,
                        )
                    )
                    if key == "ozon_new":
                        fixture["positions"].append(values)
        for index, status in enumerate(("draft", "assembling", "packed", "in_delivery", "done")):
            supply = FbsSupply(
                id=uuid.uuid4(),
                tenant_id=tenant,
                seller_id=sellers[0].id,
                warehouse_id=warehouse,
                marketplace="wb",
                wb_supply_id=f"WB-MAIN-{status}",
                name=f"Main screen {status}",
                status=status,
                delivery_type="warehouse_sc",
                updated_at=now + timedelta(seconds=index),
                delivered_at=now - timedelta(hours=1) if status == "done" else None,
            )
            session.add(supply)
            fixture["supplies"][status] = {"id": str(supply.id), "name": supply.name}
            if status == "done":
                # Three known valid durations and one negative control. All
                # created this week; the service must exclude the negative one.
                for offset, hours in enumerate((6, 18, 30, -0.5)):
                    session.add(
                        FbsOrder(
                            id=uuid.uuid4(),
                            tenant_id=tenant,
                            seller_id=sellers[0].id,
                            warehouse_id=warehouse,
                            product_id=original.product_id,
                            marketplace="wb",
                            wb_order_id=889000000 + offset,
                            wb_warehouse_id=501001,
                            supply_id=supply.id,
                            status="done",
                            supplier_status="complete",
                            mapping_status="mapped",
                            reserve_status="released",
                            created_at_wb=now - timedelta(hours=1 + hours),
                            deadline_at=now + timedelta(days=2),
                        )
                    )
        balances = (
            await session.scalars(
                select(InventoryBalance).where(InventoryBalance.tenant_id == tenant)
            )
        ).all()
        fixture["stock_by_product"] = {}
        for balance in balances:
            key = str(balance.product_id)
            fixture["stock_by_product"][key] = (
                fixture["stock_by_product"].get(key, 0) + balance.quantity
            )
        await session.commit()
    seed["main"] = fixture
    # Do not persist emulator tokens; browser needs only disposable account login.
    for key in ("seller_token", "emulator_admin_token"):
        seed.pop(key, None)
    sys.stdout.write(json.dumps(seed, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
