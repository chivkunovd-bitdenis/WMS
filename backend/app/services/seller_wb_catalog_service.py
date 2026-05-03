"""Seller-facing product list enriched from imported WB card snapshots."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
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


@dataclass(frozen=True)
class FfCatalogRow:
    product_id: uuid.UUID
    seller_id: uuid.UUID | None
    seller_name: str | None
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
            "seller_id": str(self.seller_id) if self.seller_id is not None else None,
            "seller_name": self.seller_name,
            "name": self.name,
            "sku_code": self.sku_code,
            "wb_nm_id": self.wb_nm_id,
            "wb_vendor_code": self.wb_vendor_code,
            "wb_subject_name": self.wb_subject_name,
            "wb_primary_image_url": self.wb_primary_image_url,
            "wb_barcodes": list(self.wb_barcodes),
            "wb_primary_barcode": self.wb_primary_barcode,
        }


async def list_ff_catalog_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> list[FfCatalogRow]:
    """FF warehouse catalog: products that already have warehouse movements.

    Seller WB/API catalog remains private. FF sees products only after warehouse
    flow creates stock movements (for example, posted inbound by actual qty).
    """
    moved_product_ids = (
        select(InventoryMovement.product_id)
        .where(InventoryMovement.tenant_id == tenant_id)
        .distinct()
    )
    product_stmt = (
        select(Product)
        .where(
            Product.tenant_id == tenant_id,
            Product.id.in_(moved_product_ids),
        )
        .options(selectinload(Product.seller))
        .order_by(Product.sku_code)
    )
    if seller_id is not None:
        product_stmt = product_stmt.where(Product.seller_id == seller_id)
    res = await session.execute(product_stmt)
    products = list(res.scalars().unique().all())
    if not products:
        return []

    seller_ids: set[uuid.UUID] = set()
    for p in products:
        if p.seller_id is not None:
            seller_ids.add(p.seller_id)

    card_stmt = select(SellerWildberriesImportedCard).where(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
    )
    if seller_id is not None:
        card_stmt = card_stmt.where(SellerWildberriesImportedCard.seller_id == seller_id)
    elif seller_ids:
        card_stmt = card_stmt.where(SellerWildberriesImportedCard.seller_id.in_(seller_ids))
    else:
        # No sellers on products: no point fetching cards.
        card_stmt = card_stmt.where(false())

    card_res = await session.execute(card_stmt)
    cards = list(card_res.scalars().all())
    by_seller_nm: dict[tuple[uuid.UUID, int], dict[str, Any] | None] = {}
    for c in cards:
        raw = c.raw_json if isinstance(c.raw_json, dict) else None
        by_seller_nm[(c.seller_id, int(c.nm_id))] = raw

    rows: list[FfCatalogRow] = []
    for p in products:
        nm = int(p.wb_nm_id) if p.wb_nm_id is not None else None
        card_raw: dict[str, Any] | None = None
        if nm is not None and p.seller_id is not None:
            card_raw = by_seller_nm.get((p.seller_id, nm))
        subj, img, barcodes = _enrich_from_raw(card_raw)
        rows.append(
            FfCatalogRow(
                product_id=p.id,
                seller_id=p.seller_id,
                seller_name=p.seller.name if p.seller is not None else None,
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
