"""Pick allocations and ship (stock deduction) for marketplace unload."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services import marketplace_unload_service as mu_svc

PICK_EDITABLE_STATUSES = (mu_svc.STATUS_CONFIRMED,)


class MarketplaceUnloadPickError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PickAllocationRow:
    product_id: uuid.UUID
    storage_location_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class PickOptionLocation:
    storage_location_id: uuid.UUID
    location_code: str
    quantity: int
    reserved: int
    available: int


@dataclass(frozen=True)
class PickOptionProduct:
    product_id: uuid.UUID
    sku_code: str
    product_name: str
    scanned_qty: int
    locations: list[PickOptionLocation]


async def _scanned_qty_by_product(
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


async def get_pick_options(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[PickOptionProduct]:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")

    product_ids = [ln.product_id for ln in req.lines]
    if not product_ids:
        return []

    scanned = await _scanned_qty_by_product(session, req.id)
    bal_rows = await inventory_service.list_location_balances_for_products_in_warehouse(
        session,
        tenant_id,
        req.warehouse_id,
        product_ids,
    )
    loc_by_product: dict[uuid.UUID, list[PickOptionLocation]] = {pid: [] for pid in product_ids}
    for pid, loc_id, code, on_hand, rsv in bal_rows:
        loc_by_product.setdefault(pid, []).append(
            PickOptionLocation(
                storage_location_id=loc_id,
                location_code=code,
                quantity=on_hand,
                reserved=rsv,
                available=max(0, on_hand - rsv),
            )
        )

    out: list[PickOptionProduct] = []
    for ln in req.lines:
        p = ln.product
        out.append(
            PickOptionProduct(
                product_id=ln.product_id,
                sku_code=p.sku_code,
                product_name=p.name,
                scanned_qty=scanned.get(ln.product_id, 0),
                locations=loc_by_product.get(ln.product_id, []),
            )
        )
    return out


async def list_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[MarketplaceUnloadPickAllocation]:
    req = await session.get(MarketplaceUnloadRequest, request_id)
    if req is None or req.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("not_found")
    stmt = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.request_id == request_id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
        .order_by(MarketplaceUnloadPickAllocation.created_at.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def save_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    rows: list[PickAllocationRow],
) -> list[MarketplaceUnloadPickAllocation]:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status not in PICK_EDITABLE_STATUSES:
        raise MarketplaceUnloadPickError("not_editable")

    line_products = {ln.product_id for ln in req.lines}
    if not line_products:
        raise MarketplaceUnloadPickError("no_lines")

    scanned = await _scanned_qty_by_product(session, req.id)
    pick_sum: dict[uuid.UUID, int] = {}
    for row in rows:
        if row.quantity < 1:
            raise MarketplaceUnloadPickError("invalid_quantity")
        if row.product_id not in line_products:
            raise MarketplaceUnloadPickError("product_not_in_shipment")
        loc = await session.get(StorageLocation, row.storage_location_id)
        if loc is None or loc.tenant_id != tenant_id or loc.warehouse_id != req.warehouse_id:
            raise MarketplaceUnloadPickError("location_not_found")
        prod = await session.get(Product, row.product_id)
        if prod is None or prod.tenant_id != tenant_id:
            raise MarketplaceUnloadPickError("product_not_found")
        if req.seller_id is not None and prod.seller_id != req.seller_id:
            raise MarketplaceUnloadPickError("product_seller_mismatch")
        if (
            await inventory_service.available_at_location(
                session, tenant_id, row.product_id, row.storage_location_id
            )
            < row.quantity
        ):
            raise MarketplaceUnloadPickError("insufficient_available")
        pick_sum[row.product_id] = pick_sum.get(row.product_id, 0) + row.quantity

    for pid in line_products:
        need = scanned.get(pid, 0)
        if need < 1:
            raise MarketplaceUnloadPickError("scans_required")
        got = pick_sum.get(pid, 0)
        if got != need:
            raise MarketplaceUnloadPickError("pick_scan_mismatch")

    await session.execute(
        delete(MarketplaceUnloadPickAllocation).where(
            MarketplaceUnloadPickAllocation.request_id == request_id
        )
    )
    created: list[MarketplaceUnloadPickAllocation] = []
    for row in rows:
        if row.quantity < 1:
            continue
        alloc = MarketplaceUnloadPickAllocation(
            request_id=request_id,
            product_id=row.product_id,
            storage_location_id=row.storage_location_id,
            quantity=row.quantity,
        )
        session.add(alloc)
        created.append(alloc)
    await session.commit()
    return await list_pick_allocations(session, tenant_id, request_id)


async def ship_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status != mu_svc.STATUS_CONFIRMED:
        raise MarketplaceUnloadPickError("bad_status")
    if not req.lines:
        raise MarketplaceUnloadPickError("no_lines")

    open_box = await session.execute(
        select(MarketplaceUnloadBox.id).where(
            MarketplaceUnloadBox.request_id == request_id,
            MarketplaceUnloadBox.closed_at.is_(None),
        )
    )
    if open_box.scalar_one_or_none() is not None:
        raise MarketplaceUnloadPickError("open_box_exists")

    scanned = await _scanned_qty_by_product(session, req.id)
    for ln in req.lines:
        if scanned.get(ln.product_id, 0) < 1:
            raise MarketplaceUnloadPickError("scans_required")

    allocs = await list_pick_allocations(session, tenant_id, request_id)
    if not allocs:
        raise MarketplaceUnloadPickError("pick_required")

    pick_sum: dict[uuid.UUID, int] = {}
    for a in allocs:
        pick_sum[a.product_id] = pick_sum.get(a.product_id, 0) + int(a.quantity)

    for ln in req.lines:
        need = scanned.get(ln.product_id, 0)
        if pick_sum.get(ln.product_id, 0) != need:
            raise MarketplaceUnloadPickError("pick_scan_mismatch")

    for a in allocs:
        if (
            await inventory_service.available_at_location(
                session, tenant_id, a.product_id, a.storage_location_id
            )
            < int(a.quantity)
        ):
            raise MarketplaceUnloadPickError("insufficient_available")
        await inventory_service.apply_marketplace_unload_pick(
            session,
            tenant_id=tenant_id,
            product_id=a.product_id,
            storage_location_id=a.storage_location_id,
            quantity=int(a.quantity),
            marketplace_unload_request_id=req.id,
        )

    req.status = mu_svc.STATUS_SHIPPED
    await mu_svc.release_reservations_for_shipped(session, req.id)
    await session.commit()
    r2 = await mu_svc.get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2
