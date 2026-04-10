from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
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
    session: AsyncSession, tenant_id: uuid.UUID, *, warehouse_id: uuid.UUID
) -> InboundIntakeRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise InboundIntakeError("warehouse_not_found")
    req = InboundIntakeRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        status=STATUS_DRAFT,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def list_requests(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[InboundIntakeRequest]:
    stmt = (
        select(InboundIntakeRequest)
        .where(InboundIntakeRequest.tenant_id == tenant_id)
        .options(selectinload(InboundIntakeRequest.lines))
        .order_by(InboundIntakeRequest.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def get_request(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID
) -> InboundIntakeRequest | None:
    stmt = (
        select(InboundIntakeRequest)
        .where(
            InboundIntakeRequest.id == request_id,
            InboundIntakeRequest.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeRequest.lines).selectinload(
                InboundIntakeLine.product
            ),
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    expected_qty: int,
) -> InboundIntakeLine:
    if expected_qty < 1:
        raise InboundIntakeError("invalid_qty")
    req = await get_request(session, tenant_id, request_id)
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
    line = InboundIntakeLine(
        request_id=request_id,
        product_id=product_id,
        expected_qty=expected_qty,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise InboundIntakeError("duplicate_line") from exc
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


async def post_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    *,
    storage_location_id: uuid.UUID,
) -> InboundIntakeRequest:
    """Проведение приёмки: прибавить количества в одну ячейку склада заявки."""
    req = await get_request(session, tenant_id, request_id)
    if req is None:
        raise InboundIntakeError("request_not_found")
    if req.status != STATUS_SUBMITTED:
        raise InboundIntakeError("not_submitted")
    loc = await get_storage_location_in_warehouse(
        session, tenant_id, req.warehouse_id, storage_location_id
    )
    if loc is None:
        raise InboundIntakeError("location_not_found")
    now = datetime.now(UTC)
    for line in req.lines:
        stmt = select(InventoryBalance).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.storage_location_id == storage_location_id,
            InventoryBalance.product_id == line.product_id,
        )
        bal_res = await session.execute(stmt)
        existing = bal_res.scalar_one_or_none()
        if existing is None:
            session.add(
                InventoryBalance(
                    tenant_id=tenant_id,
                    storage_location_id=storage_location_id,
                    product_id=line.product_id,
                    quantity=line.expected_qty,
                )
            )
        else:
            existing.quantity += line.expected_qty
            existing.updated_at = now
    req.status = STATUS_POSTED
    req.posted_at = now
    await session.commit()
    await session.refresh(req)
    return req
