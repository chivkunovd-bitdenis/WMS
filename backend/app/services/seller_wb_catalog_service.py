"""Seller-facing product list enriched from imported WB card snapshots."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.catalog_service import list_products
from app.services.wb_card_enrichment import (
    collect_skus_from_card,
    first_photo_url_from_card,
    primary_sku_display,
    subject_name_from_card,
)


@dataclass(frozen=True)
class SellerWbCatalogRow:
    product_id: uuid.UUID
    name: str
    sku_code: str
    wb_nm_id: int | None
    wb_vendor_code: str | None
    wb_subject_name: str | None
    wb_primary_image_url: str | None
    wb_barcodes: tuple[str, ...]
    wb_primary_barcode: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.product_id),
            "name": self.name,
            "sku_code": self.sku_code,
            "wb_nm_id": self.wb_nm_id,
            "wb_vendor_code": self.wb_vendor_code,
            "wb_subject_name": self.wb_subject_name,
            "wb_primary_image_url": self.wb_primary_image_url,
            "wb_barcodes": list(self.wb_barcodes),
            "wb_primary_barcode": self.wb_primary_barcode,
        }


def _enrich_from_raw(raw: dict[str, Any] | None) -> tuple[str | None, str | None, tuple[str, ...]]:
    if not raw:
        return None, None, ()
    skus = collect_skus_from_card(raw)
    tup = tuple(skus)
    return (
        subject_name_from_card(raw),
        first_photo_url_from_card(raw),
        tup,
    )


async def list_seller_wb_catalog_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[SellerWbCatalogRow]:
    products = await list_products(session, tenant_id, seller_id=seller_id)
    stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.seller_id == seller_id,
        SellerWildberriesImportedCard.tenant_id == tenant_id,
    )
    res = await session.execute(stmt)
    cards = list(res.scalars().all())
    by_nm: dict[int, dict[str, Any] | None] = {}  # nm_id -> raw card json
    for c in cards:
        raw = c.raw_json if isinstance(c.raw_json, dict) else None
        by_nm[int(c.nm_id)] = raw

    rows: list[SellerWbCatalogRow] = []
    for p in products:
        card_raw: dict[str, Any] | None = None
        nm = int(p.wb_nm_id) if p.wb_nm_id is not None else None
        if nm is not None:
            card_raw = by_nm.get(nm)
        subj, img, barcodes = _enrich_from_raw(card_raw)
        rows.append(
            SellerWbCatalogRow(
                product_id=p.id,
                name=p.name,
                sku_code=p.sku_code,
                wb_nm_id=nm,
                wb_vendor_code=p.wb_vendor_code,
                wb_subject_name=subj,
                wb_primary_image_url=img,
                wb_barcodes=barcodes,
                wb_primary_barcode=primary_sku_display(list(barcodes)),
            ),
        )
    return rows
