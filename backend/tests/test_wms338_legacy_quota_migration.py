"""Apply the real retirement migration to an isolated old-schema PostgreSQL fixture."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.inventory_balance import InventoryBalance
from app.models.stock_direction import StockDirection
from tests.test_inventory_stock_cap_wms338 import OPERATOR_CAP, _fbs_order, _seed


@pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="real PostgreSQL migration required"
)
async def test_retire_legacy_schema_preserves_cap_balance_and_ordinary_direction(
    db_session: AsyncSession,
) -> None:
    path = Path(__file__).parents[1] / "alembic/versions/20260910_0261_remove_legacy_fbs_quota.py"
    spec = importlib.util.spec_from_file_location("retire_legacy_quota", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    scen = await _seed(db_session, on_hand=10)
    order = _fbs_order(scen, wb_order_id=3380261)
    direction = StockDirection(
        tenant_id=scen.tenant.id, product_id=scen.product.id, name="Ordinary reserve", quantity=2
    )
    db_session.add_all([order, direction])
    await db_session.flush()

    def replay(connection: Any) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()  # Build the real prior schema, no mocked DDL.
            connection.execute(
                text("""INSERT INTO fbs_stock_pool_debits
                (id, tenant_id, pool_id, order_id, quantity_debited)
                VALUES (:id, :tenant, :pool, :order, 3)"""),
                {
                    "id": uuid.uuid4(),
                    "tenant": scen.tenant.id,
                    "pool": scen.pool.id,
                    "order": order.id,
                },
            )
            connection.execute(text("UPDATE stock_directions SET is_fbs = true"))
            with pytest.raises(RuntimeError, match="explicit data decision"):
                migration.upgrade()
            assert connection.scalar(text("SELECT count(*) FROM fbs_stock_pool_debits")) == 1
            connection.execute(text("UPDATE stock_directions SET is_fbs = false"))
            migration.upgrade()
        schema = inspect(connection)
        assert "fbs_stock_pool_debits" not in schema.get_table_names()
        assert "is_fbs" not in {col["name"] for col in schema.get_columns("stock_directions")}

    await (await db_session.connection()).run_sync(replay)
    assert await db_session.scalar(select(FbsBindingStockPool.quantity)) == OPERATOR_CAP
    assert await db_session.scalar(select(InventoryBalance.quantity)) == 10
    assert await db_session.scalar(select(StockDirection.quantity)) == 2
