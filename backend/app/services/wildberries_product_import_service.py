from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


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

    MVP constraints:
    - Product dimensions are required in schema, but WB import-only doesn't provide them reliably.
      We set a safe default (10mm cube). User can later adjust if needed.
    - sku_code is mapped from WB vendorCode (seller article). If vendorCode missing,
      fallback to WB nmID.
    """
    created = 0
    updated = 0
    skipped = 0

    for item in cards:
        if not isinstance(item, dict):
            continue
        nm = _parse_nm_id(item)
        vendor = _parse_vendor_code(item)
        title = _parse_title(item) or (vendor or (f"WB {nm}" if nm else "WB товар"))

        sku = vendor or (str(nm) if nm is not None else None)
        if not sku:
            skipped += 1
            continue
        sku = sku.strip()[:128]

        stmt = select(Product).where(Product.tenant_id == tenant_id, Product.sku_code == sku)
        res = await session.execute(stmt)
        p = res.scalar_one_or_none()

        if p is None:
            p = Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name=title,
                sku_code=sku,
                wb_nm_id=nm,
                wb_vendor_code=vendor,
                length_mm=default_dim_mm,
                width_mm=default_dim_mm,
                height_mm=default_dim_mm,
            )
            session.add(p)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                # Race/dup: retry as update.
                res2 = await session.execute(stmt)
                p2 = res2.scalar_one_or_none()
                if p2 is None:
                    skipped += 1
                    continue
                p = p2
            else:
                created += 1
                continue

        # Update only if belongs to this seller (or seller_id is NULL).
        if p.seller_id is not None and p.seller_id != seller_id:
            skipped += 1
            continue
        if p.seller_id is None:
            p.seller_id = seller_id
        if nm is not None:
            p.wb_nm_id = nm
        if vendor is not None:
            p.wb_vendor_code = vendor
        if title:
            p.name = title[:255]
        await session.commit()
        updated += 1

    return {"products_created": created, "products_updated": updated, "products_skipped": skipped}

