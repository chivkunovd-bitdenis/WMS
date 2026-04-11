"""Persist and list Wildberries imported card snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller import Seller
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard


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
        return v.strip()[:255]
    return None


def _parse_title(card: dict[str, Any]) -> str | None:
    for key in ("title", "subject", "imtName", "brand"):
        v = card.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:512]
    return None


async def upsert_imported_cards(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    cards: list[Any],
) -> int:
    """Upsert card rows from WB API ``cards`` array. Returns number of rows written/updated."""
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return 0
    now = datetime.now(tz=UTC)
    n = 0
    for item in cards:
        if not isinstance(item, dict):
            continue
        nm = _parse_nm_id(item)
        if nm is None:
            continue
        vc = _parse_vendor_code(item)
        title = _parse_title(item)
        stmt = select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.seller_id == seller_id,
            SellerWildberriesImportedCard.nm_id == nm,
        )
        res = await session.execute(stmt)
        row = res.scalar_one_or_none()
        raw: dict[str, Any] | None = item if item else None
        if row is None:
            session.add(
                SellerWildberriesImportedCard(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    nm_id=nm,
                    vendor_code=vc,
                    title=title,
                    raw_json=raw,
                    updated_at=now,
                )
            )
        else:
            row.vendor_code = vc
            row.title = title
            row.raw_json = raw
            row.updated_at = now
        n += 1
    await session.flush()
    return n


async def list_imported_cards_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[SellerWildberriesImportedCard] | None:
    """Return ordered rows, or ``None`` if seller not in tenant."""
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    stmt = (
        select(SellerWildberriesImportedCard)
        .where(SellerWildberriesImportedCard.seller_id == seller_id)
        .order_by(SellerWildberriesImportedCard.nm_id)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
