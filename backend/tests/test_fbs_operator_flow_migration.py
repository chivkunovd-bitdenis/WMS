"""Alembic round-trip for FBSFLOW-010 migration 0069."""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, inspect, text

from alembic import command
from app.core.settings import settings

MIGRATION_0068 = "20260802_0068"
MIGRATION_0069 = "20260803_0069"


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
def pg_engine(pg_sync_url: str) -> Generator[Engine, None, None]:
    engine = create_engine(pg_sync_url, future=True)
    yield engine
    engine.dispose()


def _seed_legacy_fbs_order(conn: Connection) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    order_id = uuid.uuid4()
    now = datetime.now(UTC)
    conn.execute(
        text(
            """
            INSERT INTO tenants (id, name, slug, created_at)
            VALUES (:tenant_id, 'Mig Tenant', :slug, :now)
            """
        ),
        {"tenant_id": tenant_id, "slug": f"mig-{tenant_id.hex[:8]}", "now": now},
    )
    conn.execute(
        text(
            """
            INSERT INTO sellers (id, tenant_id, name, created_at)
            VALUES (:seller_id, :tenant_id, 'Mig Seller', :now)
            """
        ),
        {"seller_id": seller_id, "tenant_id": tenant_id, "now": now},
    )
    conn.execute(
        text(
            """
            INSERT INTO fbs_orders (
                id, tenant_id, seller_id, wb_order_id, created_at_wb, deadline_at,
                mapping_status, reserve_status, status, is_legal, can_pvz,
                sticker_file, created_at, updated_at
            )
            VALUES (
                :order_id, :tenant_id, :seller_id, 900100, :created_at_wb, :deadline_at,
                'missing', 'warehouse_unmapped', 'new', false, false,
                '/legacy/sticker.png', :now, :now
            )
            """
        ),
        {
            "order_id": order_id,
            "tenant_id": tenant_id,
            "seller_id": seller_id,
            "created_at_wb": now,
            "deadline_at": now + timedelta(hours=24),
            "now": now,
        },
    )
    conn.commit()
    return order_id


def test_migration_0069_upgrade_downgrade_upgrade(
    pg_engine: Engine, pg_sync_url: str
) -> None:
    """0069: upgrade from 0068 → downgrade → upgrade; legacy rows survive backfill."""
    cfg = _alembic_config(pg_sync_url)

    with pg_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    command.upgrade(cfg, MIGRATION_0068)

    order_id = None
    with pg_engine.connect() as conn:
        order_id = _seed_legacy_fbs_order(conn)

    command.upgrade(cfg, MIGRATION_0069)

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT pick_status, pack_status, sticker_status, sticker_file
                FROM fbs_orders WHERE id = :order_id
                """
            ),
            {"order_id": order_id},
        ).one()
        assert row.pick_status == "pending"
        assert row.pack_status == "pending"
        assert row.sticker_status == "ready"
        assert row.sticker_file == "/legacy/sticker.png"

        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        assert "fbs_order_picks" in tables
        assert "fbs_print_assets" in tables
        assert "fbs_wb_operations" in tables
        assert "fbs_packaging_fulfillments" in tables

    command.downgrade(cfg, MIGRATION_0068)

    with pg_engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        assert "fbs_order_picks" not in tables
        assert "fbs_print_assets" not in tables

        row = conn.execute(
            text(
                """
                SELECT sticker_file FROM fbs_orders WHERE id = :order_id
                """
            ),
            {"order_id": order_id},
        ).one()
        assert row.sticker_file == "/legacy/sticker.png"

    command.upgrade(cfg, MIGRATION_0069)

    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT pick_status, sticker_status FROM fbs_orders WHERE id = :order_id
                """
            ),
            {"order_id": order_id},
        ).one()
        assert row.pick_status == "pending"
        assert row.sticker_status == "ready"
