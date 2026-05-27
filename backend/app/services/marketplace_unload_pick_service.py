"""Pick allocations and ship (stock deduction) for marketplace unload."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import (
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from app.services import marketplace_unload_service as mu_svc
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

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
    planned_qty: int
    picked_qty: int
    locations: list[PickOptionLocation]


@dataclass(frozen=True)
class PickScanResult:
    kind: Literal["location", "product"]
    storage_location_id: uuid.UUID | None = None
    location_code: str | None = None
    product_id: uuid.UUID | None = None
    sku_code: str | None = None
    product_name: str | None = None
    picked_qty: int | None = None
    allocation_quantity: int | None = None


async def _picked_qty_by_product(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    stmt = (
        select(
            MarketplaceUnloadPickAllocation.product_id,
            func.coalesce(func.sum(MarketplaceUnloadPickAllocation.quantity), 0),
        )
        .where(MarketplaceUnloadPickAllocation.request_id == request_id)
        .group_by(MarketplaceUnloadPickAllocation.product_id)
    )
    res = await session.execute(stmt)
    return {row[0]: int(row[1]) for row in res.all()}


async def _barcode_index_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> dict[str, uuid.UUID]:
    rows = await list_seller_wb_catalog_rows(session, tenant_id, seller_id)
    idx: dict[str, uuid.UUID] = {}
    for r in rows:
        for b in r.wb_barcodes:
            key = str(b).strip()
            if key:
                idx[key] = r.product_id
        if r.wb_primary_barcode:
            k = r.wb_primary_barcode.strip()
            if k:
                idx[k] = r.product_id
    return idx


async def _request_for_picking(
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


async def find_location_by_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    barcode: str,
) -> StorageLocation | None:
    raw = barcode.strip()
    if not raw:
        return None
    stmt = select(StorageLocation).where(
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.warehouse_id == warehouse_id,
        StorageLocation.barcode == raw,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_pick_options(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> list[PickOptionProduct]:
    req = await _request_for_picking(session, tenant_id, request_id)
    product_ids = [ln.product_id for ln in req.lines]
    if not product_ids:
        return []

    picked = await _picked_qty_by_product(session, req.id)
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
                planned_qty=int(ln.quantity),
                picked_qty=picked.get(ln.product_id, 0),
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


async def add_pick_qty(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadPickAllocation:
    if quantity < 1:
        raise MarketplaceUnloadPickError("invalid_quantity")

    req = await _request_for_picking(session, tenant_id, request_id)
    line_products = {ln.product_id: int(ln.quantity) for ln in req.lines}
    if product_id not in line_products:
        raise MarketplaceUnloadPickError("product_not_in_shipment")

    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id or loc.warehouse_id != req.warehouse_id:
        raise MarketplaceUnloadPickError("location_not_found")

    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadPickError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadPickError("product_seller_mismatch")

    stmt = select(MarketplaceUnloadPickAllocation).where(
        MarketplaceUnloadPickAllocation.request_id == request_id,
        MarketplaceUnloadPickAllocation.product_id == product_id,
        MarketplaceUnloadPickAllocation.storage_location_id == storage_location_id,
    )
    res = await session.execute(stmt)
    alloc = res.scalar_one_or_none()
    current = int(alloc.quantity) if alloc is not None else 0
    new_qty = current + quantity

    available = await inventory_service.available_at_location(
        session, tenant_id, product_id, storage_location_id
    )
    if available < new_qty:
        raise MarketplaceUnloadPickError("insufficient_available")

    if alloc is None:
        alloc = MarketplaceUnloadPickAllocation(
            request_id=request_id,
            product_id=product_id,
            storage_location_id=storage_location_id,
            quantity=new_qty,
        )
        session.add(alloc)
    else:
        alloc.quantity = new_qty

    await session.commit()
    stmt2 = (
        select(MarketplaceUnloadPickAllocation)
        .where(MarketplaceUnloadPickAllocation.id == alloc.id)
        .options(
            selectinload(MarketplaceUnloadPickAllocation.product),
            selectinload(MarketplaceUnloadPickAllocation.storage_location),
        )
    )
    res2 = await session.execute(stmt2)
    return res2.scalar_one()


async def pick_scan(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    barcode: str,
    storage_location_id: uuid.UUID | None,
) -> PickScanResult:
    raw = barcode.strip()
    if not raw:
        raise MarketplaceUnloadPickError("barcode_empty")

    req = await _request_for_picking(session, tenant_id, request_id)

    loc = await find_location_by_barcode(session, tenant_id, req.warehouse_id, raw)
    if loc is not None:
        return PickScanResult(
            kind="location",
            storage_location_id=loc.id,
            location_code=loc.code,
        )

    if storage_location_id is None:
        raise MarketplaceUnloadPickError("location_required")

    if req.seller_id is None:
        raise MarketplaceUnloadPickError("seller_required")
    idx = await _barcode_index_for_seller(session, tenant_id, req.seller_id)
    product_id = idx.get(raw)
    if product_id is None:
        raise MarketplaceUnloadPickError("barcode_unknown")

    alloc = await add_pick_qty(
        session,
        tenant_id,
        request_id,
        storage_location_id=storage_location_id,
        product_id=product_id,
        quantity=1,
    )
    picked = await _picked_qty_by_product(session, request_id)
    p = alloc.product
    return PickScanResult(
        kind="product",
        storage_location_id=storage_location_id,
        product_id=product_id,
        sku_code=p.sku_code,
        product_name=p.name,
        picked_qty=picked.get(product_id, 0),
        allocation_quantity=int(alloc.quantity),
    )


async def save_pick_allocations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    rows: list[PickAllocationRow],
) -> list[MarketplaceUnloadPickAllocation]:
    req = await _request_for_picking(session, tenant_id, request_id)
    line_products = {ln.product_id for ln in req.lines}
    if not line_products:
        raise MarketplaceUnloadPickError("no_lines")

    merged: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for row in rows:
        if row.quantity < 1:
            raise MarketplaceUnloadPickError("invalid_quantity")
        if row.product_id not in line_products:
            raise MarketplaceUnloadPickError("product_not_in_shipment")
        key = (row.product_id, row.storage_location_id)
        merged[key] = merged.get(key, 0) + row.quantity

    for (product_id, loc_id), qty in merged.items():
        loc = await session.get(StorageLocation, loc_id)
        if loc is None or loc.tenant_id != tenant_id or loc.warehouse_id != req.warehouse_id:
            raise MarketplaceUnloadPickError("location_not_found")
        prod = await session.get(Product, product_id)
        if prod is None or prod.tenant_id != tenant_id:
            raise MarketplaceUnloadPickError("product_not_found")
        if req.seller_id is not None and prod.seller_id != req.seller_id:
            raise MarketplaceUnloadPickError("product_seller_mismatch")
        if (
            await inventory_service.available_at_location(
                session, tenant_id, product_id, loc_id
            )
            < qty
        ):
            raise MarketplaceUnloadPickError("insufficient_available")

    await session.execute(
        delete(MarketplaceUnloadPickAllocation).where(
            MarketplaceUnloadPickAllocation.request_id == request_id
        )
    )
    for (product_id, loc_id), qty in merged.items():
        session.add(
            MarketplaceUnloadPickAllocation(
                request_id=request_id,
                product_id=product_id,
                storage_location_id=loc_id,
                quantity=qty,
            )
        )
    await session.commit()
    return await list_pick_allocations(session, tenant_id, request_id)


def has_pick_discrepancy(req: MarketplaceUnloadRequest) -> bool:
    picked: dict[uuid.UUID, int] = {}
    for a in req.pick_allocations:
        picked[a.product_id] = picked.get(a.product_id, 0) + int(a.quantity)
    return any(picked.get(ln.product_id, 0) != int(ln.quantity) for ln in req.lines)


async def ship_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    acknowledge_discrepancy: bool = False,
) -> MarketplaceUnloadRequest:
    req = await mu_svc.get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadPickError("not_found")
    if req.status != mu_svc.STATUS_CONFIRMED:
        raise MarketplaceUnloadPickError("bad_status")
    if not req.lines:
        raise MarketplaceUnloadPickError("no_lines")

    allocs = await list_pick_allocations(session, tenant_id, request_id)
    if not allocs:
        raise MarketplaceUnloadPickError("pick_required")

    pick_sum: dict[uuid.UUID, int] = {}
    for a in allocs:
        pick_sum[a.product_id] = pick_sum.get(a.product_id, 0) + int(a.quantity)

    if sum(pick_sum.values()) < 1:
        raise MarketplaceUnloadPickError("pick_required")

    for ln in req.lines:
        if pick_sum.get(ln.product_id, 0) < 1:
            raise MarketplaceUnloadPickError("pick_required")

    if has_pick_discrepancy(req) and not acknowledge_discrepancy:
        raise MarketplaceUnloadPickError("discrepancy_requires_ack")

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


async def picked_qty_for_lines(
    session: AsyncSession, request_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    return await _picked_qty_by_product(session, request_id)
