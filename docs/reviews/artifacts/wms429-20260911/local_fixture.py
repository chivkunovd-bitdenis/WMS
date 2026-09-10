"""One isolated local PostgreSQL fixture for the WMS-429 manual UI pass.

Run with the backend Python and the exact release checkout to inspect:
    backend/.venv/bin/python docs/reviews/artifacts/wms429-20260911/local_fixture.py \
      /Users/deniscivkunov/Projects/WMS/.worktrees/wms-release-20260911

It creates only ``wms429_ui_20260911`` on the local PostgreSQL server, contains
only dummy authentication, and serves the API at http://127.0.0.1:8429.
No project .env, marketplace account, external client, or live API is used.
"""

# ruff: noqa: E402
# The isolated environment and release-checkout import path must be set first.
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg import sql

DATABASE_NAME = "wms429_ui_20260911"
DATABASE_URL = f"postgresql+psycopg_async:///{DATABASE_NAME}"
FIXTURE_DIR = Path("/tmp/wms429_ui_20260911")
PORT = 8429
LOGIN_EMAIL = "warehouse-wms429@example.com"
LOGIN_PASSWORD = "WMS429-local-fixture-only"


def parse_repo_root() -> Path:
    parser = argparse.ArgumentParser(description="Start the isolated WMS-429 local fixture")
    parser.add_argument("repo_root", type=Path, help="release checkout whose backend must be served")
    args = parser.parse_args()
    repo_root = args.repo_root.expanduser().resolve()
    if not (repo_root / "backend" / "app" / "main.py").is_file():
        raise SystemExit(f"Not a WMS release checkout: {repo_root}")
    return repo_root


def create_database() -> None:
    """Create the single named local database without touching any other database."""
    with psycopg.connect("dbname=postgres", autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE_NAME,))
            if cursor.fetchone() is None:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE_NAME)))


def configure_isolated_process(repo_root: Path) -> None:
    """Keep Settings away from dotenv and make every external route inert."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(FIXTURE_DIR)
    os.environ.update(
        {
            "DATABASE_URL": DATABASE_URL,
            "WMS_DATA_DIR": str(FIXTURE_DIR / "data"),
            "JWT_SECRET_KEY": "wms429-local-fixture-only-not-a-production-secret",
            "WMS_ALLOW_PUBLIC_REGISTRATION": "false",
            "WMS_AUTO_CREATE_SCHEMA": "0",
            "WMS_BOOTSTRAP_ADMIN": "0",
            "WMS_OZON_LIVE_API": "false",
            "OZON_SELLER_API_BASE": "http://127.0.0.1:9",
            "WILDBERRIES_CONTENT_API_BASE": "http://127.0.0.1:9",
            "WILDBERRIES_SUPPLIES_API_BASE": "http://127.0.0.1:9",
            "WILDBERRIES_MARKETPLACE_API_BASE": "http://127.0.0.1:9",
            "WMS_S3_BUCKET": "",
            "DADATA_TOKEN": "",
            "WMS_DADATA_TOKEN": "",
        }
    )
    sys.path.insert(0, str(repo_root / "backend"))


async def seed() -> dict[str, str]:
    from app.db.session import SessionLocal, engine
    from app.models import Base
    from app.models.fbs_order import FbsOrder, FbsOrderProduct
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.product import Product
    from app.models.product_marketplace_link import ProductMarketplaceLink
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
    from app.models.user import User
    from app.models.warehouse import Warehouse
    from app.services.passwords import hash_password
    from sqlalchemy import select

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        existing = await session.scalar(select(Tenant).where(Tenant.slug == "wms429-ui"))
        if existing is not None:
            await engine.dispose()
            return {"database": DATABASE_NAME, "status": "already_seeded"}

        now = datetime.now(UTC)
        tenant = Tenant(name="Учебный выпуск WMS-429", slug="wms429-ui")
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="Учебный селлер WMS-429")
        warehouse = Warehouse(
            tenant_id=tenant.id,
            name="Учебный FBS-склад WMS-429",
            code="WMS429-FBS",
        )
        session.add_all([seller, warehouse])
        await session.flush()
        session.add(
            User(
                tenant_id=tenant.id,
                email=LOGIN_EMAIL,
                role="fulfillment_admin",
                password_hash=hash_password(LOGIN_PASSWORD),
            )
        )

        wb_product = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Учебный WB товар",
            sku_code="WMS429-WB-01",
            wb_barcode="429100000001",
            wb_nm_id=4291001,
            fbs_stock_sync_enabled=True,
            fbs_ozon_stock_sync_enabled=False,
        )
        ozon_product_one = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Учебный Ozon товар A",
            sku_code="WMS429-OZ-A",
            wb_barcode="999100000001",
            fbs_stock_sync_enabled=False,
            fbs_ozon_stock_sync_enabled=True,
        )
        ozon_product_two = Product(
            tenant_id=tenant.id,
            seller_id=seller.id,
            name="Учебный Ozon товар B",
            sku_code="WMS429-OZ-B",
            wb_barcode="999100000002",
            fbs_stock_sync_enabled=True,
            fbs_ozon_stock_sync_enabled=True,
        )
        session.add_all([wb_product, ozon_product_one, ozon_product_two])
        await session.flush()

        session.add_all(
            [
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=wb_product.id,
                    marketplace="wb",
                    external_product_id="fixture-wb-product-429",
                    external_offer_id="fixture-wb-offer-429",
                    external_sku="fixture-wb-sku-429",
                    external_barcodes=["429100000001"],
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=ozon_product_one.id,
                    marketplace="ozon",
                    external_product_id="fixture-ozon-product-a-429",
                    external_offer_id="fixture-ozon-offer-a-429",
                    external_sku="fixture-ozon-sku-a-429",
                    external_barcodes=["429200000001"],
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    product_id=ozon_product_two.id,
                    marketplace="ozon",
                    external_product_id="fixture-ozon-product-b-429",
                    external_offer_id="fixture-ozon-offer-b-429",
                    external_sku="fixture-ozon-sku-b-429",
                    external_barcodes=["429200000002"],
                ),
                TenantWbMpWarehouse(
                    tenant_id=tenant.id,
                    wb_warehouse_id=429001,
                    name="Учебный склад WB-429",
                    is_active=True,
                ),
                TenantWbMpWarehouse(
                    tenant_id=tenant.id,
                    wb_warehouse_id=-429001,
                    name="Учебный склад Ozon-429",
                    is_active=True,
                ),
                FbsWarehouseBinding(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    marketplace="wb",
                    wb_warehouse_id=429001,
                    external_warehouse_id="fixture-wb-warehouse-429",
                    wms_warehouse_id=warehouse.id,
                    stock_sync_enabled=True,
                    served=True,
                ),
                FbsWarehouseBinding(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    marketplace="ozon",
                    wb_warehouse_id=-429001,
                    external_warehouse_id="fixture-ozon-warehouse-429",
                    wms_warehouse_id=warehouse.id,
                    stock_sync_enabled=True,
                    served=True,
                ),
            ]
        )

        wb_supply = FbsSupply(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            marketplace="wb",
            external_supply_id="fixture-wb-supply-429",
            wb_supply_id="FIXTURE-WB-429",
            name="Учебная поставка WB WMS-429",
            delivery_type="warehouse_sc",
            status="assembling",
        )
        ozon_supply = FbsSupply(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            marketplace="ozon",
            external_supply_id="fixture-ozon-supply-429",
            wb_supply_id=None,
            name="Учебная поставка Ozon WMS-429",
            delivery_type="warehouse_sc",
            status="assembling",
        )
        session.add_all([wb_supply, ozon_supply])
        await session.flush()

        wb_order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=wb_product.id,
            supply_id=wb_supply.id,
            marketplace="wb",
            external_order_id="fixture-wb-order-429",
            wb_order_id=4290001,
            wb_warehouse_id=429001,
            wb_article="WMS429-WB-01",
            wb_barcode="429100000001",
            status="new",
            supplier_status="new",
            mapping_status="mapped",
            reserve_status="reserved",
            created_at_wb=now - timedelta(hours=2),
            deadline_at=now + timedelta(hours=20),
        )
        # WMS-422: a past Ozon deadline must remain in the New worklist.
        ozon_order = FbsOrder(
            tenant_id=tenant.id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            product_id=None,
            supply_id=ozon_supply.id,
            marketplace="ozon",
            external_order_id="fixture-ozon-posting-429",
            wb_order_id=4290002,
            wb_warehouse_id=-429001,
            status="new",
            supplier_status="new",
            mapping_status="mapped",
            reserve_status="reserved",
            created_at_wb=now - timedelta(days=2),
            deadline_at=now - timedelta(days=1),
        )
        session.add_all([wb_order, ozon_order])
        await session.flush()
        session.add_all(
            [
                FbsOrderProduct(
                    order_id=ozon_order.id,
                    product_id=ozon_product_one.id,
                    ozon_sku=4292001,
                    offer_id="fixture-ozon-offer-a-429",
                    name="Учебный Ozon товар A",
                    quantity=1,
                    position_index=0,
                ),
                FbsOrderProduct(
                    order_id=ozon_order.id,
                    product_id=ozon_product_two.id,
                    ozon_sku=4292002,
                    offer_id="fixture-ozon-offer-b-429",
                    name="Учебный Ozon товар B",
                    quantity=2,
                    position_index=1,
                ),
            ]
        )
        await session.commit()
        result = {
            "database": DATABASE_NAME,
            "login_email": LOGIN_EMAIL,
            "login_password": LOGIN_PASSWORD,
            "wb_supply_id": str(wb_supply.id),
            "ozon_supply_id": str(ozon_supply.id),
            "wb_order_id": str(wb_order.id),
            "ozon_order_id": str(ozon_order.id),
        }
    await engine.dispose()
    return result


def main() -> None:
    repo_root = parse_repo_root()
    create_database()
    configure_isolated_process(repo_root)
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False), flush=True)
    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, workers=1, lifespan="off")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        main()
