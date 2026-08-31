"""WB operation journal must know who acted — TC-FBS-ACTOR-001..004.

Owner asked this after a supply that got closed and handed to delivery could
not be traced to an operator: the journal had "what" and "when" but no "who".
These tests cover the human-initiated paths (create supply from orders,
deliver) and the background path (no actor, must stay empty and not fail),
plus a migration round-trip for the new column.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import AsyncClient
from sqlalchemy import Connection, Engine, create_engine, inspect, select, text

from alembic import command
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    FbsWbOperation,
)
from app.services.fbs_supply_reconcile_service import (
    OPERATION_KIND_SUPPLY_DELIVER,
    OPERATION_KIND_SUPPLY_FROM_ORDERS,
    create_pending_operation,
    request_hash_for_from_orders,
)
from tests import test_fbs_shipment_warehouse_sc as deliver_helpers
from tests import test_fbs_supply_from_orders as from_orders_helpers


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    deliver_helpers._mock_actual_composition_from_local_links(monkeypatch)


# TC-FBS-ACTOR-001 — create supply from orders records who did it
@pytest.mark.asyncio
async def test_actor_recorded_for_supply_from_orders(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await from_orders_helpers._register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    user_id = uuid.UUID(me.json()["id"])
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    seller_id, warehouse_id, location_id = await from_orders_helpers._setup_seller_with_token(
        async_client, headers, suffix
    )
    product = await from_orders_helpers._create_product(
        async_client, headers, seller_id, sku=f"SKU-{suffix[-8:]}"
    )
    order_id = await from_orders_helpers._create_ready_order(
        tenant_id,
        uuid.UUID(seller_id),
        uuid.UUID(warehouse_id),
        uuid.UUID(location_id),
        product,
        order_id=970001,
    )

    created = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "Actor supply",
            "order_ids": [str(order_id)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    supply_id = uuid.UUID(created.json()["supply"]["id"])

    async with SessionLocal() as session:
        result = await session.execute(
            select(FbsWbOperation).where(
                FbsWbOperation.operation_kind == OPERATION_KIND_SUPPLY_FROM_ORDERS,
                FbsWbOperation.local_entity_id == supply_id,
            )
        )
        operation = result.scalar_one()
        assert operation.state == WB_OPERATION_STATE_CONFIRMED
        assert operation.created_by_user_id == user_id


# TC-FBS-ACTOR-002 — handing a supply to delivery records who did it, both
# via the warehouse/SC route (this test) and the pvz route (same code path,
# see _DELIVER_ALLOWED_DELIVERY_TYPES in fbs_shipment_service.py — deliver
# is a single function for both).
@pytest.mark.asyncio
async def test_actor_recorded_for_deliver(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await deliver_helpers._register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    user_id = uuid.UUID(me.json()["id"])

    seller_id, warehouse_id, tenant_id = await deliver_helpers._setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await deliver_helpers._prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[970002, 970003],
        supply_name="Actor deliver",
    )
    await deliver_helpers._create_and_fill_physical_box(
        async_client, headers, supply["id"], order_ids
    )

    deliver = await deliver_helpers._deliver_with_preflight(
        async_client, headers, supply["id"]
    )
    assert deliver.status_code == 200, deliver.text

    async with SessionLocal() as session:
        result = await session.execute(
            select(FbsWbOperation).where(
                FbsWbOperation.operation_kind == OPERATION_KIND_SUPPLY_DELIVER,
                FbsWbOperation.local_entity_id == uuid.UUID(supply["id"]),
            )
        )
        operation = result.scalar_one()
        assert operation.state == WB_OPERATION_STATE_CONFIRMED
        assert operation.created_by_user_id == user_id


# TC-FBS-ACTOR-003 — background reconciliation has no human actor: the field
# stays empty and the journal write does not fail. No system pseudo-user is
# ever substituted — that was explicitly ruled out by the owner.
@pytest.mark.asyncio
async def test_background_operation_has_no_actor(async_client: AsyncClient) -> None:
    headers, suffix = await from_orders_helpers._register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id, _warehouse_id, _location_id = await from_orders_helpers._setup_seller_with_token(
        async_client, headers, suffix
    )

    request_hash = request_hash_for_from_orders(
        name="Background op",
        order_ids=[],
        planned_delivery_type="warehouse_sc",
    )
    async with SessionLocal() as session:
        operation = await create_pending_operation(
            session,
            tenant_id=tenant_id,
            seller_id=uuid.UUID(seller_id),
            idempotency_key=str(uuid.uuid4()),
            request_hash=request_hash,
            request_summary={"source": "background_reconcile"},
        )
        await session.commit()
        operation_id = operation.id

    async with SessionLocal() as session:
        stored = await session.get(FbsWbOperation, operation_id)
        assert stored is not None
        assert stored.created_by_user_id is None


# TC-FBS-ACTOR-004 — migration 20260827_0104 adds the column additively and
# is reversible; mirrors tests/test_fbs_operator_flow_migration.py.
MIGRATION_BEFORE = "20260826_0103"
MIGRATION_UNDER_TEST = "20260827_0104"


def _alembic_config(sync_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


def _sync_database_url() -> str | None:
    url = os.environ.get("WMS_TEST_DATABASE_URL") or settings.database_url_sync
    if url.startswith("sqlite"):
        return None
    if url.startswith("postgresql+psycopg_async://"):
        return url.replace("postgresql+psycopg_async://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture(scope="module")
def pg_sync_url() -> str:
    url = _sync_database_url()
    if url is None:
        pytest.skip("PostgreSQL WMS_TEST_DATABASE_URL required for alembic round-trip")
    return url


@pytest.fixture(scope="module")
def pg_engine(pg_sync_url: str) -> Engine:
    engine = create_engine(pg_sync_url, future=True)
    yield engine
    engine.dispose()


def test_migration_0104_adds_created_by_user_id_column(
    pg_engine: Engine, pg_sync_url: str
) -> None:
    cfg = _alembic_config(pg_sync_url)

    with pg_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    command.upgrade(cfg, MIGRATION_BEFORE)

    with pg_engine.connect() as conn:
        inspector: Connection = inspect(conn)
        columns_before = {
            col["name"] for col in inspector.get_columns("fbs_wb_operations")
        }
        assert "created_by_user_id" not in columns_before

    command.upgrade(cfg, MIGRATION_UNDER_TEST)

    with pg_engine.connect() as conn:
        inspector = inspect(conn)
        columns_after = {col["name"] for col in inspector.get_columns("fbs_wb_operations")}
        assert "created_by_user_id" in columns_after
        fk_names = {
            fk["name"] for fk in inspector.get_foreign_keys("fbs_wb_operations")
        }
        assert "fk_fbs_wb_operations_created_by_user" in fk_names

    command.downgrade(cfg, MIGRATION_BEFORE)

    with pg_engine.connect() as conn:
        inspector = inspect(conn)
        columns_rolled_back = {
            col["name"] for col in inspector.get_columns("fbs_wb_operations")
        }
        assert "created_by_user_id" not in columns_rolled_back

    command.upgrade(cfg, MIGRATION_UNDER_TEST)
