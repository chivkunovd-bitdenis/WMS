from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_movement import MOVEMENT_TYPE_INBOUND_INTAKE
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


class InboundIntakeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
) -> InboundIntakeRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise InboundIntakeError("warehouse_not_found")
    if seller_id is not None:
        sl = await session.get(Seller, seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise InboundIntakeError("seller_not_found")
    req = InboundIntakeRequest(
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
) -> list[InboundIntakeRequest]:
    stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.tenant_id == tenant_id)
        .options(selectinload(InboundIntakeRequest.lines))
        .order_by(InboundIntakeRequest.created_at.desc())
    )
    if seller_product_owner_id is not None:
        stmt = stmt.where(
            InboundIntakeRequest.seller_id == seller_product_owner_id,
        )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def get_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeRequest | None:
    stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeRequest.lines).options(
                selectinload(InboundIntakeLine.product),
                selectinload(InboundIntakeLine.storage_location),
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
) -> tuple[InboundIntakeRequest, InboundIntakeLine] | None:
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
    expected_qty: int,
    storage_location_id: uuid.UUID | None = None,
    seller_product_owner_id: uuid.UUID | None = None,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    req = await get_request(
        session,
        tenant_id,
        request_id,
        seller_product_owner_id=seller_product_owner_id,
    )
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    prod_stmt = select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant_id,
    )
    prod_res = await session.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if product is None:
        raise InboundIntakeError("product_not_found")
    if (
        seller_product_owner_id is not None
        and product.seller_id != seller_product_owner_id
    ):
        raise InboundIntakeError("product_seller_mismatch")
    if req.seller_id is None:
        req.seller_id = product.seller_id
    elif product.seller_id != req.seller_id:
        raise InboundIntakeError("mixed_seller_lines")
    loc_id: uuid.UUID | None = None
    if storage_location_id is not None:
        loc = await get_storage_location_in_warehouse(
            session, tenant_id, req.warehouse_id, storage_location_id
        )
        if loc is None:
            raise InboundIntakeError("location_not_found")
        loc_id = storage_location_id
    line = InboundIntakeLine(
        request_id=request_id,
        product_id=product_id,
        expected_qty=expected_qty,
        posted_qty=0,
        storage_location_id=loc_id,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise InboundIntakeError("duplicate_line") from exc
    await session.refresh(line)
    return line


async def set_line_storage_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
) -> InboundIntakeLine:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status not in (STATUS_DRAFT, STATUS_SUBMITTED):
        raise InboundIntakeError("not_editable")
    if line.posted_qty >= line.expected_qty:
        raise InboundIntakeError("line_closed")
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    line.storage_location_id = storage_location_id
    await session.commit()
    await session.refresh(line)
    return line


async def submit_request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_DRAFT:
        raise InboundIntakeError("not_draft")
    if len(req.lines) == 0:
        raise InboundIntakeError("submit_empty")
    req.status = STATUS_SUBMITTED
    req.submitted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(req)
    return req


def _maybe_complete_request(req: InboundIntakeRequest) -> None:
    if all(ln.posted_qty >= ln.expected_qty for ln in req.lines):
        req.status = STATUS_POSTED
        if req.posted_at is None:
            req.posted_at = datetime.now(UTC)


async def receive_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    *,
    quantity: int,
) -> InboundIntakeRequest:
    pair = await _line_on_request(session, tenant_id, request_id, line_id)
    if pair is None:
        raise InboundIntakeError("line_not_found")
    req, line = pair
    if req.status == STATUS_POSTED:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SUBMITTED:
        raise InboundIntakeError("not_submitted")
    remaining = line.expected_qty - line.posted_qty
    if remaining <= 0:
        raise InboundIntakeError("nothing_to_receive")
    if line.storage_location_id is None:
        raise InboundIntakeError("storage_not_assigned")
    if quantity < 1 or quantity > remaining:
        raise InboundIntakeError("invalid_qty")
    sid = line.storage_location_id
    await inv_svc.apply_inbound_receive(
        session,
        tenant_id=tenant_id,
        product_id=line.product_id,
        storage_location_id=sid,
        quantity=quantity,
        movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
        inbound_intake_line_id=line.id,
    )
    line.posted_qty += quantity
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req


async def post_all_remaining(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
) -> InboundIntakeRequest:
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status == STATUS_POSTED:
        raise InboundIntakeError("already_posted")
    if req.status != STATUS_SUBMITTED:
        raise InboundIntakeError("not_submitted")
    to_receive: list[tuple[InboundIntakeLine, int]] = []
    for line in req.lines:
        rem = line.expected_qty - line.posted_qty
        if rem <= 0:
            continue
        if line.storage_location_id is None:
            raise InboundIntakeError("lines_missing_storage")
        to_receive.append((line, rem))
    if not to_receive:
        raise InboundIntakeError("nothing_to_receive")
    for line, rem in to_receive:
        sid = line.storage_location_id
        assert sid is not None
        await inv_svc.apply_inbound_receive(
            session,
            tenant_id=tenant_id,
            product_id=line.product_id,
            storage_location_id=sid,
            quantity=rem,
            movement_type=MOVEMENT_TYPE_INBOUND_INTAKE,
            inbound_intake_line_id=line.id,
        )
        line.posted_qty += rem
    _maybe_complete_request(req)
    await session.commit()
    await session.refresh(req)
    return req
