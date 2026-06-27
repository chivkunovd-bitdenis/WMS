"""Unified collect: take from storage location into shipment box (+ pick allocation)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services import marketplace_unload_service as mu_svc
from app.services import sorting_location_service as sort_loc_svc
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.marketplace_unload_pick_service import (
    PICK_EDITABLE_STATUSES,
    MarketplaceUnloadPickError,
)


@dataclass(frozen=True)
class CollectResult:
    box_line: MarketplaceUnloadBoxLine
    allocation: MarketplaceUnloadPickAllocation
    picked_qty: int


async def picked_qty_by_product(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    stmt = (
        select(
            MarketplaceUnloadBoxLine.product_id,
            func.coalesce(func.sum(MarketplaceUnloadBoxLine.quantity), 0),
        )
        .join(MarketplaceUnloadBox, MarketplaceUnloadBoxLine.box_id == MarketplaceUnloadBox.id)
        .where(MarketplaceUnloadBox.request_id == request_id)
        .group_by(MarketplaceUnloadBoxLine.product_id)
    )
    res = await session.execute(stmt)
    return {row[0]: int(row[1]) for row in res.all()}


async def get_open_box(
    session: AsyncSession, request_id: uuid.UUID
) -> MarketplaceUnloadBox | None:
    stmt = select(MarketplaceUnloadBox).where(
        MarketplaceUnloadBox.request_id == request_id,
        MarketplaceUnloadBox.closed_at.is_(None),
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _request_for_collect(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")
    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    return req


async def _product_in_shipment(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id,
        MarketplaceUnloadLine.product_id == product_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def _validate_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> StorageLocation:
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id or loc.warehouse_id != warehouse_id:
        raise MarketplaceUnloadPickError("location_not_found")
    return loc


async def resolve_collect_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    storage_location_id: uuid.UUID | None,
    *,
    request_id: uuid.UUID,
    increment_qty: int,
) -> uuid.UUID:
    """Single path: address-storage flag drives cell requirement (DEC-005)."""
    address_on = await tenant_settings_svc.is_address_storage_enabled(session, tenant_id)
    if not address_on:
        if storage_location_id is not None:
            await _validate_storage_location(
                session, tenant_id, warehouse_id, storage_location_id
            )
            return storage_location_id
        rows = await inventory_service.list_location_balances_for_products_in_warehouse(
            session, tenant_id, warehouse_id, [product_id]
        )
        alloc_stmt = select(
            MarketplaceUnloadPickAllocation.storage_location_id,
            MarketplaceUnloadPickAllocation.quantity,
        ).where(
            MarketplaceUnloadPickAllocation.request_id == request_id,
            MarketplaceUnloadPickAllocation.product_id == product_id,
        )
        alloc_res = await session.execute(alloc_stmt)
        picked_by_loc = {
            loc_id: int(qty) for loc_id, qty in alloc_res.all()
        }
        candidates: list[tuple[uuid.UUID, int]] = []
        for _pid, loc_id, _code, on_hand, rsv in rows:
            avail = int(on_hand) - int(rsv)
            current_pick = picked_by_loc.get(loc_id, 0)
            new_pick = current_pick + increment_qty
            if avail >= new_pick:
                candidates.append((loc_id, avail))
        if not candidates:
            raise MarketplaceUnloadPickError("insufficient_available")
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    if storage_location_id is not None:
        await _validate_storage_location(
            session, tenant_id, warehouse_id, storage_location_id
        )
        return storage_location_id

    cell_rows = await inventory_service.list_locations_for_product_in_warehouse(
        session, tenant_id, warehouse_id, product_id
    )
    if cell_rows:
        raise MarketplaceUnloadPickError("location_required")

    sorting = await sort_loc_svc.get_or_create_sorting_location(
        session, tenant_id, warehouse_id
    )
    return sorting.id


async def collect_into_box(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    box_id: uuid.UUID | None = None,
    storage_location_id: uuid.UUID | None = None,
    product_id: uuid.UUID,
    quantity: int,
    require_open_box: bool = True,
) -> CollectResult:
    if quantity < 1:
        raise MarketplaceUnloadPickError("invalid_quantity")

    req = await _request_for_collect(session, tenant_id, request_id)
    if not await _product_in_shipment(session, req.id, product_id):
        raise MarketplaceUnloadPickError("product_not_in_shipment")

    box: MarketplaceUnloadBox | None
    if box_id is not None:
        box = await session.get(MarketplaceUnloadBox, box_id)
        if box is None or box.request_id != request_id:
            raise MarketplaceUnloadPickError("box_not_found")
        if require_open_box and box.closed_at is not None:
            raise MarketplaceUnloadPickError("box_closed")
    else:
        box = await get_open_box(session, request_id)
        if box is None:
            raise MarketplaceUnloadPickError("open_box_required")
        box_id = box.id

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadPickError("product_seller_mismatch")

    effective_location_id = await resolve_collect_storage_location(
        session,
        tenant_id,
        req.warehouse_id,
        product_id,
        storage_location_id,
        request_id=request_id,
        increment_qty=quantity,
    )

    alloc_stmt = select(MarketplaceUnloadPickAllocation).where(
        MarketplaceUnloadPickAllocation.request_id == request_id,
        MarketplaceUnloadPickAllocation.product_id == product_id,
        MarketplaceUnloadPickAllocation.storage_location_id == effective_location_id,
    )
    alloc_res = await session.execute(alloc_stmt)
    alloc = alloc_res.scalar_one_or_none()
    current_pick = int(alloc.quantity) if alloc is not None else 0
    new_pick = current_pick + quantity

    available = await inventory_service.available_at_location(
        session, tenant_id, product_id, effective_location_id
    )
    if available < new_pick:
        raise MarketplaceUnloadPickError("insufficient_available")

    if alloc is None:
        alloc = MarketplaceUnloadPickAllocation(
            request_id=request_id,
            product_id=product_id,
            storage_location_id=effective_location_id,
            quantity=new_pick,
        )
        session.add(alloc)
    else:
        alloc.quantity = new_pick

    box_line_stmt = select(MarketplaceUnloadBoxLine).where(
        MarketplaceUnloadBoxLine.box_id == box_id,
        MarketplaceUnloadBoxLine.product_id == product_id,
    )
    box_line_res = await session.execute(box_line_stmt)
    box_line = box_line_res.scalar_one_or_none()
    if box_line is None:
        box_line = MarketplaceUnloadBoxLine(
            box_id=box_id,
            product_id=product_id,
            quantity=quantity,
        )
        session.add(box_line)
    else:
        box_line.quantity = int(box_line.quantity) + quantity

    await session.commit()

    picked = await picked_qty_by_product(session, request_id)
    stmt_alloc = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.id == alloc.id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
    )
    res_alloc = await session.execute(stmt_alloc)
    alloc_loaded = res_alloc.scalar_one()
    stmt_line = (
        select(MarketplaceUnloadBoxLine)
        .where(MarketplaceUnloadBoxLine.id == box_line.id)
        .options(selectinload(MarketplaceUnloadBoxLine.product))
    )
    res_line = await session.execute(stmt_line)
    line_loaded = res_line.scalar_one()

    from app.services import packaging_task_service as pkg_svc

    pkg_task = await pkg_svc.get_task_for_unload(session, tenant_id, request_id)
    if pkg_task is not None:
        await pkg_svc.sync_lines_from_pick_allocations(session, tenant_id, pkg_task)

    return CollectResult(
        box_line=line_loaded,
        allocation=alloc_loaded,
        picked_qty=picked.get(product_id, 0),
    )
