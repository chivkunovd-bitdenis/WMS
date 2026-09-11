"""Seed deterministic WMS-430 storage-report rows into the isolated WMS-429 DB.

Run with the release checkout after ``local_fixture.py`` has created its database:
    backend/.venv/bin/python docs/reviews/artifacts/wms429-20260911/storage_report_fixture.py \
      /Users/deniscivkunov/Projects/WMS/.worktrees/wms-release-20260911

The seed is idempotent. It adds only the two named training products, two tariff
versions, and four daily storage ledger charges. It never reads project .env or
any production database.
"""

# ruff: noqa: E402
# The isolated environment and release-checkout import path must be set first.
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

DATABASE_NAME = "wms429_ui_20260911"
DATABASE_URL = f"postgresql+psycopg_async:///{DATABASE_NAME}"
FIXTURE_DIR = Path("/tmp/wms429_ui_20260911")
TENANT_SLUG = "wms429-ui"
SELLER_NAME = "Учебный селлер WMS-429"
WAREHOUSE_CODE = "WMS429-FBS"
SOURCE = "wms430_storage_fixture"
SOURCE_TYPE = "storage_day"
DAY_ONE = date(2026, 9, 8)
DAY_TWO = date(2026, 9, 9)


def parse_repo_root() -> Path:
    parser = argparse.ArgumentParser(description="Seed the isolated WMS-430 storage fixture")
    parser.add_argument("repo_root", type=Path, help="release checkout whose models must be used")
    args = parser.parse_args()
    repo_root = args.repo_root.expanduser().resolve()
    if not (repo_root / "backend" / "app" / "main.py").is_file():
        raise SystemExit(f"Not a WMS release checkout: {repo_root}")
    return repo_root


def configure_isolated_process(repo_root: Path) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(FIXTURE_DIR)
    os.environ.update(
        {
            "DATABASE_URL": DATABASE_URL,
            "WMS_DATA_DIR": str(FIXTURE_DIR / "data"),
            "JWT_SECRET_KEY": "wms429-local-fixture-only-not-a-production-secret",
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


def day_end(day: date, moscow: object) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, moscow) - timedelta(microseconds=1)


async def seed() -> dict[str, int | str]:
    from app.db.session import SessionLocal, engine
    from app.models.billing import BillingLedgerEntry, BillingTariffVersionV2
    from app.models.product import Product
    from app.models.product_dimension_event import ProductDimensionEvent
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.warehouse import Warehouse
    from app.services.storage_daily_charge_service import storage_day_event_kind, storage_day_source_id
    from app.services.storage_measurement_service import MOSCOW
    from sqlalchemy import func, select

    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        if tenant is None:
            raise RuntimeError("local_fixture_not_seeded")
        seller = await session.scalar(
            select(Seller).where(Seller.tenant_id == tenant.id, Seller.name == SELLER_NAME)
        )
        warehouse = await session.scalar(
            select(Warehouse).where(
                Warehouse.tenant_id == tenant.id,
                Warehouse.code == WAREHOUSE_CODE,
            )
        )
        if seller is None or warehouse is None:
            raise RuntimeError("local_fixture_identity_missing")

        existing_count = int(
            await session.scalar(
                select(func.count())
                .select_from(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant.id,
                    BillingLedgerEntry.source == SOURCE,
                )
            )
            or 0
        )
        if existing_count:
            await engine.dispose()
            return {"status": "already_seeded", "fixture_charge_rows": existing_count}

        products: dict[str, Product] = {}
        for sku, name, category, barcode, volume in [
            ("WMS430-STORAGE-A", "Учебное хранение A", "Учебное хранение: A", "430100000001", 2.0),
            ("WMS430-STORAGE-B", "Учебное хранение B", "Учебное хранение: B", "430100000002", 1.0),
        ]:
            product = await session.scalar(
                select(Product).where(
                    Product.tenant_id == tenant.id,
                    Product.seller_id == seller.id,
                    Product.sku_code == sku,
                )
            )
            if product is None:
                product = Product(
                    tenant_id=tenant.id,
                    seller_id=seller.id,
                    name=name,
                    sku_code=sku,
                    category=category,
                    wb_vendor_code=sku,
                    wb_barcode=barcode,
                    volume_liters=volume,
                )
                session.add(product)
                await session.flush()
                session.add(
                    ProductDimensionEvent(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        source="wms430_storage_fixture",
                        observed_at=datetime(2026, 9, 7, 12, tzinfo=UTC),
                        volume_liters=Decimal(str(volume)),
                        applied=True,
                        fingerprint=f"wms430-storage-{sku}",
                    )
                )
            products[sku] = product

        first_rate = BillingTariffVersionV2(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=None,
            employee_user_id=None,
            service_code="storage",
            unit="liter_day",
            enabled=True,
            rate=100,
            valid_from_at=datetime(2026, 9, 1, tzinfo=MOSCOW),
            valid_to_at=datetime(2026, 9, 9, tzinfo=MOSCOW),
        )
        second_rate = BillingTariffVersionV2(
            tenant_id=tenant.id,
            seller_id=seller.id,
            product_id=None,
            employee_user_id=None,
            service_code="storage",
            unit="liter_day",
            enabled=True,
            rate=200,
            valid_from_at=datetime(2026, 9, 9, tzinfo=MOSCOW),
            valid_to_at=None,
        )
        session.add_all([first_rate, second_rate])
        await session.flush()

        for day, rate, tariff in [(DAY_ONE, 100, first_rate), (DAY_TWO, 200, second_rate)]:
            for sku, quantity in [("WMS430-STORAGE-A", Decimal("2.0000")), ("WMS430-STORAGE-B", Decimal("1.0000"))]:
                product = products[sku]
                session.add(
                    BillingLedgerEntry(
                        tenant_id=tenant.id,
                        seller_id=seller.id,
                        warehouse_id=warehouse.id,
                        tariff_version_v2_id=tariff.id,
                        entry_type="charge",
                        service_code="storage",
                        source=SOURCE,
                        source_type=SOURCE_TYPE,
                        source_id=storage_day_source_id(
                            warehouse_id=warehouse.id,
                            product_id=product.id,
                        ),
                        event_kind=storage_day_event_kind(day),
                        unit="liter_day",
                        quantity=quantity,
                        rate=rate,
                        amount=int(quantity * rate),
                        occurred_at=day_end(day, MOSCOW).astimezone(UTC),
                    )
                )
        await session.commit()

        fixture_count, liter_days, amount = (
            await session.execute(
                select(
                    func.count(BillingLedgerEntry.id),
                    func.sum(BillingLedgerEntry.quantity),
                    func.sum(BillingLedgerEntry.amount),
                ).where(
                    BillingLedgerEntry.tenant_id == tenant.id,
                    BillingLedgerEntry.source == SOURCE,
                )
            )
        ).one()
    await engine.dispose()
    return {
        "status": "seeded",
        "fixture_charge_rows": int(fixture_count),
        "fixture_liter_days": str(liter_days),
        "fixture_amount_kopecks": int(amount),
    }


def main() -> None:
    repo_root = parse_repo_root()
    configure_isolated_process(repo_root)
    print(json.dumps(asyncio.run(seed()), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
