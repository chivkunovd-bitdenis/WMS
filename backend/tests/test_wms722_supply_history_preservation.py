"""History left by detached orders survives deletion of the now-empty card."""

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProductPick
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services.fbs_packaging_integration_service import detach_cancelled_order_from_supply
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks
from app.services.fbs_stock_sync_service import drain_zero_publish_background_tasks
from tests.fbs_supply_card_fixture import seed, snapshot
from tests.test_fbs_picking import _scan_location, _scan_product


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_empty_card_deletion_retains_picking_history_and_movements(async_client, marketplace):
    headers, tenant, supply, orders = await seed(async_client, marketplace, count=1)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, orders[0])
        balance = (await session.scalars(select(InventoryBalance).where(
            InventoryBalance.product_id == order.product_id,
            InventoryBalance.quantity_unpacked > 0,
        ))).one()
        location = await session.get(StorageLocation, balance.storage_location_id)
        location_id, code, barcode = location.id, location.code, order.wb_barcode
    response = await _scan_location(async_client, headers, supply, code)
    assert response.status_code == 200, response.text
    response = await _scan_product(
        async_client, headers, supply, location_id=location_id,
        barcode=barcode, idempotency_key=str(uuid.uuid4()),
    )
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, orders[0])
        order.status = "cancelled"
        await detach_cancelled_order_from_supply(session, tenant, order, actor_user_id=None)
        await session.commit()
        model = FbsOrderPick if marketplace == "wb" else FbsOrderProductPick
        history_table = model.__table__
        history = [
            dict(row._mapping) for row in (await session.execute(select(history_table))).all()
        ]
        assert history
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    before = await snapshot(exclude=("fbs_supplies", history_table.name))
    response = await async_client.delete(f"/operations/fbs-supplies/{supply}", headers=headers)
    assert response.status_code == 204, response.text
    assert await snapshot(exclude=("fbs_supplies", history_table.name)) == before
    async with SessionLocal() as session:
        after = [dict(row._mapping) for row in (await session.execute(select(history_table))).all()]
    assert after == [{**row, "fbs_supply_id": None} for row in history]


def test_history_migration_retains_rows_under_enforced_foreign_keys():
    path = Path(__file__).parents[1] / "alembic/versions/20261009_0722_fbs_supply_history.py"
    spec = importlib.util.spec_from_file_location("supply_history_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    supplies = sa.Table("fbs_supplies", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    tables = []
    for name, column, ondelete in migration.REFERENCES:
        tables.append(sa.Table(
            name, metadata, sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(column, sa.Uuid(), sa.ForeignKey("fbs_supplies.id", ondelete=ondelete),
                      nullable=False),
        ))
    engine = sa.create_engine("sqlite://")
    supply = uuid.uuid4()
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(supplies.insert().values(id=supply))
        for table in tables:
            connection.execute(table.insert().values(id=uuid.uuid4(), **{table.c[1].name: supply}))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        connection.execute(supplies.delete())
        connection.commit()
        for table in tables:
            rows = connection.execute(sa.select(table)).all()
            assert len(rows) == 1 and rows[0][1] is None
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        with (
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match="detached history"),
        ):
            migration.downgrade()
    engine.dispose()
