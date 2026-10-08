"""Check prepared labels at dispatch; never allocate or mutate their bindings.

This read is intentionally distinct from a printer receipt: it cannot cancel a
job the external printer already accepted, nor make HTTP and OS dispatch atomic.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    MARKING_KIND_SGTIN,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    FbsOrder,
    FbsOrderMarking,
    FbsOrderProduct,
)
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import MarkingCode


@dataclass(frozen=True)
class PrintBinding:
    order_id: uuid.UUID
    supply_id: uuid.UUID
    marking_id: uuid.UUID
    cis_code: str


def current_ozon_print_marking_ids(
    markings: Sequence[FbsOrderMarking], quantity: int,
) -> set[uuid.UUID]:
    """Choose the newest printable generation per Ozon exemplar.

    Ozon positions can contain several KIZ, one per exemplar. Timestamp ties
    across different exemplars are all retained, as in the existing Ozon
    quantity reader; ties for the same exemplar are ambiguous and are not
    treated as a current binding. Rows without exemplar metadata keep the
    existing quantity/cutoff fallback.
    """
    if quantity <= 0:
        return set()

    def created_key(marking: FbsOrderMarking) -> float:
        return marking.created_at.timestamp() if marking.created_at is not None else float("-inf")

    by_exemplar: dict[int, list[FbsOrderMarking]] = {}
    without_exemplar: list[FbsOrderMarking] = []
    for marking in markings:
        details = marking.meta_details_json if isinstance(marking.meta_details_json, dict) else {}
        exemplar_id = details.get("exemplar_id")
        if type(exemplar_id) is not int:
            without_exemplar.append(marking)
            continue
        by_exemplar.setdefault(exemplar_id, []).append(marking)

    latest_by_exemplar: list[FbsOrderMarking] = []
    for rows in by_exemplar.values():
        newest_at = max(created_key(row) for row in rows)
        newest = [row for row in rows if created_key(row) == newest_at]
        # An equal-time pair for one exemplar has no reliable generation order.
        if len(newest) == 1:
            latest_by_exemplar.append(newest[0])

    candidates = latest_by_exemplar
    candidates.extend(without_exemplar)
    candidates.sort(key=lambda row: (created_key(row), str(row.id)), reverse=True)
    selected = candidates[:quantity]
    if len(candidates) > quantity and selected:
        cutoff = created_key(selected[-1])
        selected.extend(row for row in candidates[quantity:] if created_key(row) == cutoff)
    return {
        row.id for row in selected
        if row.meta_status not in {META_STATUS_REJECTED, META_STATUS_REPLACEMENT_REQUIRED}
    }


async def print_bindings_current(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bindings: list[PrintBinding],
    *,
    reprint_marking_ids: set[uuid.UUID] | None = None,
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
    ozon_position_current_ids: dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]] = {}
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
        if marking.order_id != order.id:
            return False
        if marking.meta_status == META_STATUS_REJECTED and (
            order.marketplace != "wb"
            or reprint_marking_ids is None
            or marking.id not in reprint_marking_ids
        ):
            return False
        if marking.meta_status == META_STATUS_REPLACEMENT_REQUIRED:
            return False
        if code is not None and (code.tenant_id != tenant_id or code.seller_id != order.seller_id):
            return False
        # WB may store normalized value; the catalog row preserves the full CIS.
        if binding.cis_code not in {marking.value, code.cis_code if code else None}:
            return False
        if order.marketplace == "ozon":
            if (
                marking.order_product_id is None
                or marking.meta_status == META_STATUS_REPLACEMENT_REQUIRED
            ):
                return False
            position_key = (order.id, marking.order_product_id)
            current_ids = ozon_position_current_ids.get(position_key)
            if current_ids is None:
                quantity = await session.scalar(
                    select(FbsOrderProduct.quantity).where(
                        FbsOrderProduct.id == marking.order_product_id,
                        FbsOrderProduct.order_id == order.id,
                    )
                )
                if quantity is None or quantity <= 0:
                    return False
                current_rows = (await session.scalars(
                    select(FbsOrderMarking)
                    .where(
                        FbsOrderMarking.order_id == order.id,
                        FbsOrderMarking.order_product_id == marking.order_product_id,
                        FbsOrderMarking.tenant_id == tenant_id,
                        FbsOrderMarking.kind == MARKING_KIND_SGTIN,
                    )
                    .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )).all()
                current_ids = current_ozon_print_marking_ids(current_rows, quantity)
                ozon_position_current_ids[position_key] = current_ids
            if marking.id not in current_ids:
                return False
        elif marking.order_product_id is not None:
            return False
        else:
            # WB orders have one current marking row at order scope.
            current_id = await session.scalar(
                select(FbsOrderMarking.id)
                .where(
                    FbsOrderMarking.order_id == order.id,
                    FbsOrderMarking.kind == MARKING_KIND_SGTIN,
                )
                .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
                .limit(1)
                .with_for_update()
            )
            if current_id != marking.id:
                return False
    return True
