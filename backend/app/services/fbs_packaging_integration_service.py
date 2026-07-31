"""FBS supply ↔ packaging task integration."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    MARKING_KIND_SGTIN,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DRAFT,
    FBS_SUPPLY_STATUS_PACKED,
    FbsSupply,
)
from app.models.fbs_trbx import FbsTrbx
from app.models.packaging_task import STATUS_DRAFT, PackagingTask, PackagingTaskLine
from app.services import sorting_location_service as sorting_loc_svc
from app.services.document_number_service import (
    DOC_TYPE_PACKAGING,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)
from app.services.packaging_task_service import get_task, is_task_complete

logger = logging.getLogger(__name__)

_VALID_SUPPLY_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    FBS_SUPPLY_STATUS_DRAFT: frozenset({FBS_SUPPLY_STATUS_ASSEMBLING}),
    FBS_SUPPLY_STATUS_ASSEMBLING: frozenset({FBS_SUPPLY_STATUS_PACKED}),
    FBS_SUPPLY_STATUS_PACKED: frozenset(),
}


class FbsPackagingIntegrationError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def _load_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = False,
    with_trbxes: bool = False,
    for_update: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product),
            selectinload(FbsSupply.orders).selectinload(FbsOrder.markings),
        )
    if with_trbxes:
        stmt = stmt.options(selectinload(FbsSupply.trbxes))
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _supply_requires_marking(supply: FbsSupply) -> bool:
    for order in supply.orders:
        product = order.product
        if (
            product is not None
            and product.requires_honest_sign
            and not any(marking.kind == MARKING_KIND_SGTIN for marking in order.markings)
        ):
            return True
    return False


async def create_packaging_task_for_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> PackagingTask:
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    if supply.packaging_task_id is not None:
        existing = await get_task(session, tenant_id, supply.packaging_task_id)
        if existing is not None:
            return existing

    task = PackagingTask(
        tenant_id=tenant_id,
        warehouse_id=supply.warehouse_id,
        status=STATUS_DRAFT,
    )
    session.add(task)
    await session.flush()
    await assign_document_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )
    await assign_display_number_if_missing(
        session, tenant_id, DOC_TYPE_PACKAGING, task
    )

    qty_by_product: dict[uuid.UUID, int] = defaultdict(int)
    for order in supply.orders:
        if order.product_id is None:
            logger.warning(
                "fbs packaging: order %s in supply %s has no mapped product",
                order.id,
                supply.id,
            )
            continue
        qty_by_product[order.product_id] += 1

    sorting_loc = await sorting_loc_svc.get_or_create_sorting_location(
        session, tenant_id, supply.warehouse_id
    )
    for product_id, qty in sorted(qty_by_product.items(), key=lambda item: str(item[0])):
        session.add(
            PackagingTaskLine(
                task_id=task.id,
                product_id=product_id,
                storage_location_id=sorting_loc.id,
                qty_total=qty,
                qty_suggested_packed=0,
            )
        )

    supply.packaging_task_id = task.id
    await session.flush()
    loaded = await get_task(session, tenant_id, task.id)
    assert loaded is not None
    return loaded


async def update_supply_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    new_status: str,
) -> FbsSupply:
    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_orders=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")

    if new_status == supply.status:
        return supply

    allowed = _VALID_SUPPLY_STATUS_TRANSITIONS.get(supply.status, frozenset())
    if new_status not in allowed:
        raise FbsPackagingIntegrationError("invalid_status_transition")

    supply.status = new_status
    if new_status == FBS_SUPPLY_STATUS_ASSEMBLING:
        await create_packaging_task_for_supply(session, tenant_id, supply_id)
        for order in supply.orders:
            if order.status == FBS_ORDER_STATUS_IN_SUPPLY:
                order.status = FBS_ORDER_STATUS_ASSEMBLING

    await session.flush()
    return supply


async def sync_fbs_supply_on_packaging_done(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
) -> FbsSupply | None:
    supply = await _load_supply_by_packaging_task(
        session, tenant_id, packaging_task_id, with_orders=True
    )
    if supply is None or supply.status != FBS_SUPPLY_STATUS_ASSEMBLING:
        return supply

    task = await get_task(session, tenant_id, packaging_task_id)
    if task is None or not is_task_complete(task):
        return supply

    if _supply_requires_marking(supply):
        return supply

    supply.status = FBS_SUPPLY_STATUS_PACKED
    for order in supply.orders:
        if order.status in (FBS_ORDER_STATUS_IN_SUPPLY, FBS_ORDER_STATUS_ASSEMBLING):
            order.status = FBS_ORDER_STATUS_PACKED
    await session.flush()
    return supply


async def _load_supply_by_packaging_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    packaging_task_id: uuid.UUID,
    *,
    with_orders: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.tenant_id == tenant_id,
        FbsSupply.packaging_task_id == packaging_task_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product),
            selectinload(FbsSupply.orders).selectinload(FbsOrder.markings),
        )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def bind_packaging_box_to_trbx(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    trbx_id: uuid.UUID,
    packaging_box_id: uuid.UUID,
) -> FbsTrbx:
    from app.models.fbs_supply import FBS_DELIVERY_TYPE_PVZ

    supply = await _load_supply(
        session,
        tenant_id,
        supply_id,
        with_trbxes=True,
        for_update=True,
    )
    if supply is None:
        raise FbsPackagingIntegrationError("supply_not_found")
    if supply.delivery_type != FBS_DELIVERY_TYPE_PVZ:
        raise FbsPackagingIntegrationError("wrong_delivery_type")

    trbx = next((row for row in supply.trbxes if row.id == trbx_id), None)
    if trbx is None:
        raise FbsPackagingIntegrationError("trbx_not_found")

    trbx.packaging_box_id = packaging_box_id
    await session.flush()
    return trbx
