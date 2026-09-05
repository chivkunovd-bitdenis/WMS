"""WMS-355: boxes hold whole posting positions and freeze after Ozon assembly."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBoxItem
from app.services import fbs_packing_box_service as boxes_svc
from app.services.fbs_workspace_service import _unassigned_order_ids
from tests.test_fbs_ozon_lane import _ozon_supply_with_one_order


async def _positions(session: AsyncSession, order: FbsOrder) -> list[FbsOrderProduct]:
    positions = [
        FbsOrderProduct(
            order_id=order.id,
            position_index=index,
            ozon_sku=100 + index,
            quantity=quantity,
            name=f"Position {index}",
        )
        for index, quantity in enumerate([3, 5])
    ]
    session.add_all(positions)
    await session.flush()
    return positions


@pytest.mark.asyncio
async def test_whole_positions_distribute_independently_and_readiness_requires_every_position(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    boxes = await boxes_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        2,
        "positions",
        actor_user_id=None,
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[positions[0].id],
    )
    readiness = await boxes_svc.get_delivery_box_readiness(
        db_session,
        tenant.id,
        supply.id,
        [order],
    )
    assert readiness.unassigned_packed_order_ids == {order.id}
    workspace_boxes = await boxes_svc.get_boxes_for_workspace(db_session, tenant.id, supply.id)
    worklist: list[dict[str, Any]] = [
        {
            "id": str(order.id),
            "positions": [{"id": str(position.id)} for position in positions],
        }
    ]
    assert _unassigned_order_ids(supply, [order], workspace_boxes, worklist) == {order.id}
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[1].id,
        [],
        actor_user_id=None,
        order_product_ids=[positions[1].id],
    )
    # Repeating the exact assignment is safe; quantity is read only from its position.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[1].id,
        [],
        actor_user_id=None,
        order_product_ids=[positions[1].id],
    )
    readiness = await boxes_svc.get_delivery_box_readiness(
        db_session, tenant.id, supply.id, [order]
    )
    assert readiness.unassigned_packed_order_ids == set()
    workspace_boxes = await boxes_svc.get_boxes_for_workspace(db_session, tenant.id, supply.id)
    assert _unassigned_order_ids(supply, [order], workspace_boxes, worklist) == set()
    items = list(
        (
            await db_session.scalars(
                select(FbsPackingBoxItem).where(
                    FbsPackingBoxItem.fbs_order_id == order.id,
                )
            )
        ).all()
    )
    assert {item.order_product_id for item in items} == {position.id for position in positions}
    assert [position.quantity for position in positions] == [3, 5]
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="order_already_in_box"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[1].id,
            [],
            actor_user_id=None,
            order_product_ids=[positions[0].id],
        )
    await boxes_svc.remove_order(
        db_session,
        tenant.id,
        supply.id,
        boxes[1].id,
        order.id,
        order_product_id=positions[1].id,
    )
    readiness = await boxes_svc.get_delivery_box_readiness(
        db_session, tenant.id, supply.id, [order]
    )
    assert readiness.unassigned_packed_order_ids == {order.id}


@pytest.mark.asyncio
async def test_ozon_box_rejects_other_orders_and_positions_outside_its_supply(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    other = FbsOrder(
        tenant_id=tenant.id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        supply_id=supply.id,
        marketplace="ozon",
        external_order_id="other-posting",
        mapping_status="mapped",
        reserve_status="reserved",
        wb_order_id=1002,
        wb_warehouse_id=11,
        created_at_wb=order.created_at_wb,
        deadline_at=order.deadline_at,
    )
    db_session.add(other)
    await db_session.flush()
    other_positions = await _positions(db_session, other)
    boxes = await boxes_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        1,
        "one-order",
        actor_user_id=None,
    )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="order_not_in_supply"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            order_product_ids=[positions[0].id, uuid.uuid4()],
        )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_multiple_orders"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            order_product_ids=[positions[0].id, other_positions[0].id],
        )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[positions[0].id],
    )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_multiple_orders"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            order_product_ids=[other_positions[0].id],
        )


@pytest.mark.asyncio
async def test_assembled_ozon_order_freezes_all_box_membership(db_session: AsyncSession) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    boxes = await boxes_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        1,
        "assembled",
        actor_user_id=None,
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[position.id for position in positions],
    )
    order.meta_details_json = {"ozon_assembly": {"posting_numbers": ["assembled-posting"]}}
    await db_session.flush()
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            order_product_ids=[positions[0].id],
        )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        await boxes_svc.remove_order(db_session, tenant.id, supply.id, boxes[0].id, order.id)
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        await boxes_svc.clear_box(db_session, tenant.id, supply.id, boxes[0].id)


@pytest.mark.asyncio
async def test_database_prevents_duplicate_whole_position_assignments(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    boxes = await boxes_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        2,
        "unique-position",
        actor_user_id=None,
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[positions[0].id],
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                FbsPackingBoxItem(
                    tenant_id=tenant.id,
                    box_id=boxes[1].id,
                    fbs_order_id=order.id,
                    order_product_id=positions[0].id,
                )
            )
            await db_session.flush()


def test_migration_preserves_wb_uniqueness_and_allows_distinct_ozon_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/20260905_0254_fbs_box_order_positions.py"
    )
    spec = spec_from_file_location("box_positions_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    sa.Table("fbs_order_products", metadata, sa.Column("id", sa.Uuid(), primary_key=True))
    sa.Table(
        "fbs_supplies",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("marketplace", sa.String()),
        sa.Column("boxes_without_distribution_at", sa.DateTime()),
        sa.Column("boxes_without_distribution_by_user_id", sa.Uuid()),
    )
    items = sa.Table(
        "fbs_packing_box_items",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fbs_order_id", sa.Uuid(), nullable=False),
        sa.UniqueConstraint("fbs_order_id", name="uq_fbs_packing_box_items_order"),
    )
    engine = sa.create_engine("sqlite://")
    wb_order_id, ozon_order_id = uuid.uuid4(), uuid.uuid4()
    first_position_id, second_position_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            metadata.tables["fbs_order_products"].insert(),
            [
                {"id": first_position_id},
                {"id": second_position_id},
            ],
        )
        connection.execute(items.insert().values(id=1, fbs_order_id=wb_order_id))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        upgraded = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        assert "order_product_id" in upgraded.c
        assert "quantity" not in upgraded.c
        # Reflection reports UUID affinity as text on SQLite.
        with pytest.raises(IntegrityError):
            connection.execute(upgraded.insert().values(id=2, fbs_order_id=wb_order_id.hex))
        connection.execute(
            upgraded.insert(),
            [
                {
                    "id": 3,
                    "fbs_order_id": ozon_order_id.hex,
                    "order_product_id": first_position_id.hex,
                },
                {
                    "id": 4,
                    "fbs_order_id": ozon_order_id.hex,
                    "order_product_id": second_position_id.hex,
                },
            ],
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                upgraded.insert().values(
                    id=5,
                    fbs_order_id=ozon_order_id.hex,
                    order_product_id=first_position_id.hex,
                )
            )
        with pytest.raises(RuntimeError, match="Remove position assignments"):
            migration.downgrade()
        connection.execute(upgraded.delete().where(upgraded.c.id == 4))
        migration.downgrade()
        restored = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        assert "order_product_id" not in restored.c
        assert connection.scalar(sa.select(sa.func.count()).select_from(restored)) == 2
        with pytest.raises(IntegrityError):
            connection.execute(restored.insert().values(id=6, fbs_order_id=ozon_order_id.hex))
    engine.dispose()
