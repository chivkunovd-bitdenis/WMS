from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_movement import InventoryMovement
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.models.seller import Seller
from app.services import inventory_service as inv_svc
from app.services.catalog_service import (
    get_storage_location_in_warehouse,
    get_warehouse,
)

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_POSTED = "posted"


class OutboundShipmentError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
) -> OutboundShipmentRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise OutboundShipmentError("warehouse_not_found")
    if seller_id is not None:
        sl = await session.get(Seller, seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise OutboundShipmentError("seller_not_found")
    req = OutboundShipmentRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        status=STATUS_DRAFT,
        seller_id=seller_id,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[OutboundShipmentRequest]:
    stmt = (
        select(OutboundShipmentRequest)
        .where(OutboundShipmentRequest.tenant_id == tenant_id)
        .options(
            selectinload(OutboundShipmentRequest.lines),
            selectinload(OutboundShipmentRequest.warehouse),
            selectinload(OutboundShipmentRequest.seller),
        )
        .order_by(OutboundShipmentRequest.created_at.desc())
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(
            OutboundShipmentRequest.seller_id == seller_product_owner_id,
        )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> OutboundShipmentRequest | None:
    stmt = (
        select(OutboundShipmentRequest)
        .where(
            OutboundShipmentRequest.id == request_id,
            OutboundShipmentRequest.tenant_id == tenant_id,
        )
        .options(
            selectinload(OutboundShipmentRequest.lines).options(
                selectinload(OutboundShipmentLine.product),
                selectinload(OutboundShipmentLine.storage_location),
            ),
        )
    )
    res = await session.execute(stmt)
    req = res.scalar_one_or_none()
    if req is None:
        return None
    if (
        seller_product_owner_id is not None
        and req.seller_id != seller_product_owner_id
    ):
        return None
    return req


async def _line_on_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
) -> tuple[OutboundShipmentRequest, OutboundShipmentLine] | None:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        return None
    for ln in req.lines:
        if ln.id == line_id:
            return req, ln
    return None


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
    storage_location_id: uuid.UUID | None = None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> OutboundShipmentLine:
    if quantity < 1:
        raise OutboundShipmentError("invalid_qty")
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise OutboundShipmentError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise OutboundShipmentError("not_draft")
    prod_stmt = select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant_id,
    )
    prod_res = await session.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if product is None:
        raise OutboundShipmentError("product_not_found")
    if (
        seller_product_owner_id is not None
        and product.seller_id != seller_product_owner_id
    ):
        raise OutboundShipmentError("product_seller_mismatch")
    if req.seller_id is None:
        req.seller_id = product.seller_id
    elif product.seller_id != req.seller_id:
        raise OutboundShipmentError("mixed_seller_lines")
    loc_id: uuid.UUID | None = None
    if storage_location_id is not None:
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise OutboundShipmentError("location_not_found")
        loc_id = storage_location_id
    line = OutboundShipmentLine(
        request_id=request_id,
        product_id=product_id,
        quantity=quantity,
        shipped_qty=0,
        storage_location_id=loc_id,
    )
    session.add(line)
    try:
        await session.flush()
        await inv_svc.sync_outbound_line_reservation(session, tenant_id, req, line)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise OutboundShipmentError("duplicate_line") from exc
    except ValueError as exc:
        await session.rollback()
        if str(exc) == inv_svc.RESERVATION_ERROR:
            raise OutboundShipmentError("insufficient_available") from exc
        raise
    await session.refresh(line)
    return line


async def set_line_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
) -> OutboundShipmentLine:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise OutboundShipmentError("line_not_found")
    req, line = pair
    if req.status not in (STATUS_DRAFT, STATUS_SUBMITTED):
        raise OutboundShipmentError("not_editable")
    if line.shipped_qty >= line.quantity:
        raise OutboundShipmentError("line_closed")
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise OutboundShipmentError("location_not_found")
    line.storage_location_id = storage_location_id
    try:
        await inv_svc.sync_outbound_line_reservation(session, tenant_id, req, line)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        if str(exc) == inv_svc.RESERVATION_ERROR:
            raise OutboundShipmentError("insufficient_available") from exc
        raise
    await session.refresh(line)
    return line


async def delete_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
) -> OutboundShipmentRequest:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise OutboundShipmentError("line_not_found")
    req, line = pair
    if req.status != STATUS_DRAFT:
        raise OutboundShipmentError("not_draft")
    await session.delete(line)
    await session.flush()
    remaining = int(
        await session.scalar(
            select(func.count())
            .select_from(OutboundShipmentLine)
            .where(OutboundShipmentLine.request_id == request_id),
        )
        or 0,
    )
    if remaining == 0:
        root = await session.get(OutboundShipmentRequest, request_id)
        if root is not None:
            root.seller_id = None
    await session.commit()
    session.expire_all()
    out = await get_request(session, tenant_id, request_id)
    if out is None:
        raise OutboundShipmentError("request_not_found")
    return out


async def submit_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    planned_shipment_date: date | None = None,
) -> OutboundShipmentRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise OutboundShipmentError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise OutboundShipmentError("not_draft")
    if len(req.lines) == 0:
        raise OutboundShipmentError("submit_empty")
    try:
        for ln in req.lines:
            await inv_svc.sync_outbound_line_reservation(session, tenant_id, req, ln)
    except ValueError as exc:
        await session.rollback()
        if str(exc) == inv_svc.RESERVATION_ERROR:
            raise OutboundShipmentError("insufficient_available") from exc
        raise
    req.status = STATUS_SUBMITTED
    req.planned_shipment_date = (
        planned_shipment_date
        if planned_shipment_date is not None
        else datetime.now(UTC).date()
    )
    await session.commit()
    await session.refresh(req)
    return req


def _maybe_complete_request(req: OutboundShipmentRequest) -> None:
    if all(ln.shipped_qty >= ln.quantity for ln in req.lines):
        req.status = STATUS_POSTED
        if req.posted_at is None:
            req.posted_at = datetime.now(UTC)


async def ship_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int,
) -> OutboundShipmentRequest:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise OutboundShipmentError("line_not_found")
    req, line = pair
    if req.status == STATUS_POSTED:
        raise OutboundShipmentError("already_posted")
    if req.status != STATUS_SUBMITTED:
        raise OutboundShipmentError("not_submitted")
    remaining = line.quantity - line.shipped_qty
    if remaining <= 0:
        raise OutboundShipmentError("nothing_to_ship")
    if line.storage_location_id is None:
        raise OutboundShipmentError("storage_not_assigned")
    if quantity < 1 or quantity > remaining:
        raise OutboundShipmentError("invalid_qty")
    sid = line.storage_location_id
    try:
        await inv_svc.apply_outbound_shipment_line(
            session,
            tenant_id=tenant_id,
            product_id=line.product_id,
            storage_location_id=sid,
            quantity=quantity,
            outbound_shipment_line_id=line.id,
        )
    except ValueError:
        raise OutboundShipmentError("insufficient_stock") from None
    line.shipped_qty += quantity
    _maybe_complete_request(req)
    try:
        await inv_svc.sync_outbound_line_reservation(session, tenant_id, req, line)
    except ValueError as exc:
        await session.rollback()
        if str(exc) == inv_svc.RESERVATION_ERROR:
            raise OutboundShipmentError("insufficient_available") from exc
        raise
    await session.commit()
    await session.refresh(req)
    return req


async def post_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> OutboundShipmentRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise OutboundShipmentError("request_not_found")
    if req.status == STATUS_POSTED:
        raise OutboundShipmentError("already_posted")
    if req.status != STATUS_SUBMITTED:
        raise OutboundShipmentError("not_submitted")
    to_ship: list[tuple[OutboundShipmentLine, int]] = []
    for line in req.lines:
        rem = line.quantity - line.shipped_qty
        if rem <= 0:
            continue
        if line.storage_location_id is None:
            raise OutboundShipmentError("lines_missing_storage")
        to_ship.append((line, rem))
    if not to_ship:
        raise OutboundShipmentError("nothing_to_ship")
    for line, rem in to_ship:
        sid = line.storage_location_id
        assert sid is not None
        try:
            await inv_svc.apply_outbound_shipment_line(
                session,
                tenant_id=tenant_id,
                product_id=line.product_id,
                storage_location_id=sid,
                quantity=rem,
                outbound_shipment_line_id=line.id,
            )
        except ValueError:
            raise OutboundShipmentError("insufficient_stock") from None
        line.shipped_qty += rem
    try:
        for line in req.lines:
            await inv_svc.sync_outbound_line_reservation(session, tenant_id, req, line)
    except ValueError as exc:
        await session.rollback()
        if str(exc) == inv_svc.RESERVATION_ERROR:
            raise OutboundShipmentError("insufficient_available") from exc
        raise
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req


async def list_movements_for_outbound_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> list[InventoryMovement]:
    stmt = (
        select(InventoryMovement)
        .join(
            OutboundShipmentLine,
            OutboundShipmentLine.id == InventoryMovement.outbound_shipment_line_id,
        )
        .join(
            OutboundShipmentRequest,
            OutboundShipmentRequest.id == OutboundShipmentLine.request_id,
        )
        .where(
            OutboundShipmentRequest.tenant_id == tenant_id,
            OutboundShipmentRequest.id == request_id,
        )
    )
    if seller_product_owner_id is not None:
        stmt = stmt.join(Product, Product.id == OutboundShipmentLine.product_id).where(
            Product.seller_id == seller_product_owner_id,
        )
    stmt = stmt.order_by(InventoryMovement.created_at.desc())
    res = await session.execute(stmt)
    return list(res.scalars().all())
