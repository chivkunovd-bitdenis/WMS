"""Link internal Product rows to imported Wildberries card nm_id + size variant."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.wb_card_enrichment import WbSizeVariant, iter_size_variants_from_card


class WildberriesLinkError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _match_variant(
    variants: list[WbSizeVariant],
    *,
    wb_barcode: str | None,
    wb_chrt_id: int | None,
) -> WbSizeVariant:
    if wb_barcode and wb_barcode.strip():
        target = wb_barcode.strip()
        for v in variants:
            if v.barcode == target:
                return v
        raise WildberriesLinkError("wb_barcode_not_found")
    if wb_chrt_id is not None:
        for v in variants:
            if v.chrt_id == wb_chrt_id:
                return v
        raise WildberriesLinkError("wb_chrt_not_found")
    if len(variants) == 1:
        return variants[0]
    raise WildberriesLinkError("wb_size_required")


async def link_product_to_wb_card(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_id: uuid.UUID,
    nm_id: int,
    *,
    wb_barcode: str | None = None,
    wb_chrt_id: int | None = None,
) -> Product:
    p = await session.get(Product, product_id)
    if p is None or p.tenant_id != tenant_id:
        raise WildberriesLinkError("product_not_found")
    if p.seller_id is None:
        raise WildberriesLinkError("product_must_have_seller")
    if p.seller_id != seller_id:
        raise WildberriesLinkError("product_seller_mismatch")
    c_stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.seller_id == seller_id,
        SellerWildberriesImportedCard.nm_id == nm_id,
    )
    c_res = await session.execute(c_stmt)
    card = c_res.scalar_one_or_none()
    if card is None:
        raise WildberriesLinkError("wb_card_not_found")
    raw = card.raw_json if isinstance(card.raw_json, dict) else None
    if raw is None:
        raise WildberriesLinkError("wb_card_no_sizes")
    variants = iter_size_variants_from_card(raw)
    if not variants:
        raise WildberriesLinkError("wb_card_no_sizes")
    variant = _match_variant(variants, wb_barcode=wb_barcode, wb_chrt_id=wb_chrt_id)

    taken = await session.execute(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.wb_barcode == variant.barcode,
            Product.id != product_id,
        )
    )
    if taken.scalar_one_or_none() is not None:
        raise WildberriesLinkError("wb_barcode_already_linked")

    p.wb_nm_id = nm_id
    p.wb_vendor_code = card.vendor_code
    p.wb_chrt_id = variant.chrt_id
    p.wb_barcode = variant.barcode
    p.wb_size = variant.size_label
    await session.commit()
    await session.refresh(p, attribute_names=["seller"])
    return p
