"""Isolated local messenger fixture and server. Never loads project .env.

Run from backend: .venv/bin/python scripts/wms397_chat_fixture.py
Dedicated DB must already exist: createdb wms397_chat_evening_ui_20260910
No warehouse operations, balances, integration calls, or outgoing email.
"""

# ruff: noqa: E402
# Imports follow the isolated environment intentionally.
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "postgresql+psycopg:///wms397_chat_evening_ui_20260910"
os.environ["WMS_DATA_DIR"] = str(ROOT / "tests/wms_pytest_data_chat397_ui")
os.environ["JWT_SECRET_KEY"] = "isolated-chat397-fixture-only-not-a-production-secret"
# Disable dotenv before app modules initialize settings. Values below apply only
# to this dedicated process; no environment file or shared setting is modified.
fixture_dir = Path(os.environ["WMS_DATA_DIR"])
fixture_dir.mkdir(parents=True, exist_ok=True)
os.chdir(fixture_dir)
from app.core.settings import settings

settings.database_url = os.environ["DATABASE_URL"]
settings.wms_data_dir = os.environ["WMS_DATA_DIR"]
settings.wms_s3_bucket = None
settings.jwt_secret_key = os.environ["JWT_SECRET_KEY"]

from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.passwords import hash_password


async def seed() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        if (
            await session.execute(select(Tenant).where(Tenant.slug == "chat397-fixture"))
        ).scalar_one_or_none():
            print("Existing isolated fixture preserved", flush=True)
            await engine.dispose()
            return
        tenant = Tenant(name="Учебный склад WMS397", slug="chat397-fixture")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Учебный селлер WMS397")
        warehouse = Warehouse(tenant_id=tenant.id, name="Учебный склад", code="CHAT397")
        session.add_all([seller, warehouse])
        await session.flush()
        # Deliberately public dummy credentials, valid only for the isolated DB.
        for email, role, sid in [
            ("warehouse-chat397@example.com", "fulfillment_admin", None),
            ("seller-chat397@example.com", "fulfillment_seller", seller.id),
            ("staff-chat397@example.com", "fulfillment_staff", None),
        ]:
            session.add(
                User(
                    tenant_id=tenant.id,
                    seller_id=sid,
                    email=email,
                    role=role,
                    password_hash=hash_password("Chat397-test-only"),
                )
            )
        product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Учебная футболка",
            sku_code="CHAT397-TSHIRT",
        )
        session.add(product)
        await session.flush()
        supply = FbsSupply(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            name="Учебная FBS-поставка 397",
            delivery_type="warehouse",
        )
        inbound = InboundIntakeRequest(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            status="draft",
            document_number="IN-CHAT397",
        )
        unload = MarketplaceUnloadRequest(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            status="draft",
            document_number="MP-CHAT397",
        )
        outbound = OutboundShipmentRequest(
            tenant_id=tenant.id, seller_id=seller.id, warehouse_id=warehouse.id, status="draft"
        )
        session.add_all([supply, inbound, unload, outbound])
        await session.flush()
        order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            supply_id=supply.id,
            wb_order_id=3970001,
            wb_warehouse_id=397,
            created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(days=1),
            mapping_status="mapped",
            reserve_status="not_reserved",
            wb_article="CHAT397-TSHIRT",
        )
        session.add(
            FbsWarehouseBinding(
                tenant_id=tenant.id,
                seller_id=seller.id,
                wb_warehouse_id=397,
                wms_warehouse_id=warehouse.id,
                stock_sync_enabled=False,
            )
        )
        session.add_all(
            [
                order,
                InboundIntakeLine(request_id=inbound.id, product_id=product.id, expected_qty=2),
                MarketplaceUnloadLine(request_id=unload.id, product_id=product.id, quantity=2),
                OutboundShipmentLine(request_id=outbound.id, product_id=product.id, quantity=2),
            ]
        )
        await session.commit()
        print(
            json.dumps(
                {
                    "seller_id": str(seller.id),
                    "fbs_order": str(order.id),
                    "fbs_supply": str(supply.id),
                    "inbound_intake": str(inbound.id),
                    "marketplace_unload": str(unload.id),
                    "outbound_shipment": str(outbound.id),
                }
            ),
            flush=True,
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=8397, workers=1, lifespan="off")
