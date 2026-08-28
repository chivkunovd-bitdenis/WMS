from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.services.catalog_service import (
    DEFAULT_PRODUCT_DIM_MM,
    _dimension_fingerprint,
    _record_dimension_event,
    volume_liters_from_mm,
)
from app.services.wb_card_enrichment import (
    WbSizeVariant,
    country_of_origin_from_card,
    iter_size_variants_from_card,
    product_display_name,
    shelf_life_from_card,
    sku_code_for_wb_variant,
    subject_name_from_card,
)

OLD_SKU_PREFIX = "OLD/"
OLD_NAME_PREFIX = "[OLD] "


def is_legacy_old_sku(sku: str) -> bool:
    return sku.startswith(OLD_SKU_PREFIX)


async def _sku_taken(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID, sku: str
) -> bool:
    # Занятость считается внутри продавца: одинаковый артикул у разных продавцов —
    # норма, а не конфликт (см. uq_products_tenant_seller_sku).
    res = await session.execute(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.sku_code == sku,
        )
    )
    return res.first() is not None


async def _allocate_old_sku(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    original_sku: str,
) -> str:
    base = original_sku.strip()
    if is_legacy_old_sku(base):
        return base[:128]
    candidate = f"{OLD_SKU_PREFIX}{base}"[:128]
    if not await _sku_taken(session, tenant_id, seller_id, candidate):
        return candidate
    for n in range(2, 100):
        alt = f"{OLD_SKU_PREFIX}{base}-{n}"[:128]
        if not await _sku_taken(session, tenant_id, seller_id, alt):
            return alt
    return f"{OLD_SKU_PREFIX}{base[:8]}-{uuid.uuid4().hex[:6]}"[:128]


async def _mark_legacy_products_for_card(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    nm: int | None,
    *,
    multi_variant: bool,
) -> int:
    """Pre-split merged SKU (one row per nmID) → ``OLD/…`` + ``[OLD]`` name."""
    if nm is None or not multi_variant:
        return 0
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.seller_id == seller_id,
        Product.wb_nm_id == nm,
        Product.wb_barcode.is_(None),
    )
    res = await session.execute(stmt)
    rows = list(res.scalars().all())
    marked = 0
    for p in rows:
        if is_legacy_old_sku(p.sku_code):
            continue
        p.sku_code = await _allocate_old_sku(session, tenant_id, seller_id, p.sku_code)
        if not p.name.startswith(OLD_NAME_PREFIX):
            p.name = f"{OLD_NAME_PREFIX}{p.name}"[:255]
        marked += 1
    if marked:
        await session.commit()
    return marked


def _parse_nm_id(card: dict[str, Any]) -> int | None:
    raw = card.get("nmID") if "nmID" in card else card.get("nmId")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def _parse_vendor_code(card: dict[str, Any]) -> str | None:
    v = card.get("vendorCode") or card.get("vendor_code")
    if isinstance(v, str) and v.strip():
        return v.strip()[:128]
    return None


def _parse_title(card: dict[str, Any]) -> str | None:
    for key in ("title", "subject", "imtName", "brand"):
        v = card.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:255]
    return None


def _parse_dimensions_mm(item: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    """Габариты из карточки WB. WB отдаёт сантиметры, храним миллиметры.

    Возвращает (length_mm, width_mm, height_mm); None там, где WB не дал значения.
    """
    raw = item.get("dimensions")
    if not isinstance(raw, dict):
        return (None, None, None)

    def one(key: str) -> int | None:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value <= 0:
            return None
        return round(value * 10)

    return (one("length"), one("width"), one("height"))


async def _find_product_for_variant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    sku: str,
    variant: WbSizeVariant,
) -> Product | None:
    by_barcode = await session.execute(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_barcode == variant.barcode,
        )
    )
    p = by_barcode.scalar_one_or_none()
    if p is not None:
        return p
    by_sku = await session.execute(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.sku_code == sku,
            Product.seller_id == seller_id,
        )
    )
    return by_sku.scalar_one_or_none()


def _apply_variant_fields(
    p: Product,
    *,
    seller_id: uuid.UUID,
    nm: int | None,
    vendor: str | None,
    title: str,
    sku: str,
    variant: WbSizeVariant,
    category: str | None,
) -> None:
    if p.seller_id is None:
        p.seller_id = seller_id
    p.sku_code = sku
    p.name = title
    if nm is not None:
        p.wb_nm_id = nm
    if vendor is not None:
        p.wb_vendor_code = vendor
    p.wb_chrt_id = variant.chrt_id
    p.wb_barcode = variant.barcode
    p.wb_size = variant.size_label
    if category is not None:
        p.category = category


async def upsert_products_from_wb_cards(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    cards: list[object],
) -> dict[str, int]:
    """
    Create/update Product rows for seller based on WB cards.

    One Product per size barcode (``sizes[].skus``). Multi-size cards get
    distinct ``sku_code`` values (``vendor/size``) and separate stock rows.
    """
    created = 0
    updated = 0
    skipped = 0
    legacy_marked_old = 0

    for item in cards:
        if not isinstance(item, dict):
            continue
        nm = _parse_nm_id(item)
        vendor = _parse_vendor_code(item)
        base_title = _parse_title(item) or (vendor or (f"WB {nm}" if nm else "WB товар"))
        card_length_mm, card_width_mm, card_height_mm = _parse_dimensions_mm(item)
        card_country = country_of_origin_from_card(item)
        card_shelf_life = shelf_life_from_card(item)
        category = subject_name_from_card(item)
        variants = iter_size_variants_from_card(item)
        if not variants:
            skipped += 1
            continue
        multi = len(variants) > 1
        legacy_marked_old += await _mark_legacy_products_for_card(
            session,
            tenant_id,
            seller_id,
            nm,
            multi_variant=multi,
        )

        for variant in variants:
            sku = sku_code_for_wb_variant(vendor, nm, variant, multi_variant=multi)
            title = product_display_name(base_title, variant, multi_variant=multi)
            p = await _find_product_for_variant(session, tenant_id, seller_id, sku, variant)

            if p is None:
                p = Product(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    name=title,
                    sku_code=sku,
                    category=category,
                    wb_nm_id=nm,
                    wb_vendor_code=vendor,
                    wb_chrt_id=variant.chrt_id,
                    wb_barcode=variant.barcode,
                    wb_size=variant.size_label,
                    length_mm=card_length_mm,
                    width_mm=card_width_mm,
                    height_mm=card_height_mm,
                    wb_country_of_origin=card_country,
                    wb_shelf_life=card_shelf_life,
                )
                session.add(p)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    p2 = await _find_product_for_variant(
                        session, tenant_id, seller_id, sku, variant
                    )
                    if p2 is None:
                        skipped += 1
                        continue
                    p = p2
                else:
                    created += 1
                    if (
                        card_length_mm is not None
                        and card_width_mm is not None
                        and card_height_mm is not None
                    ):
                        p.volume_liters = volume_liters_from_mm(
                            card_length_mm, card_width_mm, card_height_mm
                        )
                        p.dimensions_source = "wb"
                        p.dimensions_updated_at = datetime.now(UTC)
                        p.dimensions_updated_by_user_id = None
                        await _record_dimension_event(
                            session,
                            p,
                            source="wb",
                            author_user_id=None,
                            length_mm=card_length_mm,
                            width_mm=card_width_mm,
                            height_mm=card_height_mm,
                            weight_g=p.weight_g,
                            volume_liters=p.volume_liters,
                            container_basis=None,
                            fingerprint=_dimension_fingerprint(
                                card_length_mm, card_width_mm, card_height_mm,
                                p.weight_g, p.volume_liters, "wb", None,
                            ),
                            apply=True,
                        )
                        await session.commit()
                    continue

            if p.seller_id is not None and p.seller_id != seller_id:
                skipped += 1
                continue
            _apply_variant_fields(
                p,
                seller_id=seller_id,
                nm=nm,
                vendor=vendor,
                title=title,
                sku=sku,
                variant=variant,
                category=category,
            )
            # Fill empty dimension fields with values from WB card, and also correct
            # the legacy DEFAULT_PRODUCT_DIM_MM stub (10x10x10) that an old, now
            # removed sync default used to write in place of real data. Product has
            # no field marking "entered by hand" vs "imported", so anything other
            # than that exact stub triple is left untouched -- the safest reading of
            # "never overwrite a measurement someone typed in".
            dims_are_stub = (
                p.length_mm == DEFAULT_PRODUCT_DIM_MM
                and p.width_mm == DEFAULT_PRODUCT_DIM_MM
                and p.height_mm == DEFAULT_PRODUCT_DIM_MM
            )
            if (p.length_mm is None or dims_are_stub) and card_length_mm is not None:
                p.length_mm = card_length_mm
            if (p.width_mm is None or dims_are_stub) and card_width_mm is not None:
                p.width_mm = card_width_mm
            if (p.height_mm is None or dims_are_stub) and card_height_mm is not None:
                p.height_mm = card_height_mm
            if (
                card_length_mm is not None
                and card_width_mm is not None
                and card_height_mm is not None
            ):
                wb_volume_liters = volume_liters_from_mm(
                    card_length_mm, card_width_mm, card_height_mm
                )
                active_event = await session.scalar(
                    select(ProductDimensionEvent).where(
                        ProductDimensionEvent.product_id == p.id,
                        ProductDimensionEvent.applied.is_(True),
                    )
                )
                protected_manual_measurement = active_event is not None and active_event.source in {
                    "manual", "container_override", "container"
                }
                await _record_dimension_event(
                    session, p, source="wb", author_user_id=None,
                    length_mm=card_length_mm, width_mm=card_width_mm, height_mm=card_height_mm,
                    weight_g=p.weight_g, volume_liters=wb_volume_liters, container_basis=None,
                    fingerprint=_dimension_fingerprint(
                        card_length_mm, card_width_mm, card_height_mm,
                        p.weight_g, wb_volume_liters, "wb", None,
                    ),
                    apply=not protected_manual_measurement,
                )
                if not protected_manual_measurement:
                    p.volume_liters = wb_volume_liters
                    p.dimensions_source = "wb"
                    p.dimensions_updated_at = datetime.now(UTC)
                    p.dimensions_updated_by_user_id = None
            # Same rule for country of origin / shelf life: WB card fills the gap,
            # never overwrites a value already present (e.g. entered by hand).
            if p.wb_country_of_origin is None and card_country is not None:
                p.wb_country_of_origin = card_country
            if p.wb_shelf_life is None and card_shelf_life is not None:
                p.wb_shelf_life = card_shelf_life
            try:
                await session.commit()
            except IntegrityError:
                # Two WB cards can share vendor code and size while carrying different
                # barcodes, so both map onto one sku_code, which is unique per tenant.
                # The insert branch above already tolerates that; without the same guard
                # here the whole request dies with a 500 and the seller cannot save the
                # API key at all. Skip the conflicting variant instead.
                await session.rollback()
                skipped += 1
                continue
            updated += 1

    return {
        "products_created": created,
        "products_updated": updated,
        "products_skipped": skipped,
        "legacy_marked_old": legacy_marked_old,
    }
