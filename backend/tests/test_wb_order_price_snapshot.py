"""WMS-517 BR2: WB evidence, exact kopecks, immutable history and bounded backfill."""

from __future__ import annotations

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.wb_order_price_snapshot import WbOrderPriceSnapshot
from app.services import wb_marketplace_orders_service as orders
from app.services.wb_order_price_service import (
    CRPT_MAX_PRODUCT_COST,
    WB_NEW_ORDERS_SOURCE,
    WB_ORDERS_SOURCE,
    WbPriceDataError,
    capture_wb_price_snapshot,
    product_cost_from_snapshot,
    resolve_wb_product_cost,
)


@pytest.mark.parametrize(("fields", "expected"), [
    ({"final_price": 12345, "currency_code": 643}, 12345),
    ({"final_price": 0, "currency_code": 643}, 0),
    ({"final_price": CRPT_MAX_PRODUCT_COST, "currency_code": 643}, CRPT_MAX_PRODUCT_COST),
    ({"final_price": 555, "currency_code": 840,
      "converted_final_price": 12345, "converted_currency_code": 643}, 12345),
    ({"converted_final_price": 12345, "converted_currency_code": 643}, 12345),
    ({"final_price": 12345, "currency_code": 643,
      "converted_final_price": 12345, "converted_currency_code": 643}, 12345),
])
def test_exact_rub_kopecks(fields: dict[str, Any], expected: int) -> None:
    snapshot = WbOrderPriceSnapshot(id=uuid.uuid4(), **fields)
    resolved = product_cost_from_snapshot(snapshot)
    assert resolved.product_cost == expected
    assert resolved.snapshot_id == snapshot.id


@pytest.mark.parametrize(("fields", "code"), [
    ({}, "missing_rub_final_price"),
    ({"final_price": 12345, "currency_code": 840}, "missing_rub_final_price"),
    ({"final_price": 12345, "currency_code": "643"}, "missing_rub_final_price"),
    ({"final_price": None, "currency_code": 643,
      "converted_final_price": 12345, "converted_currency_code": 643}, "missing_rub_final_price"),
    ({"final_price": -1, "currency_code": 643}, "rub_price_out_of_range"),
    ({"final_price": CRPT_MAX_PRODUCT_COST + 1, "currency_code": 643}, "rub_price_out_of_range"),
    ({"final_price": 12.5, "currency_code": 643}, "invalid_rub_price"),
    ({"final_price": True, "currency_code": 643}, "invalid_rub_price"),
    ({"final_price": "12345", "currency_code": 643}, "invalid_rub_price"),
    ({"final_price": 12345, "currency_code": 643,
      "converted_final_price": 12346, "converted_currency_code": 643}, "conflicting_rub_prices"),
    ({"final_price": 12345, "currency_code": 643,
      "converted_final_price": -1, "converted_currency_code": 643}, "rub_price_out_of_range"),
])
def test_invalid_price_is_a_typed_error(fields: dict[str, Any], code: str) -> None:
    snapshot = WbOrderPriceSnapshot(id=uuid.uuid4(), **fields)
    with pytest.raises(WbPriceDataError) as error:
        product_cost_from_snapshot(snapshot)
    assert error.value.code == code
    assert error.value.snapshot_id == snapshot.id


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant = Tenant(name="price", slug=f"price-{uuid.uuid4().hex}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="price seller")
    session.add(seller)
    await session.flush()
    return tenant.id, seller.id


def _row(order_id: int = 517) -> dict[str, Any]:
    return {"id": order_id, "createdAt": datetime.now(UTC).isoformat(), "price": 99999,
            "finalPrice": 12345, "currencyCode": 643,
            "convertedFinalPrice": 12345, "convertedCurrencyCode": 643}


async def test_import_update_persists_versions_and_deduplicates(db_session: AsyncSession) -> None:
    tenant, seller = await _seed(db_session)
    row = _row()
    order, created = await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
    )
    assert created
    first = await resolve_wb_product_cost(
        db_session, tenant_id=tenant, seller_id=seller, order_id=order.id,
    )
    assert first.product_cost == 12345 and order.price == 99999
    await db_session.commit()
    await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
    )
    assert await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) == 1
    row["finalPrice"] = row["convertedFinalPrice"] = 14001
    await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
    )
    await db_session.commit()
    db_session.expunge_all()
    history = (await db_session.scalars(select(WbOrderPriceSnapshot).order_by(
        WbOrderPriceSnapshot.revision,
    ))).all()
    assert [(s.revision, s.final_price) for s in history] == [(1, 12345), (2, 14001)]
    assert history[0].id == first.snapshot_id
    assert all(s.source == WB_ORDERS_SOURCE and s.received_at is not None for s in history)
    assert (await resolve_wb_product_cost(
        db_session, tenant_id=tenant, seller_id=seller, order_id=history[0].order_id,
    )).product_cost == 14001
    # ORM protects old evidence, in addition to the production PostgreSQL trigger.
    history[0].final_price = 9
    with pytest.raises(ValueError, match="wb_price_snapshot_is_immutable"):
        await db_session.flush()
    await db_session.rollback()


async def test_orm_cannot_delete_snapshot(db_session: AsyncSession) -> None:
    tenant, seller = await _seed(db_session)
    await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, _row(), preserve_unmapped_warehouse=True,
    )
    await db_session.commit()
    snapshot = await db_session.scalar(select(WbOrderPriceSnapshot))
    assert snapshot is not None
    snapshot_id = snapshot.id
    await db_session.delete(snapshot)
    with pytest.raises(ValueError, match="wb_price_snapshot_is_immutable"):
        await db_session.flush()
    await db_session.rollback()
    assert await db_session.get(WbOrderPriceSnapshot, snapshot_id) is not None


def test_migrated_database_retains_snapshot_and_parent_until_downgrade() -> None:
    migration_path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/20260923_0517_wb_price_snapshots.py"
    )
    spec = importlib.util.spec_from_file_location("wb_price_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(text("CREATE TABLE fbs_orders (id UUID PRIMARY KEY)"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            connection.execute(text("INSERT INTO fbs_orders (id) VALUES ('order')"))
            connection.execute(text("""
                INSERT INTO wb_order_price_snapshots
                    (id, order_id, revision, final_price, currency_code, source, received_at)
                VALUES ('snapshot', 'order', 1, '12345', '643', '/api/v3/orders', CURRENT_TIMESTAMP)
            """))
            connection.commit()
            for statement, error in (
                ("DELETE FROM wb_order_price_snapshots", "wb_price_snapshot_is_immutable"),
                ("UPDATE wb_order_price_snapshots SET final_price='9'",
                 "wb_price_snapshot_is_immutable"),
                ("DELETE FROM fbs_orders", "FOREIGN KEY constraint failed"),
            ):
                with pytest.raises(IntegrityError, match=error):
                    connection.execute(text(statement))
                connection.rollback()
                assert connection.scalar(text("SELECT COUNT(*) FROM wb_order_price_snapshots")) == 1
                assert connection.scalar(text("SELECT COUNT(*) FROM fbs_orders")) == 1
            fk = inspect(connection).get_foreign_keys("wb_order_price_snapshots")[0]
            assert fk["options"]["ondelete"] == "RESTRICT"
            model_fk = next(iter(WbOrderPriceSnapshot.__table__.c.order_id.foreign_keys))
            assert model_fk.ondelete == "RESTRICT"
            # DDL rollback is deliberate: it can remove the retained data without DML triggers.
            migration.downgrade()
            assert "wb_order_price_snapshots" not in inspect(connection).get_table_names()
            assert connection.scalar(text("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='trigger' AND name LIKE 'wb_price_snapshot_%'
            """)) == 0
    finally:
        engine.dispose()


async def test_missing_and_bad_fields_never_use_legacy_price(db_session: AsyncSession) -> None:
    tenant, seller = await _seed(db_session)
    row = _row()
    order, _ = await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
    )
    order_id = order.id
    for value, code in [(None, "missing_rub_final_price"),
                        (10**30, "rub_price_out_of_range"), (12.5, "invalid_rub_price")]:
        row["finalPrice"] = row["convertedFinalPrice"] = value
        await orders.upsert_order_from_wb_row(
            db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
        )
        await db_session.commit()
        db_session.expire_all()
        with pytest.raises(WbPriceDataError) as error:
            await resolve_wb_product_cost(
                db_session, tenant_id=tenant, seller_id=seller, order_id=order_id,
            )
        assert error.value.code == code


async def test_partial_new_feed_preserves_snapshot_and_scope(db_session: AsyncSession) -> None:
    tenant, seller = await _seed(db_session)
    order, _ = await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, _row(), preserve_unmapped_warehouse=True,
    )
    for other_tenant, other_seller in [(uuid.uuid4(), seller), (tenant, uuid.uuid4())]:
        with pytest.raises(WbPriceDataError, match="снимок финальной цены отсутствует"):
            await resolve_wb_product_cost(
                db_session, tenant_id=other_tenant, seller_id=other_seller, order_id=order.id,
            )
        with pytest.raises(WbPriceDataError, match="WB-заказ не найден"):
            await capture_wb_price_snapshot(
                db_session, tenant_id=other_tenant, seller_id=other_seller,
                order_id=order.id, row=_row(),
            )
    await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, {"id": 517, "price": 50000},
        preserve_unmapped_warehouse=True, price_source=WB_NEW_ORDERS_SOURCE,
    )
    assert await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) == 1
    assert (await resolve_wb_product_cost(
        db_session, tenant_id=tenant, seller_id=seller, order_id=order.id,
    )).product_cost == 12345


@pytest.mark.parametrize(("fields", "expected", "error_code"), [
    ({"finalPrice": CRPT_MAX_PRODUCT_COST, "currencyCode": 643}, CRPT_MAX_PRODUCT_COST, None),
    ({"finalPrice": 0, "currencyCode": 643}, 0, None),
    ({"finalPrice": 200, "currencyCode": 840,
      "convertedFinalPrice": 16005, "convertedCurrencyCode": 643}, 16005, None),
    ({"finalPrice": 200, "currencyCode": 840}, None, "missing_rub_final_price"),
    ({"finalPrice": 100, "currencyCode": 643,
      "convertedFinalPrice": 101, "convertedCurrencyCode": 643}, None, "conflicting_rub_prices"),
])
async def test_imported_price_cases_survive_reload(
    db_session: AsyncSession, fields: dict[str, Any], expected: int | None, error_code: str | None,
) -> None:
    tenant, seller = await _seed(db_session)
    row = {"id": 517, "price": 99999, **fields}
    order, _ = await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, row, preserve_unmapped_warehouse=True,
    )
    order_id = order.id
    await db_session.commit()
    db_session.expunge_all()
    if error_code is not None:
        with pytest.raises(WbPriceDataError) as error:
            await resolve_wb_product_cost(
                db_session, tenant_id=tenant, seller_id=seller, order_id=order_id,
            )
        assert error.value.code == error_code
    else:
        assert (await resolve_wb_product_cost(
            db_session, tenant_id=tenant, seller_id=seller, order_id=order_id,
        )).product_cost == expected


@pytest.mark.postgresql_concurrency
async def test_concurrent_capture_serializes_one_revision(db_session: AsyncSession) -> None:
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks require isolated WMS_TEST_DATABASE_URL")
    tenant, seller = await _seed(db_session)
    order, _ = await orders.upsert_order_from_wb_row(
        db_session, tenant, seller, {"id": 517},
        preserve_unmapped_warehouse=True, price_source=WB_NEW_ORDERS_SOURCE,
    )
    order_id = order.id
    await db_session.commit()

    async def capture() -> uuid.UUID:
        async with AsyncSession(bind=db_session.bind) as session:
            snapshot = await capture_wb_price_snapshot(
                session, tenant_id=tenant, seller_id=seller, order_id=order_id, row=_row(),
            )
            assert snapshot is not None
            snapshot_id = snapshot.id
            await session.commit()
            return snapshot_id

    first, second = await asyncio.gather(capture(), capture())
    assert first == second
    assert await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) == 1


async def test_existing_orders_backfill_uses_real_paginated_30_day_feed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, seller = await _seed(db_session)
    ids = []
    for wb_id in [517, 518, 519]:
        order, _ = await orders.upsert_order_from_wb_row(
            db_session, tenant, seller, {"id": wb_id, "price": 99999},
            preserve_unmapped_warehouse=True, price_source=WB_NEW_ORDERS_SOURCE,
        )
        ids.append(order.id)
    await db_session.commit()
    assert await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) == 0
    monkeypatch.setattr(orders, "_resolve_marketplace_api_token", AsyncMock(return_value="test"))
    monkeypatch.setattr(orders, "sync_order_statuses", AsyncMock(return_value=0))
    monkeypatch.setattr(orders, "link_confirmed_orders_to_wb_supplies", AsyncMock(return_value={}))
    pages = []

    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/new"):
            return httpx.Response(200, json={"orders": []})
        assert request.url.path == "/api/v3/orders"
        date_from = int(request.url.params["dateFrom"])
        assert abs(date_from - int((datetime.now(UTC) - timedelta(days=30)).timestamp())) < 5
        cursor = int(request.url.params["next"])
        pages.append(cursor)
        if cursor == 0:
            return httpx.Response(200, json={"orders": [_row(517)], "next": 22})
        return httpx.Response(200, json={"orders": [_row(518)], "next": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        await orders.sync_seller_orders(db_session, tenant, seller, client)
        await orders.sync_seller_orders(db_session, tenant, seller, client)
    assert pages == [0, 22, 0, 22]
    assert await db_session.scalar(select(func.count(WbOrderPriceSnapshot.id))) == 2
    for order_id in ids[:2]:
        assert (await resolve_wb_product_cost(
            db_session, tenant_id=tenant, seller_id=seller, order_id=order_id,
        )).product_cost == 12345
    # Older/unreturned rows stay ineligible even though a legacy price is present.
    with pytest.raises(WbPriceDataError) as error:
        await resolve_wb_product_cost(
            db_session, tenant_id=tenant, seller_id=seller, order_id=ids[2],
        )
    assert error.value.code == "missing_price_snapshot"
