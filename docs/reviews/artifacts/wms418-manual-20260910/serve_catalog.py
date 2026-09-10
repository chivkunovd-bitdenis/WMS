"""Serve the real WMS API with isolated synthetic catalogue data for manual UI QA."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "backend"
DATA = Path(__file__).resolve().parent / "runtime"
DATA.mkdir(exist_ok=True)
os.chdir(DATA)  # Do not load a real checkout's .env.
sys.path.insert(0, str(BACKEND))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DATA / 'catalog.sqlite'}"
os.environ["WMS_DATA_DIR"] = str(DATA / "files")
os.environ["WMS_ALLOW_PUBLIC_REGISTRATION"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-at-least-32-characters-long"
os.environ["APP_ENV"] = "development"

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
import uvicorn

from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models import Base
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from tests.test_products_ozon_catalog import _register_admin

app = create_app()


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        if await session.scalar(select(Seller.id).limit(1)):
            return
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register_admin(client, "wms418-manual")
        sellers = []
        for name in ("Первый учебный", "Второй учебный"):
            response = await client.post("/sellers", headers=headers, json={"name": name})
            assert response.status_code == 201
            sellers.append(uuid.UUID(response.json()["id"]))
    async with SessionLocal() as session:
        rows = [await session.get(Seller, value) for value in sellers]
        for i, (wb, ozon, owner, category) in enumerate([
            (True, False, 0, "Одежда"), (False, True, 0, "Одежда"),
            (True, True, 0, "Обувь"), (False, False, 0, "Одежда"),
            (True, None, 1, "Одежда"), (False, None, 1, "Обувь"),
        ]):
            seller = rows[owner]
            product = Product(tenant_id=seller.tenant_id, seller_id=seller.id,
                name=f"Учебный товар {i}", sku_code=f"WMS418-{i}", wb_nm_id=41800+i,
                fbs_stock_sync_enabled=wb, fbs_ozon_stock_sync_enabled=ozon)
            session.add(product)
            await session.flush()
            session.add(SellerWildberriesImportedCard(tenant_id=seller.tenant_id,
                seller_id=seller.id, nm_id=41800+i, raw_json={"subjectName": category}))
            if i in (1, 2, 3, 4):
                session.add(ProductMarketplaceLink(tenant_id=seller.tenant_id,
                    seller_id=seller.id, product_id=product.id, marketplace="ozon",
                    external_sku=f"OZ418-{i}", is_active=True))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    uvicorn.run(app, host="127.0.0.1", port=18418, access_log=False)
