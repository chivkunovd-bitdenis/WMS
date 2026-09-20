"""WMS-453 (and WMS-355 before it): an Ozon order position's quantity can be
split across any number of boxes, one order stays confined to one box, and a
box freezes once its order is assembled in Ozon."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
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
async def test_same_key_retried_with_corrected_quantity_after_409_succeeds(
    db_session: AsyncSession,
) -> None:
    """A request that fails validation (over the remainder, R2) must never
    claim its idempotency key — the client keeps one key until the first
    *successful* response (R6), so a 409 is followed by a retry with the
    exact same key once the operator lowers the quantity. If the key were
    claimed before the remainder check (this function's first shape, before
    a follow-up fix), that retry would wrongly read back as an
    already-applied no-op instead of actually adding anything.
    """
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "retry-after-409", actor_user_id=None
    )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_box_quantity_exceeded"):
        await boxes_svc.assign_orders(
            db_session,
            tenant.id,
            supply.id,
            boxes[0].id,
            [],
            actor_user_id=None,
            positions=_add(positions[0].id, 4),  # only 3 are available
            idempotency_key="same-key",
        )
    items = list(
        (
            await db_session.scalars(
                select(FbsPackingBoxItem).where(FbsPackingBoxItem.box_id == boxes[0].id)
            )
        ).all()
    )
    assert items == []

    # Same key, corrected quantity: must actually add, not read back as an
    # already-applied repeat of the failed attempt.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[0].id, 3),
        idempotency_key="same-key",
    )
    item = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.box_id == boxes[0].id,
            FbsPackingBoxItem.order_product_id == positions[0].id,
        )
    )
    assert item is not None and item.quantity == 3


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
async def test_repeat_after_another_operators_add_in_between_stays_a_no_op(
    db_session: AsyncSession,
) -> None:
    """Review WMS-453 F1: A -> B -> A must leave the box at 2, not 3.

    Reproduced across *separate* sessions/transactions, each with its own
    commit — the setting from the review (two operators, not one session
    replaying calls). A per-row "last key" only remembers the most recent
    touch, so once B's own add overwrites it, a retried A looks like a new
    key and gets applied again. The fix (DocumentEvent's existing tenant-wide
    idempotency-key uniqueness) must keep recognising A regardless of what
    happened to the row in between.
    """
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "f1-repro", actor_user_id=None
    )
    await db_session.commit()
    tenant_id, supply_id, box_id = tenant.id, supply.id, boxes[0].id
    position_id = positions[1].id  # quantity 5, plenty of remainder for 1+1+1

    async def _call(key: str, quantity: int) -> None:
        async with SessionLocal() as session:
            await boxes_svc.assign_orders(
                session,
                tenant_id,
                supply_id,
                box_id,
                [],
                actor_user_id=None,
                positions=_add(position_id, quantity),
                idempotency_key=key,
            )
            await session.commit()

    async def _current_quantity() -> int:
        async with SessionLocal() as session:
            item = await session.scalar(
                select(FbsPackingBoxItem).where(
                    FbsPackingBoxItem.box_id == box_id,
                    FbsPackingBoxItem.order_product_id == position_id,
                )
            )
            assert item is not None
            return item.quantity

    await _call("A", 1)
    await _call("B", 1)
    await _call("A", 1)  # the operator's client retried A after B ran, unaware of it
    assert await _current_quantity() == 2

    await _call("A", 1)  # a further retry of A must still be recognised
    assert await _current_quantity() == 2

    await _call("C", 1)  # a genuinely new, later action does add
    assert await _current_quantity() == 3


@pytest.mark.asyncio
async def test_rollback_before_route_commit_leaves_nothing_and_retry_still_adds(
    db_session: AsyncSession,
) -> None:
    """Review WMS-453 F4: on SQLite, record_document_event's SAVEPOINT can
    outlive a later session.rollback() unless the outer write transaction is
    already open — a pysqlite caveat, not a PostgreSQL one (the identical
    fix already exists for the same reason in
    inbound_intake_service._claim_intake_mutation). Reproduced exactly as in
    the review: reach assign_orders' own flush, then roll back the session
    *before* the API route's commit — a failure between flush and commit
    (lost connection, process killed, anything short of the route reaching
    session.commit()), not a validation failure inside assign_orders.
    Neither the event nor the row may survive that rollback; a retry with
    the same key in a fresh session must still add.
    """
    from app.models.document_event import EVENT_BOX_ITEM_ADDED, DocumentEvent

    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "f4-repro", actor_user_id=None
    )
    await db_session.commit()
    tenant_id, supply_id, box_id = tenant.id, supply.id, boxes[0].id
    position_id = positions[1].id

    async with SessionLocal() as session:
        await boxes_svc.assign_orders(
            session,
            tenant_id,
            supply_id,
            box_id,
            [],
            actor_user_id=None,
            positions=_add(position_id, 1),
            idempotency_key="rollback-key",
        )
        # assign_orders already reached its own flush; simulate the route
        # never reaching commit (crash, lost connection) rather than a
        # business-rule rejection.
        await session.rollback()

    async with SessionLocal() as check:
        item = await check.scalar(
            select(FbsPackingBoxItem).where(
                FbsPackingBoxItem.box_id == box_id,
                FbsPackingBoxItem.order_product_id == position_id,
            )
        )
        assert item is None
        events = (
            await check.scalars(
                select(DocumentEvent.id).where(
                    DocumentEvent.document_id == supply_id,
                    DocumentEvent.event_type == EVENT_BOX_ITEM_ADDED,
                )
            )
        ).all()
        assert events == []

    async with SessionLocal() as retry:
        await boxes_svc.assign_orders(
            retry,
            tenant_id,
            supply_id,
            box_id,
            [],
            actor_user_id=None,
            positions=_add(position_id, 1),
            idempotency_key="rollback-key",
        )
        await retry.commit()

    async with SessionLocal() as final_check:
        item = await final_check.scalar(
            select(FbsPackingBoxItem).where(
                FbsPackingBoxItem.box_id == box_id,
                FbsPackingBoxItem.order_product_id == position_id,
            )
        )
        assert item is not None and item.quantity == 1
        events = (
            await final_check.scalars(
                select(DocumentEvent.id).where(
                    DocumentEvent.document_id == supply_id,
                    DocumentEvent.event_type == EVENT_BOX_ITEM_ADDED,
                )
            )
        ).all()
        assert len(events) == 1


@pytest.mark.asyncio
async def test_colliding_key_from_another_document_type_does_not_silently_succeed(
    db_session: AsyncSession,
) -> None:
    """Review WMS-453 F5: DocumentEvent's (tenant_id, idempotency_key)
    uniqueness is tenant-wide across every operation the journal records.
    Before namespacing, an operator's client key that happened to equal
    another document's own stored key — reproduced here through the real
    inbound_intake_service._claim_intake_mutation and its
    "inbound:{action}:{mutation_id}" scheme — read back as "this box already
    got it" and silently added nothing. It must instead behave as the
    genuinely new action it is: a normal, successful add.
    """
    from app.services import inbound_intake_service as intake_svc

    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 1, "f5-cross-doc", actor_user_id=None
    )
    await db_session.commit()
    tenant_id, supply_id, box_id = tenant.id, supply.id, boxes[0].id
    position_id = positions[0].id

    mutation_id = uuid.uuid4()
    colliding_key = f"inbound:create:{mutation_id}"
    async with SessionLocal() as intake_session:
        await intake_svc._claim_intake_mutation(
            intake_session,
            tenant_id,
            uuid.uuid4(),  # an unrelated inbound intake request id
            mutation_id=mutation_id,
            action="create",
            payload={"unrelated": True},
        )
        await intake_session.commit()

    async with SessionLocal() as add_session:
        await boxes_svc.assign_orders(
            add_session,
            tenant_id,
            supply_id,
            box_id,
            [],
            actor_user_id=None,
            positions=_add(position_id, 2),
            idempotency_key=colliding_key,
        )
        await add_session.commit()

    async with SessionLocal() as check:
        item = await check.scalar(
            select(FbsPackingBoxItem).where(
                FbsPackingBoxItem.box_id == box_id,
                FbsPackingBoxItem.order_product_id == position_id,
            )
        )
        assert item is not None and item.quantity == 2


@pytest.mark.asyncio
async def test_same_key_reused_for_a_different_box_does_not_silently_succeed(
    db_session: AsyncSession,
) -> None:
    """Review WMS-453 F5: reusing the exact same client key for a second,
    different box (client bug or coincidence, not a network retry) must be
    judged as a new action for *that* box, not read back as "already done"
    just because the same string was used for a different box before.
    """
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    positions = await _positions(db_session, order)  # quantities [3, 5]
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 2, "f5-cross-box", actor_user_id=None
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[0].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 2),
        idempotency_key="shared-client-key",
    )
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        boxes[1].id,
        [],
        actor_user_id=None,
        positions=_add(positions[1].id, 2),
        idempotency_key="shared-client-key",
    )
    item0 = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.box_id == boxes[0].id,
            FbsPackingBoxItem.order_product_id == positions[1].id,
        )
    )
    item1 = await db_session.scalar(
        select(FbsPackingBoxItem).where(
            FbsPackingBoxItem.box_id == boxes[1].id,
            FbsPackingBoxItem.order_product_id == positions[1].id,
        )
    )
    assert item0 is not None and item0.quantity == 2
    assert item1 is not None and item1.quantity == 2


@pytest.mark.asyncio
async def test_concurrent_additions_serialize_under_the_supply_lock_on_postgresql(
    db_session: AsyncSession,
) -> None:
    """C3: two operators adding to two different boxes for the same position
    at the same moment must never let the sum exceed the position's
    quantity. The FOR UPDATE lock on the supply (already taken for the
    quantity check) must serialize the two transactions on real PostgreSQL —
    SQLite has no comparable row lock, so this only runs where it can prove
    anything (skipped otherwise, like the project's other *_concurrency.py
    tests, e.g. test_wms351_publication_concurrency.py).
    """
    if db_session.bind is None or db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL")
    tenant, supply, order = await _ozon_supply_with_one_order(db_session)
    position = FbsOrderProduct(
        order_id=order.id,
        position_index=0,
        ozon_sku=555,
        quantity=100,
        name="Concurrency stress position",
    )
    db_session.add(position)
    await db_session.flush()
    boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 2, "c3-concurrency", actor_user_id=None
    )
    await db_session.commit()
    tenant_id, supply_id, position_id = tenant.id, supply.id, position.id
    box_ids = [box.id for box in boxes]

    async def _attempt(box_id: uuid.UUID, key: str) -> str:
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
            try:
                await boxes_svc.assign_orders(
                    session,
                    tenant_id,
                    supply_id,
                    box_id,
                    [],
                    actor_user_id=None,
                    positions=_add(position_id, 60),
                    idempotency_key=key,
                )
                await session.commit()
                return "ok"
            except boxes_svc.FbsPackingBoxError as exc:
                await session.rollback()
                return exc.code

    results = await asyncio.gather(
        _attempt(box_ids[0], "concurrent-a"),
        _attempt(box_ids[1], "concurrent-b"),
    )
    # 60 + 60 = 120 > 100: exactly one of the two must be rejected, and the
    # lock must make that decision correctly rather than letting both see a
    # stale "0 so far" and both succeed.
    assert sorted(results) == ["ok", "ozon_box_quantity_exceeded"]

    async with SessionLocal() as check:
        total = await check.scalar(
            select(func.sum(FbsPackingBoxItem.quantity)).where(
                FbsPackingBoxItem.order_product_id == position_id
            )
        )
    assert total == 60


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

        with pytest.raises(RuntimeError, match="Remove partial or multi-box position"):
            migration.downgrade()
        connection.execute(upgraded.delete().where(upgraded.c.id == 4))
        migration.downgrade()
        restored = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        # Only what WMS-453 added is undone — order_product_id predates it
        # (WMS-355, migration 0254) and stays.
        assert "order_product_id" in restored.c
        assert "quantity" not in restored.c
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


def test_migration_downgrade_rejects_single_partial_row_but_allows_single_full_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review WMS-453 F2: a plain COUNT(*) > 1 guard missed a *single* row
    holding only part of a position ("10 of 100" in one box). The old schema
    has no quantity column, so that lone row would silently become "the whole
    position" (100) on downgrade — the owner's exact split-box scenario, not
    corrupted data. A single row holding the position's *full* quantity is
    the one state the old schema can represent and must still be allowed to
    downgrade.
    """
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/20260917_0500_wms453_ozon_box_quantity.py"
    )
    spec = spec_from_file_location("box_quantity_migration_f2", path)
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
    order_id, box_id, position_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_fbs_packing_box_items_order_position "
                "ON fbs_packing_box_items (fbs_order_id, "
                "coalesce(order_product_id, '00000000-0000-0000-0000-000000000000'))"
            )
        )
        connection.execute(order_products.insert().values(id=position_id, quantity=100))
        connection.execute(
            items.insert().values(
                id=1, box_id=box_id, fbs_order_id=order_id, order_product_id=position_id,
            )
        )
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        upgraded = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        # Upgrade backfills the whole position, as in the main migration test.
        assert connection.scalar(sa.select(upgraded.c.quantity)) == 100

        # The owner's exact scenario: only the first 10 of 100 are placed so
        # far, in a single box — one row, so the old COUNT(*) > 1 guard alone
        # would not have caught this.
        connection.execute(upgraded.update().values(quantity=10))
        with pytest.raises(RuntimeError, match="Remove partial or multi-box position"):
            migration.downgrade()

        # Once the box legitimately holds the whole position again, the lone
        # old-schema row means exactly what it always did — safe to downgrade.
        connection.execute(upgraded.update().values(quantity=100))
        migration.downgrade()
        restored = sa.Table("fbs_packing_box_items", sa.MetaData(), autoload_with=connection)
        assert "quantity" not in restored.c
        assert connection.scalar(sa.select(restored.c.order_product_id)) == position_id.hex
    engine.dispose()
