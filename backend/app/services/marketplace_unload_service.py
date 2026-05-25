from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, func, select
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
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services.catalog_service import get_warehouse
from app.services.wb_mp_warehouse_service import get_cached_mp_warehouse

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_CONFIRMED = "confirmed"
STATUS_SHIPPED = "shipped"

RESERVE_STATUSES = (STATUS_SUBMITTED, STATUS_CONFIRMED)
SELLER_EDITABLE_STATUSES = (STATUS_DRAFT,)
FF_LINE_EDITABLE_STATUSES = (STATUS_DRAFT, STATUS_CONFIRMED)


class MarketplaceUnloadError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def assert_request_visible(user: User, req: MarketplaceUnloadRequest) -> None:
    from app.core.roles import FULFILLMENT_SELLER

    if user.role == FULFILLMENT_SELLER:
        if user.seller_id is None or req.seller_id != user.seller_id:
            raise MarketplaceUnloadError("not_found")


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
        ff_modified=False,
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
    if req.status not in SELLER_EDITABLE_STATUSES:
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
            selectinload(MarketplaceUnloadRequest.lines).selectinload(
                MarketplaceUnloadLine.reservation
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
    *,
    seller_id: uuid.UUID | None = None,
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
    if seller_id is not None:
        stmt = stmt.where(MarketplaceUnloadRequest.seller_id == seller_id)
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def _mp_reserved_qty_for_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_request_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        select(func.coalesce(func.sum(MarketplaceUnloadReservation.quantity), 0))
        .join(
            MarketplaceUnloadLine,
            MarketplaceUnloadLine.id
            == MarketplaceUnloadReservation.marketplace_unload_line_id,
        )
        .join(
            MarketplaceUnloadRequest,
            MarketplaceUnloadRequest.id == MarketplaceUnloadLine.request_id,
        )
        .where(
            MarketplaceUnloadReservation.tenant_id == tenant_id,
            MarketplaceUnloadReservation.warehouse_id == warehouse_id,
            MarketplaceUnloadReservation.product_id == product_id,
            MarketplaceUnloadRequest.status.in_(RESERVE_STATUSES),
        )
    )
    if exclude_request_id is not None:
        stmt = stmt.where(MarketplaceUnloadRequest.id != exclude_request_id)
    return int(await session.scalar(stmt) or 0)


async def _available_product_qty_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_request_id: uuid.UUID | None = None,
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
    reserved_outbound_stmt = (
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
    reserved_outbound = int(await session.scalar(reserved_outbound_stmt) or 0)
    reserved_mp = await _mp_reserved_qty_for_product(
        session,
        tenant_id,
        warehouse_id,
        product_id,
        exclude_request_id=exclude_request_id,
    )
    return on_hand - reserved_outbound - reserved_mp


async def _release_reservations(session: AsyncSession, request_id: uuid.UUID) -> None:
    line_ids_stmt = select(MarketplaceUnloadLine.id).where(
        MarketplaceUnloadLine.request_id == request_id
    )
    res = await session.execute(line_ids_stmt)
    line_ids = [row[0] for row in res.all()]
    if not line_ids:
        return
    await session.execute(
        delete(MarketplaceUnloadReservation).where(
            MarketplaceUnloadReservation.marketplace_unload_line_id.in_(line_ids)
        )
    )


async def _apply_reservations(session: AsyncSession, req: MarketplaceUnloadRequest) -> None:
    await _release_reservations(session, req.id)
    for ln in req.lines:
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=req.tenant_id,
                marketplace_unload_line_id=ln.id,
                product_id=ln.product_id,
                warehouse_id=req.warehouse_id,
                quantity=int(ln.quantity),
            )
        )


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
    allow_ff_confirmed: bool = False,
) -> MarketplaceUnloadLine:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    editable = SELLER_EDITABLE_STATUSES if not allow_ff_confirmed else FF_LINE_EDITABLE_STATUSES
    if req.status not in editable:
        raise MarketplaceUnloadError("not_editable")
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise MarketplaceUnloadError("product_not_found")
    if req.seller_id is not None and prod.seller_id != req.seller_id:
        raise MarketplaceUnloadError("product_seller_mismatch")
    available_qty = await _available_product_qty_in_warehouse(
        session,
        tenant_id,
        req.warehouse_id,
        product_id,
        exclude_request_id=req.id if req.status in RESERVE_STATUSES else None,
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
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise MarketplaceUnloadError("duplicate_line") from None
    if allow_ff_confirmed and req.status == STATUS_CONFIRMED:
        req.ff_modified = True
    await session.commit()
    await session.refresh(line, attribute_names=["product"])
    return line


async def replace_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    lines: list[tuple[uuid.UUID, int]],
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_DRAFT:
        raise MarketplaceUnloadError("not_editable")

    normalized: dict[uuid.UUID, int] = {}
    for product_id, qty in lines:
        if qty < 1:
            continue
        normalized[product_id] = normalized.get(product_id, 0) + qty

    for product_id, qty in normalized.items():
        available_qty = await _available_product_qty_in_warehouse(
            session, tenant_id, req.warehouse_id, product_id
        )
        if available_qty < qty:
            raise MarketplaceUnloadError("insufficient_available")

    for ln in list(req.lines):
        await session.delete(ln)
    await session.flush()

    for product_id, qty in normalized.items():
        prod = await session.get(Product, product_id)
        if prod is None or prod.tenant_id != tenant_id:
            raise MarketplaceUnloadError("product_not_found")
        if req.seller_id is not None and prod.seller_id != req.seller_id:
            raise MarketplaceUnloadError("product_seller_mismatch")
        session.add(
            MarketplaceUnloadLine(
                request_id=req.id,
                product_id=product_id,
                quantity=qty,
            )
        )
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def plan_request(
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
    for ln in req.lines:
        available_qty = await _available_product_qty_in_warehouse(
            session,
            tenant_id,
            req.warehouse_id,
            ln.product_id,
            exclude_request_id=req.id,
        )
        if available_qty < ln.quantity:
            raise MarketplaceUnloadError("insufficient_available")
    await _apply_reservations(session, req)
    req.status = STATUS_SUBMITTED
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def unplan_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status != STATUS_SUBMITTED:
        raise MarketplaceUnloadError("bad_status")
    await _release_reservations(session, req.id)
    req.status = STATUS_DRAFT
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def confirm_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_shipment_date: date | None = None,
) -> MarketplaceUnloadRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    if req.status not in (STATUS_DRAFT, STATUS_SUBMITTED):
        raise MarketplaceUnloadError("bad_status")
    if req.wb_mp_warehouse_id is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_required")
    if not req.lines:
        raise MarketplaceUnloadError("no_lines")
    mpw = await get_cached_mp_warehouse(session, tenant_id, int(req.wb_mp_warehouse_id))
    if mpw is None:
        raise MarketplaceUnloadError("wb_mp_warehouse_unknown")
    if req.status == STATUS_DRAFT:
        for ln in req.lines:
            available_qty = await _available_product_qty_in_warehouse(
                session,
                tenant_id,
                req.warehouse_id,
                ln.product_id,
                exclude_request_id=req.id,
            )
            if available_qty < ln.quantity:
                raise MarketplaceUnloadError("insufficient_available")
        await _apply_reservations(session, req)
    req.planned_shipment_date = planned_shipment_date
    req.status = STATUS_CONFIRMED
    await session.commit()
    r2 = await get_request(session, tenant_id, request_id)
    assert r2 is not None
    return r2


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> MarketplaceUnloadRequest:
    """Legacy alias: FF confirms from draft or submitted."""
    return await confirm_request(session, tenant_id, request_id)


async def release_reservations_for_shipped(
    session: AsyncSession, request_id: uuid.UUID
) -> None:
    await _release_reservations(session, request_id)


async def delete_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    allow_ff_confirmed: bool = False,
) -> None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise MarketplaceUnloadError("not_found")
    editable = SELLER_EDITABLE_STATUSES if not allow_ff_confirmed else FF_LINE_EDITABLE_STATUSES
    if req.status not in editable:
        raise MarketplaceUnloadError("not_editable")
    line = await session.get(MarketplaceUnloadLine, line_id)
    if line is None or line.request_id != request_id:
        raise MarketplaceUnloadError("line_not_found")
    await session.delete(line)
    if allow_ff_confirmed and req.status == STATUS_CONFIRMED:
        req.ff_modified = True
    await session.commit()
