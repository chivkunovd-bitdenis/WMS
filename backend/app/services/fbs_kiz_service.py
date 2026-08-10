"""FBS KIZ manual binding lookup by WB order sticker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    FBS_ORDER_MARKING_FROZEN_STATUSES,
    FBS_ORDER_MARKING_WRITE_STATUSES,
    MARKING_KIND_SGTIN,
    META_STATUS_REJECTED,
    FbsOrder,
    FbsOrderMarking,
)
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.wb_card_enrichment import first_photo_url_from_card

_MISSING_PRODUCT_NAME = "Товар не сопоставлен"
_POOL_MARKING_SOURCE = "pool"


class FbsKizError(Exception):
    def __init__(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.context = context or {}
        super().__init__(code)


@dataclass(frozen=True)
class FbsKizProduct:
    name: str
    image_url: str | None
    barcode: str | None
    seller_article: str | None


@dataclass(frozen=True)
class FbsKizCurrentMarking:
    masked: str
    meta_status: str
    from_pool: bool


@dataclass(frozen=True)
class FbsKizLookup:
    order_id: uuid.UUID
    wb_order_id: int
    product: FbsKizProduct
    current_kiz: FbsKizCurrentMarking | None
    needs_confirmation: bool
    can_bind: bool
    block_reason: str | None


def normalize_scanned_sticker(raw: str) -> str:
    """Normalize scanner noise for WB sticker matching."""
    stripped = raw.strip()
    return "".join(ch for ch in stripped if ch != "\ufeff" and not ch.isspace())


def _normalized_optional(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = normalize_scanned_sticker(raw)
    return normalized or None


def _find_order_by_sticker(orders: list[FbsOrder], sticker: str) -> FbsOrder | None:
    for order in orders:
        if _normalized_optional(order.sticker_code) == sticker:
            return order
    for order in orders:
        if _normalized_optional(order.wb_barcode) == sticker:
            return order
    # A third variant (partA+partB from the WB sticker) is deliberately not implemented:
    # we store neither part, and what the printed sticker's QR actually encodes is unknown
    # until the hardware check in TASK.md section 8. Add it together with persisting
    # partA/partB once a real scan proves it is needed.
    return None


def _current_sgtin_marking(order: FbsOrder) -> FbsOrderMarking | None:
    candidates = [
        marking
        for marking in order.markings
        if marking.kind == MARKING_KIND_SGTIN and marking.meta_status != META_STATUS_REJECTED
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda marking: (marking.created_at, marking.id.hex))


def _mask_kiz(value: str) -> str:
    return f"…{value[-6:]}"


async def _image_url_for_order(session: AsyncSession, order: FbsOrder) -> str | None:
    if order.wb_nm_id is None:
        return None
    stmt = (
        select(SellerWildberriesImportedCard.raw_json)
        .where(
            SellerWildberriesImportedCard.seller_id == order.seller_id,
            SellerWildberriesImportedCard.nm_id == int(order.wb_nm_id),
        )
        .limit(1)
    )
    raw = (await session.execute(stmt)).scalar_one_or_none()
    if isinstance(raw, dict):
        return first_photo_url_from_card(raw)
    return None


def _product_payload(order: FbsOrder, image_url: str | None) -> FbsKizProduct:
    product: Product | None = order.product
    barcode = order.wb_barcode or (product.wb_barcode if product is not None else None)
    seller_article = product.sku_code if product is not None else order.wb_article
    name = (
        product.name
        if product is not None
        else order.wb_article or _MISSING_PRODUCT_NAME
    )
    return FbsKizProduct(
        name=name,
        image_url=image_url,
        barcode=barcode,
        seller_article=seller_article,
    )


async def lookup_order_by_sticker(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    sticker: str,
) -> FbsKizLookup:
    normalized_sticker = normalize_scanned_sticker(sticker)
    if not normalized_sticker:
        raise FbsKizError("sticker_not_found")

    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.markings),
        )
        .order_by(FbsOrder.created_at, FbsOrder.id)
    )
    orders = list((await session.execute(stmt)).scalars().all())
    order = _find_order_by_sticker(orders, normalized_sticker)
    if order is None:
        raise FbsKizError("sticker_not_found")

    if (
        order.status in FBS_ORDER_MARKING_FROZEN_STATUSES
        or order.status not in FBS_ORDER_MARKING_WRITE_STATUSES
    ):
        raise FbsKizError("order_frozen", context={"order_id": str(order.id)})

    current = _current_sgtin_marking(order)
    current_out = (
        FbsKizCurrentMarking(
            masked=_mask_kiz(current.value),
            meta_status=current.meta_status,
            from_pool=current.source == _POOL_MARKING_SOURCE,
        )
        if current is not None
        else None
    )
    image_url = await _image_url_for_order(session, order)
    return FbsKizLookup(
        order_id=order.id,
        wb_order_id=int(order.wb_order_id),
        product=_product_payload(order, image_url),
        current_kiz=current_out,
        needs_confirmation=current_out is not None,
        can_bind=True,
        block_reason=None,
    )
