"""Seller-facing product list enriched from imported WB card snapshots."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Text, and_, cast, exists, false, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_stock_sync_item import STOCK_SYNC_STATUS_CONFIRMED, FbsStockSyncItem
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.catalog_service import (
    list_ozon_product_links,
    list_products,
    marketplace_scope_condition,
    ozon_link_primary_image_url,
)
from app.services.wb_card_enrichment import (
    brand_from_card,
    collect_skus_from_card,
    color_from_card,
    composition_from_card,
    first_photo_url_from_card,
    primary_sku_display,
    size_from_card_for_barcode,
    subject_name_from_card,
)


@dataclass(frozen=True)
class SellerWbCatalogRow:
    product_id: uuid.UUID
    name: str
    sku_code: str
    wb_nm_id: int | None
    wb_vendor_code: str | None
    ozon_sku: str | None
    ozon_offer_id: str | None
    wb_subject_name: str | None
    wb_primary_image_url: str | None
    wb_barcodes: tuple[str, ...]
    wb_primary_barcode: str | None
    marketplace_bindings: tuple[dict[str, Any], ...] = ()
    wb_size: str | None = None
    wb_color: str | None = None
    wb_brand: str | None = None
    wb_composition: str | None = None
    packaging_instructions: str | None = None
    country_of_origin_iso_code: str | None = None
    requires_honest_sign: bool = False
    fbs_stock_sync_enabled: bool = False
    fbs_stock_limit: int | None = None
    fbs_published_amount: int | None = None
    fbs_sync_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.product_id),
            "name": self.name,
            "sku_code": self.sku_code,
            "wb_nm_id": self.wb_nm_id,
            "wb_vendor_code": self.wb_vendor_code,
            "ozon_sku": self.ozon_sku,
            "ozon_offer_id": self.ozon_offer_id,
            "marketplace_bindings": list(self.marketplace_bindings),
            "wb_subject_name": self.wb_subject_name,
            "wb_primary_image_url": self.wb_primary_image_url,
            "wb_barcodes": list(self.wb_barcodes),
            "wb_primary_barcode": self.wb_primary_barcode,
            "wb_size": self.wb_size,
            "wb_color": self.wb_color,
            "wb_brand": self.wb_brand,
            "wb_composition": self.wb_composition,
            "packaging_instructions": self.packaging_instructions,
            "country_of_origin_iso_code": self.country_of_origin_iso_code,
            "requires_honest_sign": self.requires_honest_sign,
            "fbs_stock_sync_enabled": self.fbs_stock_sync_enabled,
            "fbs_stock_limit": self.fbs_stock_limit,
            "fbs_published_amount": self.fbs_published_amount,
            "fbs_sync_status": self.fbs_sync_status,
        }


def _ozon_barcode_binding(link: ProductMarketplaceLink | None) -> tuple[dict[str, Any], ...]:
    """Expose imported codes without inventing one from SKU or copying into WB fields."""
    if link is None:
        return ()
    return (
        {
            "marketplace": "ozon",
            "external_product_id": link.external_product_id,
            "external_offer_id": link.external_offer_id,
            "external_sku": link.external_sku,
            "external_barcodes": list(link.external_barcodes or []),
        },
    )


def _barcodes_for_product(
    p: Product,
    card_raw: dict[str, Any] | None,
) -> tuple[str | None, tuple[str, ...]]:
    if p.wb_barcode and p.wb_barcode.strip():
        code = p.wb_barcode.strip()
        return code, (code,)
    subj, img, barcodes = _enrich_from_raw(card_raw)
    del subj, img
    primary = primary_sku_display(list(barcodes))
    return primary, barcodes


def _size_for_product(
    p: Product,
    card_raw: dict[str, Any] | None,
    primary_barcode: str | None,
) -> str | None:
    if p.wb_size and p.wb_size.strip():
        return p.wb_size.strip()
    return size_from_card_for_barcode(card_raw, primary_barcode) if card_raw else None


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


def _variant_from_raw(
    raw: dict[str, Any] | None,
    *,
    primary_barcode: str | None,
    p: Product | None = None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if p is not None:
        size = _size_for_product(p, raw, primary_barcode)
    else:
        size = size_from_card_for_barcode(raw, primary_barcode) if raw else None
    if not raw:
        return size, None, None, None
    return (
        size,
        color_from_card(raw),
        brand_from_card(raw),
        composition_from_card(raw),
    )


@dataclass(frozen=True)
class _FbsSyncState:
    published_amount: int | None
    status: str | None
    updated_at: datetime


def _is_preferred_fbs_sync_state(
    candidate: _FbsSyncState,
    current: _FbsSyncState | None,
) -> bool:
    if current is None:
        return True
    candidate_confirmed = (
        candidate.status == STOCK_SYNC_STATUS_CONFIRMED and candidate.published_amount is not None
    )
    current_confirmed = (
        current.status == STOCK_SYNC_STATUS_CONFIRMED and current.published_amount is not None
    )
    if candidate_confirmed != current_confirmed:
        return candidate_confirmed
    return candidate.updated_at > current.updated_at


async def _load_fbs_sync_state_by_seller_chrt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    products: list[Product],
    *,
    seller_id: uuid.UUID | None = None,
) -> dict[tuple[uuid.UUID, int], _FbsSyncState]:
    chrt_ids = {int(p.wb_chrt_id) for p in products if p.wb_chrt_id is not None}
    if not chrt_ids:
        return {}

    seller_ids = {p.seller_id for p in products if p.seller_id is not None}
    stmt = (
        select(
            FbsWarehouseBinding.seller_id,
            FbsStockSyncItem.chrt_id,
            FbsStockSyncItem.last_confirmed_amount,
            FbsStockSyncItem.status,
            FbsStockSyncItem.updated_at,
        )
        .join(
            FbsWarehouseBinding,
            FbsWarehouseBinding.id == FbsStockSyncItem.binding_id,
        )
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.is_active.is_(True),
            FbsWarehouseBinding.stock_sync_enabled.is_(True),
            FbsStockSyncItem.chrt_id.in_(chrt_ids),
        )
    )
    if seller_id is not None:
        stmt = stmt.where(FbsWarehouseBinding.seller_id == seller_id)
    elif seller_ids:
        stmt = stmt.where(FbsWarehouseBinding.seller_id.in_(seller_ids))
    else:
        stmt = stmt.where(false())

    res = await session.execute(stmt)
    state_by_key: dict[tuple[uuid.UUID, int], _FbsSyncState] = {}
    for seller_id_row, chrt_id, published_amount, status, updated_at in res.all():
        key = (seller_id_row, int(chrt_id))
        current = state_by_key.get(key)
        candidate = _FbsSyncState(
            published_amount=published_amount,
            status=status,
            updated_at=updated_at,
        )
        if _is_preferred_fbs_sync_state(candidate, current):
            state_by_key[key] = candidate
    return state_by_key


async def list_seller_wb_catalog_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    search: str | None = None,
    limit: int | None = None,
    product_ids: set[uuid.UUID] | None = None,
) -> list[SellerWbCatalogRow]:
    products = await list_products(
        session,
        tenant_id,
        seller_id=seller_id,
        search=search,
        limit=limit,
        product_ids=product_ids,
    )
    ozon_links = await list_ozon_product_links(
        session, tenant_id, {product.id for product in products}
    )
    sync_state_by_key = await _load_fbs_sync_state_by_seller_chrt(
        session,
        tenant_id,
        products,
        seller_id=seller_id,
    )
    # Берём карточки только по товарам этой выдачи. Раньше грузились все карточки
    # селлера целиком — у крупного это полторы тысячи записей с тяжёлым raw_json,
    # и запрос занимал секунды даже когда на экран уходила одна строка.
    nm_ids = {int(p.wb_nm_id) for p in products if p.wb_nm_id is not None}
    cards: list[SellerWildberriesImportedCard] = []
    if nm_ids:
        stmt = select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.seller_id == seller_id,
            SellerWildberriesImportedCard.tenant_id == tenant_id,
            SellerWildberriesImportedCard.nm_id.in_(nm_ids),
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
        subj, img, _legacy_barcodes = _enrich_from_raw(card_raw)
        primary, barcodes = _barcodes_for_product(p, card_raw)
        if primary is None:
            primary = primary_sku_display(list(barcodes))
        wb_size, wb_color, wb_brand, wb_composition = _variant_from_raw(
            card_raw, primary_barcode=primary, p=p
        )
        if subj is None and card_raw:
            subj = subject_name_from_card(card_raw)
        if img is None and card_raw:
            img = first_photo_url_from_card(card_raw)
        if img is None:
            img = ozon_link_primary_image_url(ozon_links.get(p.id))
        chrt_id = int(p.wb_chrt_id) if p.wb_chrt_id is not None else None
        sync_state = sync_state_by_key.get((seller_id, chrt_id)) if chrt_id is not None else None
        rows.append(
            SellerWbCatalogRow(
                product_id=p.id,
                name=p.name,
                sku_code=p.sku_code,
                wb_nm_id=nm,
                wb_vendor_code=p.wb_vendor_code,
                ozon_sku=ozon_links[p.id].external_sku if p.id in ozon_links else None,
                ozon_offer_id=(ozon_links[p.id].external_offer_id if p.id in ozon_links else None),
                wb_subject_name=subj,
                wb_primary_image_url=img,
                wb_barcodes=barcodes,
                wb_primary_barcode=primary,
                marketplace_bindings=_ozon_barcode_binding(ozon_links.get(p.id)),
                wb_size=wb_size,
                wb_color=wb_color,
                wb_brand=wb_brand,
                wb_composition=wb_composition,
                packaging_instructions=p.packaging_instructions,
                country_of_origin_iso_code=p.country_of_origin_iso_code,
                requires_honest_sign=bool(p.requires_honest_sign),
                fbs_stock_sync_enabled=bool(p.fbs_stock_sync_enabled),
                fbs_stock_limit=p.fbs_stock_limit,
                fbs_published_amount=(
                    int(sync_state.published_amount)
                    if sync_state is not None and sync_state.published_amount is not None
                    else None
                ),
                fbs_sync_status=sync_state.status if sync_state is not None else None,
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
    marketplace_bindings: tuple[dict[str, Any], ...] = ()
    ozon_sku: str | None = None
    ozon_offer_id: str | None = None
    wb_size: str | None = None
    wb_color: str | None = None
    wb_brand: str | None = None
    wb_composition: str | None = None
    packaging_instructions: str | None = None
    country_of_origin_iso_code: str | None = None
    requires_honest_sign: bool = False
    fbs_stock_sync_enabled: bool = False
    fbs_stock_limit: int | None = None
    fbs_published_amount: int | None = None
    fbs_sync_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.product_id),
            "seller_id": str(self.seller_id) if self.seller_id is not None else None,
            "seller_name": self.seller_name,
            "name": self.name,
            "sku_code": self.sku_code,
            "wb_nm_id": self.wb_nm_id,
            "wb_vendor_code": self.wb_vendor_code,
            "ozon_sku": self.ozon_sku,
            "ozon_offer_id": self.ozon_offer_id,
            "marketplace_bindings": list(self.marketplace_bindings),
            "wb_subject_name": self.wb_subject_name,
            "wb_primary_image_url": self.wb_primary_image_url,
            "wb_barcodes": list(self.wb_barcodes),
            "wb_primary_barcode": self.wb_primary_barcode,
            "wb_size": self.wb_size,
            "wb_color": self.wb_color,
            "wb_brand": self.wb_brand,
            "wb_composition": self.wb_composition,
            "packaging_instructions": self.packaging_instructions,
            "country_of_origin_iso_code": self.country_of_origin_iso_code,
            "requires_honest_sign": self.requires_honest_sign,
            "fbs_stock_sync_enabled": self.fbs_stock_sync_enabled,
            "fbs_stock_limit": self.fbs_stock_limit,
            "fbs_published_amount": self.fbs_published_amount,
            "fbs_sync_status": self.fbs_sync_status,
            # Manual/Excel until WB sync/link sets nmID on the same barcode.
            "is_manual": self.wb_nm_id is None,
        }


async def list_linked_wb_catalog_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    search: str | None = None,
    marketplace: str | None = None,
) -> list[FfCatalogRow]:
    """All tenant products enriched from imported WB cards (no stock-movement gate)."""
    scoped_products = await list_products(
        session,
        tenant_id,
        seller_id=seller_id,
        search=search,
        marketplace=marketplace,
    )
    return await _enrich_linked_products(
        session,
        tenant_id,
        scoped_products,
        seller_id=seller_id,
    )


async def _enrich_linked_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    scoped_products: list[Product],
    *,
    seller_id: uuid.UUID | None = None,
) -> list[FfCatalogRow]:
    if not scoped_products:
        return []
    ozon_links = await list_ozon_product_links(
        session, tenant_id, {product.id for product in scoped_products}
    )
    sync_state_by_key = await _load_fbs_sync_state_by_seller_chrt(
        session,
        tenant_id,
        scoped_products,
        seller_id=seller_id,
    )

    card_keys = {
        (p.seller_id, int(p.wb_nm_id))
        for p in scoped_products
        if p.seller_id is not None and p.wb_nm_id is not None
    }
    cards: list[SellerWildberriesImportedCard] = []
    if card_keys:
        card_stmt = select(SellerWildberriesImportedCard).where(
            SellerWildberriesImportedCard.tenant_id == tenant_id,
            tuple_(
                SellerWildberriesImportedCard.seller_id,
                SellerWildberriesImportedCard.nm_id,
            ).in_(card_keys),
        )
        card_res = await session.execute(card_stmt)
        cards = list(card_res.scalars().all())
    by_seller_nm: dict[tuple[uuid.UUID, int], dict[str, Any] | None] = {}
    for c in cards:
        raw = c.raw_json if isinstance(c.raw_json, dict) else None
        by_seller_nm[(c.seller_id, int(c.nm_id))] = raw

    rows: list[FfCatalogRow] = []
    for p in scoped_products:
        nm = int(p.wb_nm_id) if p.wb_nm_id is not None else None
        card_raw: dict[str, Any] | None = None
        if nm is not None and p.seller_id is not None:
            card_raw = by_seller_nm.get((p.seller_id, nm))
        subj, img, _legacy_barcodes = _enrich_from_raw(card_raw)
        primary, barcodes = _barcodes_for_product(p, card_raw)
        if primary is None:
            primary = primary_sku_display(list(barcodes))
        wb_size, wb_color, wb_brand, wb_composition = _variant_from_raw(
            card_raw, primary_barcode=primary, p=p
        )
        if subj is None and card_raw:
            subj = subject_name_from_card(card_raw)
        if img is None and card_raw:
            img = first_photo_url_from_card(card_raw)
        if img is None:
            img = ozon_link_primary_image_url(ozon_links.get(p.id))
        chrt_id = int(p.wb_chrt_id) if p.wb_chrt_id is not None else None
        sync_state = (
            sync_state_by_key.get((p.seller_id, chrt_id))
            if p.seller_id is not None and chrt_id is not None
            else None
        )
        rows.append(
            FfCatalogRow(
                product_id=p.id,
                seller_id=p.seller_id,
                seller_name=p.seller.name if p.seller is not None else None,
                name=p.name,
                sku_code=p.sku_code,
                wb_nm_id=nm,
                wb_vendor_code=p.wb_vendor_code,
                ozon_sku=ozon_links[p.id].external_sku if p.id in ozon_links else None,
                ozon_offer_id=ozon_links[p.id].external_offer_id if p.id in ozon_links else None,
                wb_subject_name=subj,
                wb_primary_image_url=img,
                wb_barcodes=barcodes,
                wb_primary_barcode=primary,
                marketplace_bindings=_ozon_barcode_binding(ozon_links.get(p.id)),
                wb_size=wb_size,
                wb_color=wb_color,
                wb_brand=wb_brand,
                wb_composition=wb_composition,
                packaging_instructions=p.packaging_instructions,
                country_of_origin_iso_code=p.country_of_origin_iso_code,
                requires_honest_sign=bool(p.requires_honest_sign),
                fbs_stock_sync_enabled=bool(p.fbs_stock_sync_enabled),
                fbs_stock_limit=p.fbs_stock_limit,
                fbs_published_amount=(
                    int(sync_state.published_amount)
                    if sync_state is not None and sync_state.published_amount is not None
                    else None
                ),
                fbs_sync_status=sync_state.status if sync_state is not None else None,
            ),
        )
    return rows


async def list_linked_wb_catalog_page_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    search: str | None = None,
    category: str | None = None,
    marketplace: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[FfCatalogRow], int, int, list[str]]:
    """Return one stable FF catalog page and the total before enrichment.

    The legacy catalog endpoint intentionally remains unpaged.  This query is for
    the operator table: it narrows the Product rows in SQL first and only then
    parses WB card JSON for the current page.
    """
    card_join = and_(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == Product.seller_id,
        SellerWildberriesImportedCard.nm_id == Product.wb_nm_id,
    )
    scope_filters = [Product.tenant_id == tenant_id]
    if seller_id is not None:
        scope_filters.append(Product.seller_id == seller_id)
    marketplace_condition = marketplace_scope_condition(tenant_id, marketplace)
    if marketplace_condition is not None:
        scope_filters.append(marketplace_condition)
    filters = list(scope_filters)
    normalized_search = (search or "").strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        ozon_link_matches = exists(
            select(ProductMarketplaceLink.id).where(
                ProductMarketplaceLink.tenant_id == tenant_id,
                ProductMarketplaceLink.product_id == Product.id,
                ProductMarketplaceLink.marketplace == "ozon",
                ProductMarketplaceLink.is_active.is_(True),
                or_(
                    ProductMarketplaceLink.external_sku.ilike(pattern),
                    ProductMarketplaceLink.external_offer_id.ilike(pattern),
                ),
            )
        )
        filters.append(
            or_(
                Product.name.ilike(pattern),
                Product.sku_code.ilike(pattern),
                Product.wb_vendor_code.ilike(pattern),
                Product.wb_barcode.ilike(pattern),
                SellerWildberriesImportedCard.title.ilike(pattern),
                SellerWildberriesImportedCard.vendor_code.ilike(pattern),
                cast(SellerWildberriesImportedCard.raw_json, Text).ilike(pattern),
                ozon_link_matches,
            )
        )
    normalized_category = (category or "").strip()
    if normalized_category:
        filters.append(
            SellerWildberriesImportedCard.raw_json["subjectName"].as_string() == normalized_category
        )

    matched_ids = (
        select(Product.id)
        .select_from(Product)
        .outerjoin(SellerWildberriesImportedCard, card_join)
        .where(*filters)
    )
    total = int(await session.scalar(select(func.count()).select_from(matched_ids.subquery())) or 0)
    scope_total = int(
        await session.scalar(select(func.count(Product.id)).where(*scope_filters)) or 0
    )
    product_stmt = (
        select(Product)
        .outerjoin(SellerWildberriesImportedCard, card_join)
        .where(*filters)
        .options(selectinload(Product.seller))
        .order_by(Product.sku_code, Product.id)
        .limit(limit)
        .offset(offset)
    )
    products = list((await session.execute(product_stmt)).scalars().unique().all())

    category_filters = [Product.tenant_id == tenant_id]
    if seller_id is not None:
        category_filters.append(Product.seller_id == seller_id)
    subject = SellerWildberriesImportedCard.raw_json["subjectName"].as_string()
    category_stmt = (
        select(subject)
        .select_from(Product)
        .join(SellerWildberriesImportedCard, card_join)
        .where(*category_filters, subject.is_not(None), subject != "")
        .distinct()
        .order_by(subject)
    )
    categories = [str(value) for value in (await session.scalars(category_stmt)).all()]
    rows = await _enrich_linked_products(
        session,
        tenant_id,
        products,
        seller_id=seller_id,
    )
    return rows, total, scope_total, categories


async def list_ff_catalog_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
    search: str | None = None,
    marketplace: str | None = None,
) -> list[FfCatalogRow]:
    """FF warehouse catalog: all tenant products enriched from imported WB cards."""
    return await list_linked_wb_catalog_rows(
        session, tenant_id, seller_id=seller_id, search=search, marketplace=marketplace
    )
