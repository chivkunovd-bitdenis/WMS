from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_balance import InventoryBalance
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.services.catalog_service import get_warehouse
from app.services.wb_mp_warehouse_service import get_cached_mp_warehouse

STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"
STATUS_SHIPPED = "shipped"


class MarketplaceUnloadError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_mp_warehouse_id: int | None,
) -> MarketplaceUnloadRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise MarketplaceUnloadError("warehouse_not_found")
    sl = await session.get(Seller, seller_id)
    if sl is None or sl.tenant_id != tenant_id:
        raise MarketplaceUnloadError("seller_not_found")
    if wb_mp_warehouse_id is not None:
        mpw = await get_cached_mp_warehouse(session, tenant_id, wb_mp_warehouse_id)
        if mpw is None:
            raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    req = MarketplaceUnloadRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        wb_mp_warehouse_id=wb_mp_warehouse_id,
        status=STATUS_DRAFT,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def set_wb_mp_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    wb_mp_warehouse_id: int,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("not_editable")
    mpw = await get_cached_mp_warehouse(session, tenant_id, wb_mp_warehouse_id)
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    req.wb_mp_warehouse_id = wb_mp_warehouse_id
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest | None:
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(MarketplaceUnloadRequest.id == request_id)
        .where(MarketplaceUnloadRequest.tenant_id == tenant_id)
        .options(
            selectinload(MarketplaceUnloadRequest.warehouse),
            selectinload(MarketplaceUnloadRequest.seller),
            selectinload(MarketplaceUnloadRequest.lines).selectinload(
                MarketplaceUnloadLine.product
            ),
            selectinload(MarketplaceUnloadRequest.boxes)
            .selectinload(MarketplaceUnloadBox.lines)
            .selectinload(MarketplaceUnloadBoxLine.product),
            selectinload(MarketplaceUnloadRequest.pick_allocations).selectinload(
                MarketplaceUnloadPickAllocation.product
            ),
            selectinload(MarketplaceUnloadRequest.pick_allocations).selectinload(
                MarketplaceUnloadPickAllocation.storage_location
            ),
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[MarketplaceUnloadRequest]:
    stmt = (
        select(MarketplaceUnloadRequest)
        .where(MarketplaceUnloadRequest.tenant_id == tenant_id)
        .options(
            selectinload(MarketplaceUnloadRequest.warehouse),
            selectinload(MarketplaceUnloadRequest.seller),
            selectinload(MarketplaceUnloadRequest.lines),
        )
        .order_by(MarketplaceUnloadRequest.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def _available_product_qty_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    on_hand_stmt = (
        select(func.coalesce(func.sum(InventoryBalance.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
    )
    reserved_stmt = (
        select(func.coalesce(func.sum(InventoryReservation.quantity), 0))
        .join(StorageLocation, StorageLocation.id == InventoryReservation.storage_location_id)
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryReservation.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .where(
            InventoryReservation.tenant_id == tenant_id,
            InventoryReservation.product_id == product_id,
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
            OutboundShipmentRequest.status.in_(("draft", "submitted")),
        )
    )
    on_hand = int(await session.scalar(on_hand_stmt) or 0)
    reserved = int(await session.scalar(reserved_stmt) or 0)
    return on_hand - reserved


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
) -> MarketplaceUnloadLine:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("not_editable")
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadError("product_seller_mismatch")
    available_qty = await _available_product_qty_in_warehouse(
        session, tenant_id, req.warehouse_id, product_id
    )
    if available_qty < quantity:
        raise MarketplaceUnloadError("insufficient_available")
    line = MarketplaceUnloadLine(
        request_id=req.id,
        product_id=product_id,
        quantity=quantity,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise MarketplaceUnloadError("duplicate_line") from None
    await session.refresh(line, attribute_names=["product"])
    return line


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("bad_status")
    if req.wb_mp_warehouse_id is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_required")
    if not req.lines:
        raise MarketplaceUnloadError("no_lines")
    mpw = await get_cached_mp_warehouse(session, tenant_id, int(req.wb_mp_warehouse_id))
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    req.status = STATUS_CONFIRMED
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def delete_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
) -> None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("not_editable")
    line = await session.get(MarketplaceUnloadLine, line_id)
    if line is None or line.request_id != request_id:
        raise MarketplaceUnloadError("line_not_found")
    await session.delete(line)
    await session.commit()
