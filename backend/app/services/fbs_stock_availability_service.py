"""FBS stock availability: batch math for WB publish and order reserve."""

from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import stock_direction_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE


def clamp_nonneg(value: int) -> int:
    return max(0, value)


async def fbs_reserved_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    stmt = (
        select(
            FbsOrderReservation.product_id,
            func.coalesce(func.sum(FbsOrderReservation.quantity), 0),
        )
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id == warehouse_id,
            FbsOrderReservation.product_id.in_(product_ids),
        )
        .group_by(FbsOrderReservation.product_id)
    )
    if exclude_fbs_order_ids:
        stmt = stmt.where(FbsOrderReservation.fbs_order_id.notin_(exclude_fbs_order_ids))
    res = await session.execute(stmt)
    return {pid: int(qty) for pid, qty in res.all()}


async def fbs_reserved_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = (
        frozenset({exclude_order_id}) if exclude_order_id is not None else None
    )
    reserved = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        [product_id],
        exclude_fbs_order_ids=exclude_ids,
    )
    return int(reserved.get(product_id, 0))


async def _storage_and_sorting_on_hand_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int]]:
    """product_id -> (storage_qty, sorting_qty)."""
    if not product_ids:
        return {}
    storage_qty = func.coalesce(
        func.sum(
            case(
                (
                    StorageLocation.code != SORTING_LOCATION_CODE,
                    InventoryBalance.quantity,
                ),
                else_=0,
            )
        ),
        0,
    )
    sorting_qty = func.coalesce(
        func.sum(
            case(
                (
                    StorageLocation.code == SORTING_LOCATION_CODE,
                    InventoryBalance.quantity,
                ),
                else_=0,
            )
        ),
        0,
    )
    stmt = (
        select(
            InventoryBalance.product_id,
            storage_qty,
            sorting_qty,
        )
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
        .group_by(InventoryBalance.product_id)
    )
    res = await session.execute(stmt)
    return {
        pid: (int(storage or 0), int(sorting or 0)) for pid, storage, sorting in res.all()
    }


async def fbs_available_qty_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    exclude_fbs_order_ids: frozenset[uuid.UUID] | None = None,
) -> dict[uuid.UUID, int]:
    """FBS pool minus active FBS reserves; legacy physical formula when no directions exist."""
    if not product_ids:
        return {}
    from app.services.marketplace_unload_service import _outbound_reserved_by_product

    on_hand_map = await _storage_and_sorting_on_hand_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    outbound_map = await _outbound_reserved_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    fbs_map = await fbs_reserved_by_product(
        session,
        tenant_id,
        warehouse_id,
        product_ids,
        exclude_fbs_order_ids=exclude_fbs_order_ids,
    )
    direction_map = await stock_direction_service.direction_totals_by_product(
        session, tenant_id, product_ids
    )
    result: dict[uuid.UUID, int] = {}
    for pid in product_ids:
        directions = direction_map.get(pid)
        fbs = int(fbs_map.get(pid, 0))
        if directions is not None and directions.has_any:
            result[pid] = clamp_nonneg(directions.fbs - fbs)
            continue
        storage, sorting = on_hand_map.get(pid, (0, 0))
        outbound = int(outbound_map.get(pid, 0))
        result[pid] = clamp_nonneg(storage + sorting - outbound - fbs)
    return result


async def fbs_available_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_fbs_order_id: uuid.UUID | None = None,
) -> int:
    exclude_ids = (
        frozenset({exclude_fbs_order_id}) if exclude_fbs_order_id is not None else None
    )
    result = await fbs_available_qty_by_product(
        session,
        tenant_id,
        warehouse_id,
        [product_id],
        exclude_fbs_order_ids=exclude_ids,
    )
    return int(result.get(product_id, 0))
