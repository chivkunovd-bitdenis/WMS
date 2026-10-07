"""Check prepared labels at dispatch; never allocate or mutate their bindings.

This read is intentionally distinct from a printer receipt: it cannot cancel a
job the external printer already accepted, nor make HTTP and OS dispatch atomic.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    MARKING_KIND_SGTIN,
    META_STATUS_REJECTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import MarkingCode


@dataclass(frozen=True)
class PrintBinding:
    order_id: uuid.UUID
    supply_id: uuid.UUID
    marking_id: uuid.UUID
    cis_code: str


async def print_bindings_current(
    session: AsyncSession, tenant_id: uuid.UUID, bindings: list[PrintBinding],
) -> bool:
    # The same order locks as KIZ delete/replace, in a stable order. Nothing
    # survives the request: a disconnected printer cannot block the operator.
    supply_ids = {binding.supply_id for binding in bindings}
    supplies = (await session.scalars(
        select(FbsSupply).where(
            FbsSupply.id.in_(supply_ids), FbsSupply.tenant_id == tenant_id,
        )
    )).all()
    supply_by_id = {supply.id: supply for supply in supplies}
    orders = (await session.scalars(
        select(FbsOrder).where(
            FbsOrder.id.in_({binding.order_id for binding in bindings}),
            FbsOrder.tenant_id == tenant_id,
        ).order_by(FbsOrder.id).with_for_update(of=FbsOrder)
        .execution_options(populate_existing=True)
    )).all()
    order_by_id = {order.id: order for order in orders}
    rows = (await session.execute(
        select(FbsOrderMarking, MarkingCode)
        .outerjoin(MarkingCode, MarkingCode.id == FbsOrderMarking.marking_code_id)
        .where(
            FbsOrderMarking.id.in_({binding.marking_id for binding in bindings}),
            FbsOrderMarking.tenant_id == tenant_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
        ).order_by(FbsOrderMarking.id).with_for_update(of=FbsOrderMarking)
        .execution_options(populate_existing=True)
    )).all()
    marking_by_id = {marking.id: (marking, code) for marking, code in rows}
    for binding in sorted(bindings, key=lambda item: (item.order_id, item.marking_id)):
        order = order_by_id.get(binding.order_id)
        supply = supply_by_id.get(binding.supply_id)
        row = marking_by_id.get(binding.marking_id)
        if order is None or supply is None or row is None:
            return False
        if order.seller_id != supply.seller_id or order.marketplace != supply.marketplace:
            return False
        if order.supply_id != supply.id:
            # A valid FBS reprint may use an order carried forward through the
            # existing pick/box/fulfillment history of this supply.
            from app.services.fbs_cancelled_after_pack_service import order_belonged_to_supply

            if not await order_belonged_to_supply(session, order, supply):
                return False
        marking, code = row
        if marking.order_id != order.id or marking.meta_status == META_STATUS_REJECTED:
            return False
        if code is not None and (code.tenant_id != tenant_id or code.seller_id != order.seller_id):
            return False
        # WB may store normalized value; the catalog row preserves the full CIS.
        if binding.cis_code not in {marking.value, code.cis_code if code else None}:
            return False
        # A response can become stale even when its old marking row survives:
        # replacements keep history on the order, and Ozon keeps one active
        # marking per posting position. Check the current generation in the
        # same position before allowing the prepared label to leave the browser.
        current_stmt = (
            select(FbsOrderMarking.id)
            .where(
                FbsOrderMarking.order_id == order.id,
                FbsOrderMarking.kind == MARKING_KIND_SGTIN,
                FbsOrderMarking.meta_status != META_STATUS_REJECTED,
            )
            .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
            .limit(1)
            .with_for_update()
        )
        if order.marketplace == "ozon":
            if marking.order_product_id is None:
                return False
            current_stmt = current_stmt.where(
                FbsOrderMarking.order_product_id == marking.order_product_id
            )
        elif marking.order_product_id is not None:
            return False
        current_id = await session.scalar(current_stmt)
        if current_id != marking.id:
            return False
    return True
