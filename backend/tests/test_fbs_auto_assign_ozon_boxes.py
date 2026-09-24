"""WMS-526: server-side auto layout of unboxed Ozon positions into new boxes.

One position -> one new box, everything else (WB, manual layout, existing
empty boxes) untouched. See docs/requirements/WMS-526.md for R2-R4, R8-R11.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder, FbsOrderProduct
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import fbs_packing_box_service as boxes_svc

_wb_order_ids = itertools.count(90_000)


async def _ozon_supply(db_session: AsyncSession) -> tuple[Tenant, FbsSupply]:
    tenant = Tenant(name="Auto-assign", slug=f"auto-assign-{uuid.uuid4().hex[:10]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"auto-assign-{uuid.uuid4().hex[:8]}")
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="ozon",
        external_supply_id="ozon-supply-auto",
        wb_supply_id="ozon-supply-auto",
        name="Ozon FBS auto-assign",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add_all([tenant, seller, warehouse, supply])
    await db_session.flush()
    return tenant, supply


async def _wb_supply(db_session: AsyncSession) -> tuple[Tenant, FbsSupply]:
    tenant = Tenant(name="Auto-assign WB", slug=f"auto-assign-wb-{uuid.uuid4().hex[:10]}")
    seller = Seller(tenant=tenant, name="Seller")
    warehouse = Warehouse(tenant=tenant, name="FBS", code=f"auto-assign-wb-{uuid.uuid4().hex[:8]}")
    supply = FbsSupply(
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        marketplace="wb",
        wb_supply_id="wb-supply-auto",
        name="WB auto-assign",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add_all([tenant, seller, warehouse, supply])
    await db_session.flush()
    return tenant, supply


async def _order(
    db_session: AsyncSession,
    tenant: Tenant,
    supply: FbsSupply,
    *,
    external_id: str,
    deadline_offset_hours: int = 0,
    status: str | None = None,
) -> FbsOrder:
    now = datetime.now(UTC)
    order = FbsOrder(
        tenant=tenant,
        seller_id=supply.seller_id,
        warehouse_id=supply.warehouse_id,
        supply=supply,
        marketplace=supply.marketplace,
        external_order_id=external_id,
        wb_order_id=next(_wb_order_ids),
        wb_warehouse_id=11,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=now,
        deadline_at=now + timedelta(days=1, hours=deadline_offset_hours),
    )
    if status is not None:
        order.status = status
    db_session.add(order)
    await db_session.flush()
    return order


async def _positions(
    db_session: AsyncSession, order: FbsOrder, quantities: list[int]
) -> list[FbsOrderProduct]:
    positions = [
        FbsOrderProduct(
            order_id=order.id,
            position_index=index,
            ozon_sku=5000 + index,
            quantity=quantity,
            name=f"Position {index}",
        )
        for index, quantity in enumerate(quantities)
    ]
    db_session.add_all(positions)
    await db_session.flush()
    return positions


async def _box_items_for_supply(
    db_session: AsyncSession, supply_id: uuid.UUID
) -> list[FbsPackingBoxItem]:
    return list(
        (
            await db_session.scalars(
                select(FbsPackingBoxItem)
                .join(FbsPackingBox, FbsPackingBox.id == FbsPackingBoxItem.box_id)
                .where(FbsPackingBox.supply_id == supply_id)
            )
        ).all()
    )


async def _boxes_for_supply(db_session: AsyncSession, supply_id: uuid.UUID) -> list[FbsPackingBox]:
    return list(
        (
            await db_session.scalars(
                select(FbsPackingBox)
                .where(FbsPackingBox.supply_id == supply_id)
                .order_by(FbsPackingBox.box_number)
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_auto_assign_puts_every_position_in_its_own_consecutive_box(
    db_session: AsyncSession,
) -> None:
    tenant, supply = await _ozon_supply(db_session)
    single_orders = [
        await _order(db_session, tenant, supply, external_id=f"single-{i}", deadline_offset_hours=i)
        for i in range(3)
    ]
    single_positions = [
        (await _positions(db_session, order, [1]))[0] for order in single_orders
    ]
    multi_order = await _order(
        db_session, tenant, supply, external_id="multi", deadline_offset_hours=10
    )
    multi_positions = await _positions(db_session, multi_order, [1, 1])
    qty_order = await _order(
        db_session, tenant, supply, external_id="qty-two", deadline_offset_hours=20
    )
    qty_position = (await _positions(db_session, qty_order, [2]))[0]

    boxes = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )

    assert len(boxes) == 6
    assert [box.box_number for box in boxes] == [1, 2, 3, 4, 5, 6]
    for box in boxes:
        assert len(box.items) == 1

    items = await _box_items_for_supply(db_session, supply.id)
    assigned_position_ids = {item.order_product_id for item in items}
    assert assigned_position_ids == {p.id for p in single_positions} | {
        p.id for p in multi_positions
    } | {qty_position.id}

    # The multi-position order's two positions landed in consecutively
    # numbered boxes (R2: "positions of one order go consecutively").
    boxes_by_position = {item.order_product_id: item.box_id for item in items}
    box_number_by_id = {box.id: box.box_number for box in boxes}
    multi_box_numbers = sorted(
        box_number_by_id[boxes_by_position[p.id]] for p in multi_positions
    )
    assert multi_box_numbers[1] - multi_box_numbers[0] == 1

    # The qty=2 position is whole in its one box; quantity still lives only
    # on the position (WMS-355), never duplicated onto the box.
    qty_box_id = boxes_by_position[qty_position.id]
    qty_box_items = [item for item in items if item.box_id == qty_box_id]
    assert len(qty_box_items) == 1
    await db_session.refresh(qty_position)
    assert qty_position.quantity == 2


@pytest.mark.asyncio
async def test_repeat_call_does_not_duplicate_boxes_or_positions(db_session: AsyncSession) -> None:
    tenant, supply = await _ozon_supply(db_session)
    order = await _order(db_session, tenant, supply, external_id="repeat")
    await _positions(db_session, order, [1])

    first = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )
    assert len(first) == 1

    second = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )
    assert len(second) == 1
    assert [b.id for b in second] == [b.id for b in first]

    boxes = await _boxes_for_supply(db_session, supply.id)
    assert len(boxes) == 1
    items = await _box_items_for_supply(db_session, supply.id)
    assert len(items) == 1


@pytest.mark.asyncio
async def test_nothing_to_assign_is_a_successful_noop(db_session: AsyncSession) -> None:
    tenant, supply = await _ozon_supply(db_session)

    boxes = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )

    assert boxes == []
    assert await _boxes_for_supply(db_session, supply.id) == []


@pytest.mark.asyncio
async def test_partial_layout_and_existing_empty_box_are_left_alone(
    db_session: AsyncSession,
) -> None:
    tenant, supply = await _ozon_supply(db_session)
    manual_order = await _order(db_session, tenant, supply, external_id="manual")
    manual_position = (await _positions(db_session, manual_order, [1]))[0]
    split_order = await _order(
        db_session, tenant, supply, external_id="split", deadline_offset_hours=5
    )
    split_positions = await _positions(db_session, split_order, [1, 1])

    manual_boxes = await boxes_svc.create_boxes(
        db_session, tenant.id, supply.id, 3, "manual-setup", actor_user_id=None
    )
    # box 1: manual order fully assigned by hand.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        manual_boxes[0].id,
        [],
        actor_user_id=None,
        order_product_ids=[manual_position.id],
    )
    # box 2: only the first position of the split order.
    await boxes_svc.assign_orders(
        db_session,
        tenant.id,
        supply.id,
        manual_boxes[1].id,
        [],
        actor_user_id=None,
        order_product_ids=[split_positions[0].id],
    )
    # box 3 stays empty.
    empty_box_id = manual_boxes[2].id

    boxes = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )

    # Only the still-unboxed second position of the split order got a new box.
    assert len(boxes) == 4
    new_boxes = [box for box in boxes if box.box_number > 3]
    assert len(new_boxes) == 1
    assert [item.order_product_id for item in new_boxes[0].items] == [split_positions[1].id]

    # Existing boxes untouched: manual assignment intact, empty box still empty.
    items = await _box_items_for_supply(db_session, supply.id)
    manual_items = [item for item in items if item.box_id == manual_boxes[0].id]
    assert [item.order_product_id for item in manual_items] == [manual_position.id]
    empty_box = await db_session.get(FbsPackingBox, empty_box_id)
    await db_session.refresh(empty_box, ["items"])
    assert empty_box.items == []


@pytest.mark.asyncio
async def test_cancelled_order_is_skipped(db_session: AsyncSession) -> None:
    tenant, supply = await _ozon_supply(db_session)
    cancelled_order = await _order(
        db_session,
        tenant,
        supply,
        external_id="cancelled",
        status=FBS_ORDER_STATUS_CANCELLED,
    )
    cancelled_position = (await _positions(db_session, cancelled_order, [1]))[0]
    live_order = await _order(
        db_session, tenant, supply, external_id="live", deadline_offset_hours=1
    )
    live_position = (await _positions(db_session, live_order, [1]))[0]

    boxes = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )

    assert len(boxes) == 1
    items = await _box_items_for_supply(db_session, supply.id)
    assert {item.order_product_id for item in items} == {live_position.id}
    assert cancelled_position.id not in {item.order_product_id for item in items}


@pytest.mark.asyncio
async def test_wb_supply_is_rejected_without_creating_anything(db_session: AsyncSession) -> None:
    tenant, supply = await _wb_supply(db_session)
    order = await _order(db_session, tenant, supply, external_id="wb-order")

    with pytest.raises(boxes_svc.FbsPackingBoxError, match="auto_assign_requires_ozon"):
        await boxes_svc.auto_assign_ozon_positions(
            db_session, tenant.id, supply.id, actor_user_id=None
        )

    assert await _boxes_for_supply(db_session, supply.id) == []
    # Order stays untouched; no box was ever attempted for it.
    assert order.status != FBS_ORDER_STATUS_CANCELLED


@pytest.mark.asyncio
async def test_delivered_supply_is_rejected_same_as_create_boxes(
    db_session: AsyncSession,
) -> None:
    tenant, supply = await _ozon_supply(db_session)
    order = await _order(db_session, tenant, supply, external_id="delivered")
    await _positions(db_session, order, [1])
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    await db_session.flush()

    with pytest.raises(boxes_svc.FbsPackingBoxError, match="supply_not_editable"):
        await boxes_svc.create_boxes(
            db_session, tenant.id, supply.id, 1, "after-delivery", actor_user_id=None
        )
    with pytest.raises(boxes_svc.FbsPackingBoxError, match="supply_not_editable"):
        await boxes_svc.auto_assign_ozon_positions(
            db_session, tenant.id, supply.id, actor_user_id=None
        )


@pytest.mark.asyncio
async def test_more_than_one_hundred_positions_are_all_assigned_in_one_call(
    db_session: AsyncSession,
) -> None:
    tenant, supply = await _ozon_supply(db_session)
    order = await _order(db_session, tenant, supply, external_id="bulk")
    await _positions(db_session, order, [1] * 150)

    boxes = await boxes_svc.auto_assign_ozon_positions(
        db_session, tenant.id, supply.id, actor_user_id=None
    )

    assert len(boxes) == 150
    assert sorted(box.box_number for box in boxes) == list(range(1, 151))
    items = await _box_items_for_supply(db_session, supply.id)
    assert len({item.order_product_id for item in items}) == 150
    box_ids = {item.box_id for item in items}
    assert len(box_ids) == 150


@pytest.mark.asyncio
async def test_failure_partway_leaves_no_new_boxes_or_assignments(
    db_session: AsyncSession,
) -> None:
    tenant, supply = await _ozon_supply(db_session)
    good_order = await _order(
        db_session, tenant, supply, external_id="good", deadline_offset_hours=0
    )
    await _positions(db_session, good_order, [1])
    # Contrived edge state: an order flagged as already assembled in Ozon
    # while one of its positions is still unboxed. In practice assembly only
    # happens once every position of the order is boxed, but this reuses the
    # existing _assert_ozon_orders_mutable guard (WMS-355/357) to force a
    # failure partway through the loop and prove the whole operation is one
    # transaction, not a per-position commit.
    bad_order = await _order(
        db_session, tenant, supply, external_id="bad", deadline_offset_hours=1
    )
    await _positions(db_session, bad_order, [1])
    bad_order.meta_details_json = {"ozon_assembly": {"posting_numbers": ["already-shipped"]}}
    await db_session.flush()

    with pytest.raises(boxes_svc.FbsPackingBoxError, match="ozon_order_already_assembled"):
        async with db_session.begin_nested():
            await boxes_svc.auto_assign_ozon_positions(
                db_session, tenant.id, supply.id, actor_user_id=None
            )

    assert await _boxes_for_supply(db_session, supply.id) == []
    assert await _box_items_for_supply(db_session, supply.id) == []
    remaining_boxes = await db_session.scalar(
        select(func.count(FbsPackingBox.id)).where(FbsPackingBox.supply_id == supply.id)
    )
    assert remaining_boxes == 0
