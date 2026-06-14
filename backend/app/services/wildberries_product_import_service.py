from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.wb_card_enrichment import (
    WbSizeVariant,
    iter_size_variants_from_card,
    product_display_name,
    sku_code_for_wb_variant,
)

OLD_SKU_PREFIX = "OLD/"
OLD_NAME_PREFIX = "[OLD] "


def is_legacy_old_sku(sku: str) -> bool:
    return sku.startswith(OLD_SKU_PREFIX)


async def _sku_taken(session: AsyncSession, tenant_id: uuid.UUID, sku: str) -> bool:
    res = await session.execute(
        select(Product.id).where(Product.tenant_id == tenant_id, Product.sku_code == sku)
    )
    return res.scalar_one_or_none() is not None


async def _allocate_old_sku(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    original_sku: str,
) -> str:
    base = original_sku.strip()
    if is_legacy_old_sku(base):
        return base[:128]
    candidate = f"{OLD_SKU_PREFIX}{base}"[:128]
    if not await _sku_taken(session, tenant_id, candidate):
        return candidate
    for n in range(2, 100):
        alt = f"{OLD_SKU_PREFIX}{base}-{n}"[:128]
        if not await _sku_taken(session, tenant_id, alt):
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
        p.sku_code = await _allocate_old_sku(session, tenant_id, p.sku_code)
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
            Product.wb_barcode == variant.barcode,
        )
    )
    p = by_barcode.scalar_one_or_none()
    if p is not None:
        return p
    by_sku = await session.execute(
        select(Product).where(Product.tenant_id == tenant_id, Product.sku_code == sku)
    )
    p = by_sku.scalar_one_or_none()
    if p is None:
        return None
    if p.seller_id is not None and p.seller_id != seller_id:
        return None
    return p


def _apply_variant_fields(
    p: Product,
    *,
    seller_id: uuid.UUID,
    nm: int | None,
    vendor: str | None,
    title: str,
    sku: str,
    variant: WbSizeVariant,
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


async def upsert_products_from_wb_cards(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    cards: list[object],
    *,
    default_dim_mm: int = 10,
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
                    wb_nm_id=nm,
                    wb_vendor_code=vendor,
                    wb_chrt_id=variant.chrt_id,
                    wb_barcode=variant.barcode,
                    wb_size=variant.size_label,
                    length_mm=default_dim_mm,
                    width_mm=default_dim_mm,
                    height_mm=default_dim_mm,
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
            )
            await session.commit()
            updated += 1

    return {
        "products_created": created,
        "products_updated": updated,
        "products_skipped": skipped,
        "legacy_marked_old": legacy_marked_old,
    }
