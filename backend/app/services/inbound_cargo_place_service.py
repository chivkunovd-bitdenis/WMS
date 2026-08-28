"""Product composition and operator notes for inbound cargo places."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_intake import (
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
)
from app.models.product import Product
from app.services import inbound_intake_service as intake_svc
from app.services.inbound_intake_service import InboundIntakeError


async def _load_cargo_place(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
) -> InboundIntakeCargoPlace:
    stmt = (
        select(InboundIntakeCargoPlace)
        .where(
            InboundIntakeCargoPlace.id == place_id,
            InboundIntakeCargoPlace.request_id == request_id,
            InboundIntakeCargoPlace.tenant_id == tenant_id,
        )
        .options(
            selectinload(InboundIntakeCargoPlace.lines).selectinload(
                InboundIntakeCargoPlaceLine.product
            )
        )
        .execution_options(populate_existing=True)
    )
    place = (await session.execute(stmt)).scalar_one_or_none()
    if place is None:
        raise InboundIntakeError("cargo_place_not_found")
    return place


async def set_line_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    quantity: int,
) -> InboundIntakeCargoPlace:
    """Create, replace, or remove one product row in an inbound cargo place."""
    if quantity < 0:
        raise InboundIntakeError("invalid_qty")
    request = await intake_svc.get_request(session, tenant_id, request_id)
    if request is None:
        raise InboundIntakeError("request_not_found")
    if request.status in intake_svc.DONE_STATUSES:
        raise InboundIntakeError("not_editable")
    place = await _load_cargo_place(session, tenant_id, request_id, place_id)
    if not any(line.product_id == product_id for line in request.lines):
        raise InboundIntakeError("product_not_on_request")
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise InboundIntakeError("product_not_found")

    line = next((row for row in place.lines if row.product_id == product_id), None)
    if line is not None and quantity < line.posted_qty:
        raise InboundIntakeError("actual_below_posted")
    if quantity == 0:
        if line is not None:
            await session.delete(line)
    elif line is None:
        session.add(
            InboundIntakeCargoPlaceLine(
                tenant_id=tenant_id,
                cargo_place_id=place.id,
                product_id=product_id,
                quantity=quantity,
            )
        )
    else:
        line.quantity = quantity
    await session.commit()
    return await _load_cargo_place(session, tenant_id, request_id, place_id)


async def update_free_text(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    place_id: uuid.UUID,
    *,
    free_text: str | None,
) -> InboundIntakeCargoPlace:
    place = await _load_cargo_place(session, tenant_id, request_id, place_id)
    place.free_text = free_text.strip() if free_text and free_text.strip() else None
    await session.commit()
    return await _load_cargo_place(session, tenant_id, request_id, place_id)
