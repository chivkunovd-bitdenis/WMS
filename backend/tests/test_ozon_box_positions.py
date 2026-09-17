"""WMS-453 (and WMS-355 before it): an Ozon order position's quantity can be
split across any number of boxes, one order stays confined to one box, and a
box freezes once its order is assembled in Ozon."""

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


def _add(position_id: uuid.UUID, quantity: int) -> list[boxes_svc.OzonBoxPositionInput]:
    return [boxes_svc.OzonBoxPositionInput(order_product_id=position_id, quantity=quantity)]


@pytest.mark.asyncio
async def test_position_quantity_splits_across_boxes_and_readiness_requires_full_quantity(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    boxes = await boxes_svc.create_boxes(
        db_session,
        tenant.id,
        supply.id,
        3,
        "positions",
        actor_user_id=None,
    )
    # Position 0 (quantity 3) is split 1 + 2 across two different boxes —
    # the owner's "1кор=10, 2кор=10..." scenario, scaled down.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[0].id, 1),
        idempotency_key="split-1a",
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
            "positions": [
                {"id": str(position.id), "quantity": position.quantity} for position in positions
            ],
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
        positions=_add(positions[0].id, 2),
        idempotency_key="split-1b",
    )
    # Position 1 (quantity 5) goes whole into the third box, same as before WMS-453.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[2].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 5),
        idempotency_key="whole-2",
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
                select(FbsPackingBoxItem).where(FbsPackingBoxItem.fbs_order_id == order.id)
            )
        ).all()
    )
    by_box = {(item.box_id, item.order_product_id): item.quantity for item in items}
    assert by_box[(boxes[0].id, positions[0].id)] == 1
    assert by_box[(boxes[1].id, positions[0].id)] == 2
    assert by_box[(boxes[2].id, positions[1].id)] == 5
    # The order position's own quantity is never touched — the split lives
    # only in the box rows (AGENTS.md: no second independent counter).
    assert [position.quantity for position in positions] == [3, 5]


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
            positions=[
                boxes_svc.OzonBoxPositionInput(order_product_id=positions[0].id, quantity=1),
                boxes_svc.OzonBoxPositionInput(order_product_id=uuid.uuid4(), quantity=1),
            ],
            idempotency_key="foreign-position",
        )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_multiple_orders"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            positions=[
                boxes_svc.OzonBoxPositionInput(order_product_id=positions[0].id, quantity=1),
                boxes_svc.OzonBoxPositionInput(order_product_id=other_positions[0].id, quantity=1),
            ],
            idempotency_key="two-orders",
        )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[0].id, 3),
        idempotency_key="first-order",
    )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_multiple_orders"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            positions=_add(other_positions[0].id, 1),
            idempotency_key="second-order",
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
        positions=[
            boxes_svc.OzonBoxPositionInput(order_product_id=position.id, quantity=position.quantity)
            for position in positions
        ],
        idempotency_key="assemble-seed",
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
            positions=_add(positions[0].id, 1),
            idempotency_key="after-assembly",
        )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        await boxes_svc.remove_order(db_session, tenant.id, supply.id, boxes[0].id, order.id)
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        await boxes_svc.clear_box(db_session, tenant.id, supply.id, boxes[0].id)


@pytest.mark.asyncio
async def test_database_allows_same_position_in_different_boxes_but_not_twice_in_one_box(
    db_session: AsyncSession,
) -> None:
    """WMS-453 relaxed the old "one row per position" rule (WMS-355): a
    position may now repeat across different boxes, but the same box must
    never hold two rows for the same position — that's still a DB
    invariant, not just an application check."""
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
        positions=_add(positions[0].id, 1),
        idempotency_key="first-box",
    )
    # Same position, a different box: allowed now.
    db_session.add(
        FbsPackingBoxItem(
            tenant_id=tenant.id,
            box_id=boxes[1].id,
            fbs_order_id=order.id,
            order_product_id=positions[0].id,
            quantity=1,
        )
    )
    await db_session.flush()
    # Same position, same box a second time: still rejected by the DB.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                FbsPackingBoxItem(
                    tenant_id=tenant.id,
                    box_id=boxes[0].id,
                    fbs_order_id=order.id,
                    order_product_id=positions[0].id,
                    quantity=1,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_quantity_over_remainder_is_rejected_and_saves_nothing(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 2, "over-limit", actor_user_id=None
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[0].id, 2),
        idempotency_key="first-part",
    )
    # Remainder of position 0 is 1; asking for 2 more must be rejected whole,
    # not reduced to whatever still fits.
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_quantity_exceeded"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[1].id,
            [],
            actor_user_id=None,
            positions=_add(positions[0].id, 2),
            idempotency_key="second-part",
        )
    items = list(
        (
            await db_session.scalars(
                select(FbsPackingBoxItem).where(
                    FbsPackingBoxItem.box_id == boxes[1].id,
                )
            )
        ).all()
    )
    assert items == []
    # Exactly the remainder still fits.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[1].id,
        [],
        actor_user_id=None,
        positions=_add(positions[0].id, 1),
        idempotency_key="second-part-exact",
    )
    readiness = await boxes_svc.get_delivery_box_readiness(
        db_session, tenant.id, supply.id, [order]
    )
    # Position 1 (quantity 5) is still fully unassigned, so the order stays
    # unready overall — only position 0 is complete now.
    assert readiness.unassigned_packed_order_ids == {order.id}


@pytest.mark.asyncio
async def test_repeat_idempotency_key_is_a_no_op_and_new_key_adds_to_existing_row(
    db_session: AsyncSession,
) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "idempotency", actor_user_id=None
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 3),
        idempotency_key="retry-key",
    )
    # A lost-response retry with the exact same key must not double the
    # quantity in the box (R6, B05/B09 — a repeated request is not a new
    # action).
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 3),
        idempotency_key="retry-key",
    )
    item = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.box_id == boxes[0].id,
            FbsPackingBoxItem.order_product_id == positions[1].id,
        )
    )
    assert item is not None and item.quantity == 3

    # Reopening the modal and deliberately adding the same position again,
    # under a new key, is a genuine second action and sums into the row.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 2),
        idempotency_key="deliberate-second-add",
    )
    await db_session.refresh(item)
    assert item.quantity == 5
    only_row = list(
        (
            await db_session.scalars(
                select(FbsPackingBoxItem).where(
                    FbsPackingBoxItem.box_id == boxes[0].id,
                    FbsPackingBoxItem.order_product_id == positions[1].id,
                )
            )
        ).all()
    )
    assert len(only_row) == 1


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_rejected(db_session: AsyncSession) -> None:
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "no-key", actor_user_id=None
    )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="missing_idempotency_key"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            positions=_add(positions[0].id, 1),
            idempotency_key=None,
        )


def test_migration_backfills_quantity_and_builds_new_partial_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/20260917_0500_wms453_ozon_box_quantity.py"
    )
    spec = spec_from_file_location("box_quantity_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    order_products = sa.Table(
        "fbs_order_products",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )
    items = sa.Table(
        "fbs_packing_box_items",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("fbs_order_id", sa.Uuid(), nullable=False),
        sa.Column("order_product_id", sa.Uuid(), nullable=True),
    )
    engine = sa.create_engine("sqlite://")
    wb_order_id, ozon_order_id = uuid.uuid4(), uuid.uuid4()
    wb_box_id, ozon_box_1, ozon_box_2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    position_id = uuid.uuid4()
    with engine.begin() as connection:
        metadata.create_all(connection)
        # Mirror the index migration 0254 already created — 0500 (this
        # migration) expects it present so it can drop and replace it.
        connection.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_fbs_packing_box_items_order_position "
                "ON fbs_packing_box_items (fbs_order_id, "
                "coalesce(order_product_id, '00000000-0000-0000-0000-000000000000'))"
            )
        )
        connection.execute(order_products.insert().values(id=position_id, quantity=7))
        connection.execute(
            items.insert(),
            [
                {
                    "id": 1,
                    "box_id": wb_box_id,
                    "fbs_order_id": wb_order_id,
                    "order_product_id": None,
                },
                {
                    "id": 2,
                    "box_id": ozon_box_1,
                    "fbs_order_id": ozon_order_id,
                    "order_product_id": position_id,
                },
            ],
        )
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        upgraded = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        assert "quantity" in upgraded.c
        assert "last_idempotency_key" in upgraded.c
        rows = {
            row.id: row.quantity
            for row in connection.execute(sa.select(upgraded.c.id, upgraded.c.quantity))
        }
        # WB row backfilled to 1; the Ozon row backfilled to its whole
        # position quantity (old rule: one row held the whole position).
        assert rows == {1: 1, 2: 7}

        # A second WB row for the same order is still rejected (WB never
        # splits across boxes).
        with pytest.raises(IntegrityError):
            connection.execute(
                upgraded.insert().values(
                    id=3,
                    box_id=uuid.uuid4().hex,
                    fbs_order_id=wb_order_id.hex,
                    order_product_id=None,
                    quantity=1,
                )
            )
        # The same Ozon position in a *different* box is now allowed — this
        # is exactly what WMS-453 unblocks.
        connection.execute(
            upgraded.insert().values(
                id=4,
                box_id=ozon_box_2.hex,
                fbs_order_id=ozon_order_id.hex,
                order_product_id=position_id.hex,
                quantity=3,
            )
        )
        # The same Ozon position twice in the *same* box is still rejected.
        with pytest.raises(IntegrityError):
            connection.execute(
                upgraded.insert().values(
                    id=5,
                    box_id=ozon_box_1.hex,
                    fbs_order_id=ozon_order_id.hex,
                    order_product_id=position_id.hex,
                    quantity=1,
                )
            )

        with pytest.raises(RuntimeError, match="Remove position assignments"):
            migration.downgrade()
        connection.execute(upgraded.delete().where(upgraded.c.id == 4))
        migration.downgrade()
        restored = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        # Only what WMS-453 added is undone — order_product_id predates it
        # (WMS-355, migration 0254) and stays.
        assert "order_product_id" in restored.c
        assert "quantity" not in restored.c
        assert "last_idempotency_key" not in restored.c
        assert connection.scalar(sa.select(sa.func.count()).select_from(restored)) == 2
        # The pre-WMS-453 combined index is back: same position, same order,
        # a second row is rejected again regardless of which box.
        with pytest.raises(IntegrityError):
            connection.execute(
                restored.insert().values(
                    id=6, box_id=uuid.uuid4().hex, fbs_order_id=ozon_order_id.hex,
                    order_product_id=position_id.hex,
                )
            )
    engine.dispose()
