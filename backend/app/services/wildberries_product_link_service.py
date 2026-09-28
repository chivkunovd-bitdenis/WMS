"""Link internal Product rows to imported Wildberries card nm_id + size variant."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.product_barcode_service import add_barcodes_to_product
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
            if target in v.barcodes:
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
) -> tuple[Product, list[str]]:
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
    if variant.chrt_id is None:
        raise WildberriesLinkError("wb_chrt_missing")

    chrt_taken = await session.execute(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_chrt_id == variant.chrt_id,
            Product.id != product_id,
        )
    )
    if chrt_taken.first() is not None:
        raise WildberriesLinkError("wb_chrt_already_linked")

    barcode_taken = await session.execute(
        select(Product.id)
        .outerjoin(
            ProductBarcode,
            (ProductBarcode.product_id == Product.id)
            & (ProductBarcode.tenant_id == tenant_id)
            & (ProductBarcode.seller_id == seller_id),
        )
        .where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.id != product_id,
            or_(
                Product.wb_barcode.in_(variant.barcodes),
                ProductBarcode.barcode.in_(variant.barcodes),
            ),
        )
    )
    if barcode_taken.first() is not None:
        raise WildberriesLinkError("wb_barcode_already_linked")

    identity_changed = p.wb_nm_id != nm_id or p.wb_chrt_id != variant.chrt_id
    previous_primary = p.wb_barcode.strip() if p.wb_barcode and p.wb_barcode.strip() else None
    explicit_primary = wb_barcode.strip() if wb_barcode and wb_barcode.strip() else None
    selected_primary = explicit_primary or variant.barcode
    if (
        explicit_primary is None
        and not identity_changed
        and previous_primary is not None
        and previous_primary in variant.barcodes
    ):
        selected_primary = previous_primary
    removed_barcodes: list[str] = []
    if identity_changed:
        removed_barcodes = list(
            dict.fromkeys(
                (
                    await session.execute(
                        select(ProductBarcode.barcode)
                        .where(
                            ProductBarcode.tenant_id == tenant_id,
                            ProductBarcode.seller_id == seller_id,
                            ProductBarcode.product_id == product_id,
                            ProductBarcode.source == "wb",
                            ProductBarcode.barcode.not_in(variant.barcodes),
                        )
                        .order_by(ProductBarcode.barcode)
                    )
                ).scalars()
            )
        )
        if previous_primary and previous_primary not in variant.barcodes:
            removed_barcodes = list(
                dict.fromkeys((*removed_barcodes, previous_primary))
            )
        await session.execute(
            delete(ProductBarcode).where(
                ProductBarcode.tenant_id == tenant_id,
                ProductBarcode.seller_id == seller_id,
                ProductBarcode.product_id == product_id,
                ProductBarcode.source == "wb",
                ProductBarcode.barcode.not_in(variant.barcodes),
            )
        )
    p.wb_nm_id = nm_id
    p.wb_vendor_code = card.vendor_code
    p.wb_chrt_id = variant.chrt_id
    p.wb_barcode = selected_primary
    p.wb_size = variant.size_label
    retained_barcodes = variant.barcodes
    if not identity_changed and previous_primary:
        retained_barcodes = tuple(
            dict.fromkeys((previous_primary, *retained_barcodes))
        )
    barcode_result = await add_barcodes_to_product(session, p, retained_barcodes)
    if barcode_result.conflicts:
        await session.rollback()
        raise WildberriesLinkError("wb_barcode_already_linked")
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise WildberriesLinkError("wb_barcode_already_linked") from exc
    await session.refresh(p, attribute_names=["seller"])
    return p, removed_barcodes
