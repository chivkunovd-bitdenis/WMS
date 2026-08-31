"""Canonical reconciliation of a local WB FBS supply with its actual WB composition."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.services.fbs_supply_reconcile_service import fetch_wb_supply_order_ids

_TERMINAL_ORDER_STATUSES = frozenset(
    {FBS_ORDER_STATUS_CANCELLED, FBS_ORDER_STATUS_DONE, FBS_ORDER_STATUS_DEFECT}
)
_TERMINAL_SUPPLY_STATUSES = frozenset(
    {FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_DONE}
)
_LINKABLE_SUPPLY_STATUSES = frozenset(
    {
        FBS_SUPPLY_STATUS_DRAFT,
        FBS_SUPPLY_STATUS_ASSEMBLING,
        FBS_SUPPLY_STATUS_PACKED,
    }
)


class FbsSupplyCompositionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SupplyCompositionDiscrepancy:
    code: str
    wb_order_id: int
    local_order_id: uuid.UUID | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SupplyCompositionDelta:
    wb_only_order_ids: tuple[int, ...]
    local_only_order_ids: tuple[int, ...]
    linked_order_ids: tuple[int, ...]


@dataclass(frozen=True)
class SupplyCompositionResult:
    supply: FbsSupply
    active_orders: tuple[FbsOrder, ...]
    wb_order_ids: tuple[int, ...]
    wb_order_fingerprint: str
    delta: SupplyCompositionDelta
    discrepancies: tuple[SupplyCompositionDiscrepancy, ...]


@dataclass(frozen=True)
class SupplyOrderLinkResult:
    linked: bool
    discrepancy: SupplyCompositionDiscrepancy | None


def wb_order_ids_fingerprint(wb_order_ids: Iterable[int]) -> str:
    """Stable fingerprint of the complete WB order-id set, independent of response order."""
    normalized = sorted({int(order_id) for order_id in wb_order_ids})
    payload = ",".join(str(order_id) for order_id in normalized).encode()
    return hashlib.sha256(payload).hexdigest()


def _discrepancy(
    code: str,
    order: FbsOrder,
    *,
    detail: str | None = None,
) -> SupplyCompositionDiscrepancy:
    return SupplyCompositionDiscrepancy(
        code=code,
        wb_order_id=int(order.wb_order_id),
        local_order_id=order.id,
        detail=detail,
    )


def supply_order_link_discrepancy(
    supply: FbsSupply,
    order: FbsOrder,
    *,
    existing_orders: Iterable[FbsOrder],
) -> SupplyCompositionDiscrepancy | None:
    """Return the structural reason why an unlinked order cannot join this WB supply."""
    if order.tenant_id != supply.tenant_id:
        return _discrepancy("different_tenant", order)
    if order.seller_id != supply.seller_id:
        return _discrepancy("different_seller", order)
    if supply.marketplace != "wb" or order.marketplace != "wb":
        return _discrepancy("different_marketplace", order)
    if order.supply_id == supply.id:
        return None
    if order.supply_id is not None:
        return _discrepancy("order_in_other_supply", order)
    if supply.status in _TERMINAL_SUPPLY_STATUSES:
        return _discrepancy("terminal_supply", order, detail=supply.status)
    if supply.status not in _LINKABLE_SUPPLY_STATUSES:
        return _discrepancy("supply_not_editable", order, detail=supply.status)
    if order.status in _TERMINAL_ORDER_STATUSES:
        return _discrepancy("terminal_order", order, detail=order.status)
    if order.warehouse_id is None:
        return _discrepancy("order_warehouse_unmapped", order)
    if order.warehouse_id != supply.warehouse_id:
        return _discrepancy("different_wms_warehouse", order)
    if order.wb_supply_id and order.wb_supply_id.strip() != supply.wb_supply_id:
        return _discrepancy("different_wb_supply", order, detail=order.wb_supply_id)

    comparison_orders = [item for item in existing_orders if item.id != order.id]
    wb_warehouse_ids = {
        int(item.wb_warehouse_id)
        for item in comparison_orders
        if item.wb_warehouse_id is not None
    }
    if wb_warehouse_ids and order.wb_warehouse_id not in wb_warehouse_ids:
        return _discrepancy("different_wb_warehouse", order)
    buyer_types = {bool(item.is_legal) for item in comparison_orders}
    if buyer_types and bool(order.is_legal) not in buyer_types:
        return _discrepancy("legal_type_mismatch", order)
    cargo_types = {item.cargo_type or "unknown" for item in comparison_orders}
    if cargo_types and (order.cargo_type or "unknown") not in cargo_types:
        return _discrepancy("different_cargo_type", order)
    return None


async def link_order_to_wb_supply_if_compatible(
    session: AsyncSession,
    supply: FbsSupply,
    order: FbsOrder,
    *,
    existing_orders: list[FbsOrder],
) -> SupplyOrderLinkResult:
    """Bind one already imported order without moving it from another local supply."""
    discrepancy = supply_order_link_discrepancy(
        supply,
        order,
        existing_orders=existing_orders,
    )
    if discrepancy is not None:
        return SupplyOrderLinkResult(linked=False, discrepancy=discrepancy)
    if order.supply_id == supply.id:
        return SupplyOrderLinkResult(linked=False, discrepancy=None)

    order.supply_id = supply.id
    order.wb_supply_id = supply.wb_supply_id
    order.status = (
        FBS_ORDER_STATUS_IN_SUPPLY
        if supply.status == FBS_SUPPLY_STATUS_DRAFT
        else FBS_ORDER_STATUS_ASSEMBLING
    )
    supply.cargo_type = supply.cargo_type or order.cargo_type
    existing_orders.append(order)
    await session.flush()
    return SupplyOrderLinkResult(linked=True, discrepancy=None)


async def reconcile_actual_wb_supply_composition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    http_client: httpx.AsyncClient,
    api_token: str,
) -> SupplyCompositionResult:
    """Fetch the complete WB composition and reconcile safe local links without committing."""
    supply_stmt = (
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .options(selectinload(FbsSupply.orders))
        .with_for_update()
    )
    supply = (await session.execute(supply_stmt)).scalar_one_or_none()
    if supply is None:
        raise FbsSupplyCompositionError("supply_not_found")
    if supply.marketplace != "wb":
        raise FbsSupplyCompositionError("wrong_marketplace")
    wb_supply_id = (supply.wb_supply_id or "").strip()
    if not wb_supply_id or wb_supply_id.startswith("PENDING-"):
        raise FbsSupplyCompositionError("supply_without_wb_id")

    wb_order_ids = tuple(
        sorted(
            set(
                await fetch_wb_supply_order_ids(
                    http_client,
                    api_token=api_token,
                    wb_supply_id=wb_supply_id,
                )
            )
        )
    )
    actual_ids = set(wb_order_ids)
    initial_local_ids = {int(order.wb_order_id) for order in supply.orders}
    existing_orders = [
        order for order in supply.orders if int(order.wb_order_id) in actual_ids
    ]

    order_stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.seller_id == supply.seller_id,
            FbsOrder.wb_order_id.in_(wb_order_ids),
        )
        .order_by(FbsOrder.wb_order_id, FbsOrder.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    known_orders = (
        list((await session.execute(order_stmt)).scalars().all()) if wb_order_ids else []
    )
    known_by_wb_id = {int(order.wb_order_id): order for order in known_orders}

    discrepancies: list[SupplyCompositionDiscrepancy] = []
    linked_orders: list[FbsOrder] = []
    for wb_order_id in wb_order_ids:
        order = known_by_wb_id.get(wb_order_id)
        if order is None:
            discrepancies.append(
                SupplyCompositionDiscrepancy(
                    code="unknown_wb_order",
                    wb_order_id=wb_order_id,
                )
            )
            continue
        link_result = await link_order_to_wb_supply_if_compatible(
            session,
            supply,
            order,
            existing_orders=existing_orders,
        )
        if link_result.discrepancy is not None:
            discrepancies.append(link_result.discrepancy)
        elif link_result.linked:
            linked_orders.append(order)

    for order in supply.orders:
        wb_order_id = int(order.wb_order_id)
        if wb_order_id not in actual_ids:
            discrepancies.append(_discrepancy("local_order_not_in_wb", order))

    active_orders: list[FbsOrder] = []
    for order in existing_orders:
        if int(order.wb_order_id) not in actual_ids or order.supply_id != supply.id:
            continue
        if order.status in _TERMINAL_ORDER_STATUSES:
            discrepancies.append(_discrepancy("terminal_local_order", order, detail=order.status))
            continue
        active_orders.append(order)

    if linked_orders:
        # PackagingTask is only a legacy compatibility projection; composition above
        # is established from WB plus FbsOrder links and does not read it back.
        from app.services.fbs_supply_service import (
            _sync_existing_packaging_task_for_added_orders,
        )

        await _sync_existing_packaging_task_for_added_orders(
            session,
            tenant_id,
            supply,
            linked_orders,
        )

    discrepancies.sort(
        key=lambda item: (item.wb_order_id, item.code, str(item.local_order_id or ""))
    )
    active_orders.sort(key=lambda order: (int(order.wb_order_id), str(order.id)))
    linked_ids = tuple(sorted(int(order.wb_order_id) for order in linked_orders))
    return SupplyCompositionResult(
        supply=supply,
        active_orders=tuple(active_orders),
        wb_order_ids=wb_order_ids,
        wb_order_fingerprint=wb_order_ids_fingerprint(wb_order_ids),
        delta=SupplyCompositionDelta(
            wb_only_order_ids=tuple(sorted(actual_ids - initial_local_ids)),
            local_only_order_ids=tuple(sorted(initial_local_ids - actual_ids)),
            linked_order_ids=linked_ids,
        ),
        discrepancies=tuple(discrepancies),
    )
