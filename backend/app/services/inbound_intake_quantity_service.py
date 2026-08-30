from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeCargoPlace,
    InboundIntakeCargoPlaceLine,
)


async def container_total_for_product(
    session: AsyncSession, request_id: uuid.UUID, product_id: uuid.UUID
) -> int:
    """Return product units recorded in boxes and cargo places of one intake."""
    box_quantities = (
        select(InboundIntakeBoxLine.quantity.label("quantity"))
        .join(InboundIntakeBox, InboundIntakeBoxLine.box_id == InboundIntakeBox.id)
        .where(
            InboundIntakeBox.request_id == request_id,
            InboundIntakeBoxLine.product_id == product_id,
        )
    )
    cargo_place_quantities = (
        select(InboundIntakeCargoPlaceLine.quantity.label("quantity"))
        .join(
            InboundIntakeCargoPlace,
            InboundIntakeCargoPlaceLine.cargo_place_id == InboundIntakeCargoPlace.id,
        )
        .where(
            InboundIntakeCargoPlace.request_id == request_id,
            InboundIntakeCargoPlaceLine.product_id == product_id,
        )
    )
    quantities = sa.union_all(box_quantities, cargo_place_quantities).subquery()
    total = await session.scalar(
        select(sa.func.coalesce(sa.func.sum(quantities.c.quantity), 0))
    )
    return int(total or 0)
