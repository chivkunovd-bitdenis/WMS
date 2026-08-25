"""Resolve an Ozon marking to one exact product position without guessing."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderProduct
from app.models.marking_code import MarkingCode
from app.models.product import Product


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


def _barcode_matches_gtin(barcode: str | None, gtin: str) -> bool:
    if barcode is None:
        return False
    digits = "".join(char for char in barcode if char.isdigit())
    return bool(digits) and digits.lstrip("0") == gtin.lstrip("0")


async def resolve_marking_position(
    session: AsyncSession,
    order: FbsOrder,
    value: str,
) -> FbsOrderProduct:
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
    if len(positions) == 1:
        return positions[0]
    if not positions:
        raise OzonMarkingPositionError(
            "ozon_marking_position_missing",
            "В отправлении Ozon нет товарных позиций для маркировки.",
        )

    code = await session.scalar(
        select(MarkingCode).where(
            MarkingCode.tenant_id == order.tenant_id,
            MarkingCode.cis_code == value,
        )
    )
    if code is not None and code.product_id is not None:
        matches = [position for position in positions if position.product_id == code.product_id]
        if len(matches) == 1:
            return matches[0]

    gtin = value[2:16] if value.startswith("01") and len(value) >= 16 else ""
    product_ids = [position.product_id for position in positions if position.product_id is not None]
    products = {
        product.id: product
        for product in (
            (
                await session.execute(select(Product).where(Product.id.in_(product_ids)))
            )
            .scalars()
            .all()
            if product_ids
            else []
        )
    }
    matches = [
        position
        for position in positions
        if position.product_id is not None
        and (product := products.get(position.product_id)) is not None
        and _barcode_matches_gtin(product.wb_barcode, gtin)
    ]
    if len(matches) == 1:
        return matches[0]
    raise OzonMarkingPositionError(
        "ozon_marking_product_ambiguous",
        "Не удалось определить позицию Ozon для этого кода маркировки.",
    )


async def choose_exemplar_id(
    session: AsyncSession,
    marking: FbsOrderMarking,
    exemplar_ids: list[int],
) -> int | None:
    desired = (marking.meta_details_json or {}).get("exemplar_id")
    if isinstance(desired, int) and desired in exemplar_ids:
        return desired
    if marking.order_product_id is None:
        return exemplar_ids[0] if exemplar_ids else None
    siblings = list(
        (
            await session.execute(
                select(FbsOrderMarking).where(
                    FbsOrderMarking.order_product_id == marking.order_product_id,
                    FbsOrderMarking.id != marking.id,
                    FbsOrderMarking.meta_status != "rejected",
                )
            )
        )
        .scalars()
        .all()
    )
    used = {
        exemplar_id
        for sibling in siblings
        if isinstance(
            exemplar_id := (sibling.meta_details_json or {}).get("exemplar_id"), int
        )
    }
    return next((exemplar_id for exemplar_id in exemplar_ids if exemplar_id not in used), None)
