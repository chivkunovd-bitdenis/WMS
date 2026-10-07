"""The print guard must accept every current Ozon exemplar for a multi-unit position."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import FbsOrder, FbsOrderMarking
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FbsSupply
from app.services.fbs_print_binding_service import PrintBinding, print_bindings_current
from app.services.ozon_fbs_marking_gate_service import current_markings
from tests.test_ozon_fbs_process_contract import _seed_order


def _bindings(
    order: FbsOrder,
    supply: FbsSupply,
    markings: list[FbsOrderMarking],
) -> list[PrintBinding]:
    return [
        PrintBinding(
            order_id=order.id,
            supply_id=supply.id,
            marking_id=marking.id,
            cis_code=marking.value,
        )
        for marking in markings
    ]


async def test_ozon_quantity_three_accepts_all_current_bindings_and_rejects_replaced_generation(
    db_session: AsyncSession,
) -> None:
    order, position = await _seed_order(db_session)
    supply = FbsSupply(
        tenant_id=order.tenant_id,
        seller_id=order.seller_id,
        warehouse_id=order.warehouse_id,
        marketplace="ozon",
        name="Ozon quantity print proof",
        status="assembling",
        delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    markings = [
        FbsOrderMarking(
            tenant_id=order.tenant_id,
            order_id=order.id,
            order_product_id=position.id,
            kind="sgtin",
            value=f"010460123456789021{index:04d}",
            meta_details_json={"exemplar_id": 80 + index},
        )
        for index in range(1, 4)
    ]
    db_session.add_all(markings)
    await db_session.commit()

    order = await db_session.scalar(
        select(FbsOrder)
        .where(FbsOrder.id == order.id)
        .options(selectinload(FbsOrder.product_positions))
    )
    assert order is not None
    position = next(row for row in order.product_positions if row.id == position.id)
    assert position.quantity == 3
    current = current_markings(order, markings)
    assert {row.id for row in current} == {row.id for row in markings}
    current_bindings = _bindings(order, supply, current)
    assert await print_bindings_current(db_session, order.tenant_id, current_bindings) is True

    replaced = markings[0]
    replaced.meta_status = "replacement_required"
    replacement = FbsOrderMarking(
        tenant_id=order.tenant_id,
        order_id=order.id,
        order_product_id=position.id,
        kind="sgtin",
        value="0104601234567890219999",
        meta_details_json={"exemplar_id": 99},
        created_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    db_session.add(replacement)
    await db_session.commit()

    next_generation = current_markings(order, [*markings, replacement])
    assert len(next_generation) == position.quantity
    assert replacement in next_generation
    assert replaced not in next_generation
    stale_binding = _bindings(order, supply, [replaced])
    next_bindings = _bindings(order, supply, next_generation)
    assert await print_bindings_current(db_session, order.tenant_id, stale_binding) is False
    assert await print_bindings_current(db_session, order.tenant_id, next_bindings) is True
