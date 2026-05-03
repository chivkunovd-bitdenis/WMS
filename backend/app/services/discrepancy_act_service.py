from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.product import Product
from app.models.seller import Seller

STATUS_DRAFT = "draft"
STATUS_CONFIRMED = "confirmed"


class DiscrepancyActError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def create_act(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    inbound_intake_request_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
) -> DiscrepancyAct:
    resolved_seller_id = seller_id
    if inbound_intake_request_id is not None:
        inbound = await session.get(InboundIntakeRequest, inbound_intake_request_id)
        if inbound is None or inbound.tenant_id != tenant_id:
            raise DiscrepancyActError("inbound_not_found")
        if resolved_seller_id is None:
            resolved_seller_id = inbound.seller_id
    if resolved_seller_id is not None:
        sl = await session.get(Seller, resolved_seller_id)
        if sl is None or sl.tenant_id != tenant_id:
            raise DiscrepancyActError("seller_not_found")
    act = DiscrepancyAct(
        tenant_id=tenant_id,
        inbound_intake_request_id=inbound_intake_request_id,
        seller_id=resolved_seller_id,
        status=STATUS_DRAFT,
    )
    session.add(act)
    await session.commit()
    await session.refresh(act)
    return act


async def get_act(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    act_id: uuid.UUID,
) -> DiscrepancyAct | None:
    stmt = (
        select(DiscrepancyAct)
        .where(DiscrepancyAct.id == act_id)
        .where(DiscrepancyAct.tenant_id == tenant_id)
        .options(
            selectinload(DiscrepancyAct.inbound_intake_request),
            selectinload(DiscrepancyAct.seller),
            selectinload(DiscrepancyAct.lines).selectinload(DiscrepancyActLine.product),
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def list_acts(session: AsyncSession, tenant_id: uuid.UUID) -> list[DiscrepancyAct]:
    stmt = (
        select(DiscrepancyAct)
        .where(DiscrepancyAct.tenant_id == tenant_id)
        .options(
            selectinload(DiscrepancyAct.inbound_intake_request),
            selectinload(DiscrepancyAct.seller),
            selectinload(DiscrepancyAct.lines),
        )
        .order_by(DiscrepancyAct.created_at.desc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def add_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    act_id: uuid.UUID,
    *,
    product_id: uuid.UUID,
    quantity: int,
    inbound_intake_line_id: uuid.UUID | None = None,
) -> DiscrepancyActLine:
    act = await get_act(session, tenant_id, act_id)
    if act is None:
        raise DiscrepancyActError("not_found")
    if act.status != STATUS_DRAFT:
        raise DiscrepancyActError("not_editable")
    prod = await session.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise DiscrepancyActError("product_not_found")
    if inbound_intake_line_id is not None:
        if act.inbound_intake_request_id is None:
            raise DiscrepancyActError("inbound_link_required")
        il = await session.get(InboundIntakeLine, inbound_intake_line_id)
        if il is None or il.request_id != act.inbound_intake_request_id:
            raise DiscrepancyActError("inbound_line_not_found")
        if il.product_id != product_id:
            raise DiscrepancyActError("product_mismatch")
    line = DiscrepancyActLine(
        act_id=act.id,
        product_id=product_id,
        quantity=quantity,
        inbound_intake_line_id=inbound_intake_line_id,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DiscrepancyActError("duplicate_line") from None
    await session.refresh(line, attribute_names=["product"])
    return line


async def submit_act(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    act_id: uuid.UUID,
) -> DiscrepancyAct:
    act = await get_act(session, tenant_id, act_id)
    if act is None:
        raise DiscrepancyActError("not_found")
    if act.status != STATUS_DRAFT:
        raise DiscrepancyActError("bad_status")
    act.status = STATUS_CONFIRMED
    await session.commit()
    r2 = await get_act(session, tenant_id, act_id)
    assert r2 is not None
    return r2


async def delete_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    act_id: uuid.UUID,
    line_id: uuid.UUID,
) -> None:
    act = await get_act(session, tenant_id, act_id)
    if act is None:
        raise DiscrepancyActError("not_found")
    if act.status != STATUS_DRAFT:
        raise DiscrepancyActError("not_editable")
    line = await session.get(DiscrepancyActLine, line_id)
    if line is None or line.act_id != act_id:
        raise DiscrepancyActError("line_not_found")
    await session.delete(line)
    await session.commit()
