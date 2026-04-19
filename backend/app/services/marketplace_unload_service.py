from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.product import Product
from app.models.seller import Seller
from app.services.catalog_service import get_warehouse

STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"


class MarketplaceUnloadError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    warehouse_id: uuid.UUID,
    seller_id: uuid.UUID | None = None,
) -> MarketplaceUnloadRequest:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise MarketplaceUnloadError("warehouse_not_found")
    if seller_id is not None:
        sl = await session.get(Seller, seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise MarketplaceUnloadError("seller_not_found")
    req = MarketplaceUnloadRequest(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        status=STATUS_DRAFT,
    )
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


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
