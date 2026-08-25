"""Resolve an Ozon marking to one exact product position without guessing."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderProduct


@dataclass(frozen=True)
class OzonMarkingPositionError(Exception):
    code: str
    message: str


async def marking_position_sku(
    session: AsyncSession,
    order: FbsOrder,
    marking: FbsOrderMarking,
) -> int | None:
    if marking.order_product_id is not None:
        position = await session.scalar(
            select(FbsOrderProduct).where(
                FbsOrderProduct.id == marking.order_product_id,
                FbsOrderProduct.order_id == order.id,
            )
        )
        if position is None:
            raise OzonMarkingPositionError(
                "ozon_marking_position_invalid",
                "Позиция кода маркировки не входит в это отправление Ozon.",
            )
        if position.ozon_sku is None:
            raise OzonMarkingPositionError(
                "ozon_product_id_missing",
                "У позиции кода маркировки нет числового Ozon SKU.",
            )
        return int(position.ozon_sku)

    positions = list(
        (
            await session.execute(
                select(FbsOrderProduct)
                .where(FbsOrderProduct.order_id == order.id)
                .order_by(FbsOrderProduct.position_index)
            )
        )
        .scalars()
        .all()
    )
    if len(positions) > 1:
        raise OzonMarkingPositionError(
            "ozon_marking_position_missing",
            "Код маркировки не привязан к позиции многотоварного отправления Ozon.",
        )
    if not positions:
        return None
    if positions[0].ozon_sku is None:
        raise OzonMarkingPositionError(
            "ozon_product_id_missing",
            "У позиции кода маркировки нет числового Ozon SKU.",
        )
    marking.order_product_id = positions[0].id
    return int(positions[0].ozon_sku)
