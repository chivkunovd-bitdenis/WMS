"""Seller-facing union of on-fulfillment products and not-yet-selected WB cards.

WMS-548: the seller must see the whole marketplace catalog (every card of every
connected shop) and be able to add a card to fulfillment on demand, while the
fulfillment side keeps working only with products that were actually selected.
The system already keeps two layers for WB — the full card snapshot
(``seller_wildberries_imported_cards``) and the WMS ``products`` that the
warehouse works with — so no new table is needed for WB: "on fulfillment"
simply means "this seller already has a product with this card's nmID"
(decision A3 in docs/requirements/WMS-548.md). A card becomes a product only
when the seller explicitly adds it here.

Both the paged listing and the bulk add avoid loading a seller's whole catalog
into Python or building a giant ``IN`` clause — WMS-538 showed exactly what
that does to a seller with tens of thousands of cards: the union of the two
sources is paginated in SQL, and search/category filters run in SQL too.

WMS-548 D3 adds the Ozon half by the same shape: a snapshot table
(``seller_ozon_imported_cards``), an ``ozon_card`` branch in the union next to
the WB one (gated by the same ``marketplace``/``on_fulfillment`` filters —
Ozon carries no category, so a category filter simply excludes Ozon rows, as
decided in А6), and real handling of ``ozon_product_ids`` in
``add_cards_to_fulfillment``. Ozon's own matching/linking rules
(``ozon_product_import_service``) are reused unchanged; only whether an
unmatched card may turn into a *new* product is decided here, same as for WB.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal, TypeVar

from sqlalchemy import (
    ColumnElement,
    Select,
    String,
    Text,
    and_,
    cast,
    exists,
    false,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.catalog_service import chunked, marketplace_scope_condition
from app.services.ozon_product_import_service import (
    OzonProductImportResult,
    build_ozon_match_context,
    process_one_ozon_card,
)
from app.services.ozon_product_import_service import (
    card_barcodes as ozon_card_barcodes,
)
from app.services.ozon_product_import_service import (
    card_primary_image_url as ozon_card_primary_image_url,
)
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows
from app.services.wb_card_enrichment import (
    WbSizeVariant,
    collect_skus_from_card,
    first_photo_url_from_card,
    iter_size_variants_from_card,
    sku_code_for_wb_variant,
    subject_name_from_card,
)
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards

logger = logging.getLogger(__name__)

OnFulfillmentFilter = Literal["all", "yes", "no"]
MarketplaceFilter = Literal["wildberries", "ozon"]

# Тот же порядок величины, что и у пачек nmID/product_id в других местах
# каталога (см. catalog_service.ID_IN_BATCH_SIZE) — но контракт /seller-catalog
# ограничивает запрос на добавление 500 идентификаторами, так что здесь это
# скорее документирует лимит контракта, чем защищает от IN-запроса на тысячи id.
ADD_TO_FULFILLMENT_MAX_IDS = 500

_T = TypeVar("_T")


def _dedupe_preserve_order(values: list[_T]) -> list[_T]:
    return list(dict.fromkeys(values))


def _size_label(entry: dict[str, Any]) -> str | None:
    tech = entry.get("techSize")
    if isinstance(tech, str) and tech.strip():
        return tech.strip()
    wb_size = entry.get("wbSize")
    if isinstance(wb_size, str) and wb_size.strip():
        return wb_size.strip()
    return None


def _all_size_labels_from_card(card: dict[str, Any] | None) -> list[str]:
    if not card:
        return []
    sizes = card.get("sizes")
    if not isinstance(sizes, list):
        return []
    labels: list[str] = []
    for sz in sizes:
        if isinstance(sz, dict):
            label = _size_label(sz)
            if label and label not in labels:
                labels.append(label)
    return labels


def _not_on_fulfillment_condition(
    tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> ColumnElement[bool]:
    """True for a snapshot card row that has no WMS product with its nmID yet."""
    has_product = exists(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.seller_id == seller_id,
            Product.wb_nm_id == SellerWildberriesImportedCard.nm_id,
        )
    )
    return ~has_product


def _card_search_filters(search: str | None) -> list[Any]:
    normalized = (search or "").strip()
    if not normalized:
        return []
    pattern = f"%{normalized}%"
    return [
        or_(
            SellerWildberriesImportedCard.title.ilike(pattern),
            SellerWildberriesImportedCard.vendor_code.ilike(pattern),
            cast(SellerWildberriesImportedCard.nm_id, String).ilike(pattern),
            cast(SellerWildberriesImportedCard.raw_json, Text).ilike(pattern),
        )
    ]


def _card_category_filters(category: str | None) -> list[Any]:
    normalized = (category or "").strip()
    if not normalized:
        return []
    return [SellerWildberriesImportedCard.raw_json["subjectName"].as_string() == normalized]


def _ozon_not_on_fulfillment_condition(
    tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> ColumnElement[bool]:
    """True for an Ozon snapshot row with no active link to a WMS product yet."""
    has_link = exists(
        select(ProductMarketplaceLink.id).where(
            ProductMarketplaceLink.tenant_id == tenant_id,
            ProductMarketplaceLink.seller_id == seller_id,
            ProductMarketplaceLink.marketplace == "ozon",
            ProductMarketplaceLink.is_active.is_(True),
            ProductMarketplaceLink.external_product_id == SellerOzonImportedCard.ozon_product_id,
        )
    )
    return ~has_link


def _ozon_card_search_filters(search: str | None) -> list[Any]:
    normalized = (search or "").strip()
    if not normalized:
        return []
    pattern = f"%{normalized}%"
    return [
        or_(
            SellerOzonImportedCard.name.ilike(pattern),
            SellerOzonImportedCard.offer_id.ilike(pattern),
            SellerOzonImportedCard.sku.ilike(pattern),
            SellerOzonImportedCard.ozon_product_id.ilike(pattern),
            cast(SellerOzonImportedCard.raw_json, Text).ilike(pattern),
        )
    ]


def _ozon_card_category_filters(category: str | None) -> list[Any]:
    """Ozon carries no category (the import never receives one, А6) — a
    category filter simply excludes every Ozon row rather than matching none
    of them silently."""
    normalized = (category or "").strip()
    if not normalized:
        return []
    return [false()]


def _product_search_filters(tenant_id: uuid.UUID, search: str | None) -> list[Any]:
    normalized = (search or "").strip()
    if not normalized:
        return []
    pattern = f"%{normalized}%"
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
    return [
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
    ]


def _product_card_join(tenant_id: uuid.UUID) -> ColumnElement[bool]:
    return and_(
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == Product.seller_id,
        SellerWildberriesImportedCard.nm_id == Product.wb_nm_id,
    )


async def _connection_flags(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> tuple[bool, bool]:
    """Same check as GET /products/wb-catalog: is a WB/Ozon key saved for this seller."""
    wb_connected = (
        await session.scalar(
            select(SellerWildberriesCredentials.seller_id).where(
                SellerWildberriesCredentials.seller_id == seller_id,
                SellerWildberriesCredentials.marketplace_token_encrypted.isnot(None),
            )
        )
        is not None
    )
    ozon_connected = (
        await session.scalar(
            select(MarketplaceAccount.id).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
                MarketplaceAccount.account_slot == "primary",
                MarketplaceAccount.is_active.is_(True),
            )
        )
        is not None
    )
    return wb_connected, ozon_connected


async def list_seller_catalog_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    search: str | None = None,
    category: str | None = None,
    on_fulfillment: OnFulfillmentFilter = "all",
    marketplace: MarketplaceFilter | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, int, list[str]]:
    """One page of the seller's catalog: on-fulfillment products + snapshot cards.

    Mirrors ``seller_wb_catalog_service.list_linked_wb_catalog_page_rows``: the
    Product/card rows are narrowed to ids in SQL first (a stable sort key plus
    the row's own id), and only the current page's rows get the expensive
    per-row enrichment (WB card JSON parsing, Ozon link lookup, FBS sync
    state).
    """
    marketplace_condition = marketplace_scope_condition(tenant_id, marketplace)
    card_join = _product_card_join(tenant_id)
    include_wb = marketplace in (None, "wildberries")
    include_ozon = marketplace in (None, "ozon")

    product_filters: list[Any] = [Product.tenant_id == tenant_id, Product.seller_id == seller_id]
    if marketplace_condition is not None:
        product_filters.append(marketplace_condition)
    product_filters.extend(_product_search_filters(tenant_id, search))
    product_filters.extend(_card_category_filters(category))

    wb_card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    wb_card_filters.extend(_card_search_filters(search))
    wb_card_filters.extend(_card_category_filters(category))

    ozon_card_filters: list[Any] = [
        SellerOzonImportedCard.tenant_id == tenant_id,
        SellerOzonImportedCard.seller_id == seller_id,
        _ozon_not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    ozon_card_filters.extend(_ozon_card_search_filters(search))
    ozon_card_filters.extend(_ozon_card_category_filters(category))

    product_branch = (
        select(
            literal("product").label("kind"),
            Product.sku_code.label("sort_key"),
            cast(Product.id, String).label("raw_key"),
        )
        .select_from(Product)
        .outerjoin(SellerWildberriesImportedCard, card_join)
        .where(*product_filters)
    )
    wb_card_branch = select(
        literal("wb_card").label("kind"),
        func.coalesce(
            SellerWildberriesImportedCard.vendor_code,
            cast(SellerWildberriesImportedCard.nm_id, String),
        ).label("sort_key"),
        cast(SellerWildberriesImportedCard.nm_id, String).label("raw_key"),
    ).where(*wb_card_filters)
    ozon_card_branch = select(
        literal("ozon_card").label("kind"),
        func.coalesce(
            SellerOzonImportedCard.offer_id,
            SellerOzonImportedCard.ozon_product_id,
        ).label("sort_key"),
        SellerOzonImportedCard.ozon_product_id.label("raw_key"),
    ).where(*ozon_card_filters)

    not_on_ff_branches = [
        branch
        for branch, enabled in ((wb_card_branch, include_wb), (ozon_card_branch, include_ozon))
        if enabled
    ]

    universe: Any
    if on_fulfillment == "yes":
        universe = product_branch
    elif on_fulfillment == "no":
        universe = union_all(*not_on_ff_branches) if len(not_on_ff_branches) > 1 else (
            not_on_ff_branches[0]
        )
    else:
        universe = union_all(product_branch, *not_on_ff_branches)
    universe_subq = universe.subquery("seller_catalog_universe")

    total = int(
        await session.scalar(select(func.count()).select_from(universe_subq)) or 0
    )

    scope_product_filters: list[Any] = [
        Product.tenant_id == tenant_id,
        Product.seller_id == seller_id,
    ]
    if marketplace_condition is not None:
        scope_product_filters.append(marketplace_condition)
    scope_wb_card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    scope_ozon_card_filters: list[Any] = [
        SellerOzonImportedCard.tenant_id == tenant_id,
        SellerOzonImportedCard.seller_id == seller_id,
        _ozon_not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    scope_total = int(
        await session.scalar(
            select(func.count()).select_from(Product).where(*scope_product_filters)
        )
        or 0
    )
    if include_wb:
        scope_total += int(
            await session.scalar(
                select(func.count())
                .select_from(SellerWildberriesImportedCard)
                .where(*scope_wb_card_filters)
            )
            or 0
        )
    if include_ozon:
        scope_total += int(
            await session.scalar(
                select(func.count())
                .select_from(SellerOzonImportedCard)
                .where(*scope_ozon_card_filters)
            )
            or 0
        )

    page_stmt = (
        select(universe_subq.c.kind, universe_subq.c.raw_key)
        .order_by(universe_subq.c.sort_key, universe_subq.c.kind, universe_subq.c.raw_key)
        .limit(limit)
        .offset(offset)
    )
    page_rows = list((await session.execute(page_stmt)).all())

    category_stmt = (
        select(SellerWildberriesImportedCard.raw_json["subjectName"].as_string())
        .where(
            SellerWildberriesImportedCard.tenant_id == tenant_id,
            SellerWildberriesImportedCard.seller_id == seller_id,
            SellerWildberriesImportedCard.raw_json["subjectName"].as_string().is_not(None),
            SellerWildberriesImportedCard.raw_json["subjectName"].as_string() != "",
        )
        .distinct()
        .order_by(SellerWildberriesImportedCard.raw_json["subjectName"].as_string())
    )
    categories = [str(value) for value in (await session.scalars(category_stmt)).all()]

    items = await _build_page_items(session, tenant_id, seller_id, page_rows)
    return items, total, scope_total, categories


async def _build_page_items(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    page_rows: list[Any],
) -> list[dict[str, Any]]:
    product_ids: list[uuid.UUID] = []
    nm_ids: list[int] = []
    ozon_product_ids: list[str] = []
    for kind, raw_key in page_rows:
        if kind == "product":
            product_ids.append(uuid.UUID(raw_key))
        elif kind == "wb_card":
            nm_ids.append(int(raw_key))
        else:
            ozon_product_ids.append(raw_key)

    wb_connected, ozon_connected = await _connection_flags(session, tenant_id, seller_id)

    rows_by_product_id: dict[uuid.UUID, dict[str, Any]] = {}
    if product_ids:
        catalog_rows = await list_seller_wb_catalog_rows(
            session, tenant_id, seller_id, product_ids=set(product_ids)
        )
        for row in catalog_rows:
            data = row.as_dict()
            data["has_packaging_instructions"] = bool((row.packaging_instructions or "").strip())
            rows_by_product_id[row.product_id] = data

    cards_by_nm: dict[int, SellerWildberriesImportedCard] = {}
    if nm_ids:
        for batch in chunked(sorted(set(nm_ids)), 2000):
            stmt = select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.tenant_id == tenant_id,
                SellerWildberriesImportedCard.seller_id == seller_id,
                SellerWildberriesImportedCard.nm_id.in_(batch),
            )
            for card_row in (await session.execute(stmt)).scalars().all():
                cards_by_nm[int(card_row.nm_id)] = card_row

    ozon_cards_by_id: dict[str, SellerOzonImportedCard] = {}
    if ozon_product_ids:
        for ozon_batch in chunked(sorted(set(ozon_product_ids)), 2000):
            ozon_stmt = select(SellerOzonImportedCard).where(
                SellerOzonImportedCard.tenant_id == tenant_id,
                SellerOzonImportedCard.seller_id == seller_id,
                SellerOzonImportedCard.ozon_product_id.in_(ozon_batch),
            )
            for ozon_card_row in (await session.execute(ozon_stmt)).scalars().all():
                ozon_cards_by_id[ozon_card_row.ozon_product_id] = ozon_card_row

    items: list[dict[str, Any]] = []
    for kind, raw_key in page_rows:
        if kind == "product":
            product_id = uuid.UUID(raw_key)
            product_data = rows_by_product_id.get(product_id)
            if product_data is None:
                continue
            marketplace_value = (
                "wildberries" if product_data.get("wb_nm_id") is not None else "ozon"
            )
            items.append(
                {
                    "key": f"product:{product_id}",
                    "on_fulfillment": True,
                    "marketplace": marketplace_value,
                    "wb_connected": wb_connected,
                    "ozon_connected": ozon_connected,
                    **product_data,
                }
            )
        elif kind == "wb_card":
            nm_id = int(raw_key)
            card = cards_by_nm.get(nm_id)
            if card is None:
                continue
            raw = card.raw_json if isinstance(card.raw_json, dict) else None
            items.append(
                {
                    "key": f"wb:{nm_id}",
                    "on_fulfillment": False,
                    "marketplace": "wildberries",
                    "nm_id": nm_id,
                    "vendor_code": card.vendor_code,
                    "name": card.title,
                    "photo_url": first_photo_url_from_card(raw) if raw else None,
                    "barcodes": collect_skus_from_card(raw) if raw else [],
                    "sizes": _all_size_labels_from_card(raw),
                    "category": subject_name_from_card(raw) if raw else None,
                }
            )
        else:
            ozon_card = ozon_cards_by_id.get(raw_key)
            if ozon_card is None:
                continue
            ozon_raw = ozon_card.raw_json if isinstance(ozon_card.raw_json, dict) else None
            items.append(
                {
                    "key": f"ozon:{raw_key}",
                    "on_fulfillment": False,
                    "marketplace": "ozon",
                    "ozon_product_id": raw_key,
                    "vendor_code": ozon_card.offer_id,
                    "name": ozon_card.name,
                    "photo_url": (
                        ozon_card_primary_image_url(ozon_raw) if ozon_raw else None
                    ),
                    "barcodes": ozon_card_barcodes(ozon_raw) if ozon_raw else [],
                    "sizes": [],
                    "category": None,
                }
            )
    return items


async def list_seller_catalog_keys(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    search: str | None = None,
    category: str | None = None,
    on_fulfillment: OnFulfillmentFilter = "all",
    marketplace: MarketplaceFilter | None = None,
) -> list[str]:
    """All keys matching the same filters as the page — for "select all found"."""
    marketplace_condition = marketplace_scope_condition(tenant_id, marketplace)
    card_join = _product_card_join(tenant_id)
    include_wb = marketplace in (None, "wildberries")
    include_ozon = marketplace in (None, "ozon")

    product_filters: list[Any] = [Product.tenant_id == tenant_id, Product.seller_id == seller_id]
    if marketplace_condition is not None:
        product_filters.append(marketplace_condition)
    product_filters.extend(_product_search_filters(tenant_id, search))
    product_filters.extend(_card_category_filters(category))

    wb_card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    wb_card_filters.extend(_card_search_filters(search))
    wb_card_filters.extend(_card_category_filters(category))

    ozon_card_filters: list[Any] = [
        SellerOzonImportedCard.tenant_id == tenant_id,
        SellerOzonImportedCard.seller_id == seller_id,
        _ozon_not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    ozon_card_filters.extend(_ozon_card_search_filters(search))
    ozon_card_filters.extend(_ozon_card_category_filters(category))

    keys: list[str] = []
    if on_fulfillment in ("all", "yes"):
        product_stmt = (
            select(Product.id)
            .select_from(Product)
            .outerjoin(SellerWildberriesImportedCard, card_join)
            .where(*product_filters)
        )
        keys.extend(f"product:{pid}" for pid in (await session.scalars(product_stmt)).all())
    if on_fulfillment in ("all", "no"):
        if include_wb:
            wb_card_stmt = select(SellerWildberriesImportedCard.nm_id).where(*wb_card_filters)
            keys.extend(f"wb:{nm_id}" for nm_id in (await session.scalars(wb_card_stmt)).all())
        if include_ozon:
            ozon_card_stmt = select(SellerOzonImportedCard.ozon_product_id).where(
                *ozon_card_filters
            )
            keys.extend(
                f"ozon:{ozon_id}" for ozon_id in (await session.scalars(ozon_card_stmt)).all()
            )
    return keys


def _conflicting_product_query(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    nm_id: int,
    skus: set[str],
    barcodes: set[str],
) -> Select[tuple[uuid.UUID]]:
    return select(Product.id).where(
        Product.tenant_id == tenant_id,
        Product.seller_id == seller_id,
        Product.wb_nm_id.is_not(None),
        Product.wb_nm_id != nm_id,
        or_(Product.sku_code.in_(skus), Product.wb_barcode.in_(barcodes)),
    )


async def _card_has_vendor_code_conflict(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    nm_id: int,
    vendor: str | None,
    variants: list[WbSizeVariant],
) -> bool:
    """A never-before-selected card must not silently steal another card's slot.

    ``upsert_products_from_wb_cards`` matches an existing product by sku_code
    or wb_barcode and adopts it (needed so a re-synced card can update its own
    product). That is correct for a card that is already on fulfillment, but
    for a brand-new addition it would mean handing this card's identity to a
    product that actually belongs to a *different*, already-selected nmID —
    real data corruption, not a legitimate merge. Products with no wb_nm_id
    (manual/Excel-created) are left to the existing adopt-on-match behaviour
    unchanged, since that is the documented, wanted merge path.
    """
    multi = len(variants) > 1
    skus = {sku_code_for_wb_variant(vendor, nm_id, v, multi_variant=multi) for v in variants}
    barcodes = {v.barcode for v in variants}
    if not skus and not barcodes:
        return False
    stmt = _conflicting_product_query(tenant_id, seller_id, nm_id, skus, barcodes)
    return (await session.scalar(stmt)) is not None


async def add_cards_to_fulfillment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    wb_nm_ids: list[int],
    ozon_product_ids: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn selected WB cards into WMS products; report per-card outcome.

    Each card is looked up and upserted on its own, so a failure on one card
    (or the request dying partway through) never loses the cards already
    committed before it, and a repeat of the same ids is safe: cards already
    on fulfillment are simply re-upserted with the latest snapshot data
    (matches new sizes, changes nothing else), and concurrent requests for the
    same brand-new card are deduplicated by ``upsert_products_from_wb_cards``
    itself (it already retries on the unique-constraint race).
    """
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    nm_ids = _dedupe_preserve_order(wb_nm_ids)
    if nm_ids:
        cards_by_nm: dict[int, SellerWildberriesImportedCard] = {}
        for batch in chunked(sorted(set(nm_ids)), 2000):
            stmt = select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.tenant_id == tenant_id,
                SellerWildberriesImportedCard.seller_id == seller_id,
                SellerWildberriesImportedCard.nm_id.in_(batch),
            )
            for card_row in (await session.execute(stmt)).scalars().all():
                cards_by_nm[int(card_row.nm_id)] = card_row

        for nm_id in nm_ids:
            card = cards_by_nm.get(nm_id)
            if card is None:
                # Не своя карточка (чужой селлер/тенант) или её нет — не
                # раскрываем, есть ли она вообще у кого-то ещё (R14).
                skipped.append(
                    {
                        "marketplace": "wildberries",
                        "id": str(nm_id),
                        "vendor_code": None,
                        "reason": "not_found",
                    }
                )
                continue
            # Захватываем поля карточки в локальные переменные до апсерта: он
            # коммитит, а неудача ниже коммитит откат, который на этой же
            # сессии истекает атрибуты всех загруженных объектов — ленивая
            # подгрузка `card.vendor_code` после отката под конкурентной
            # нагрузкой уже падала MissingGreenlet вместо честного skipped.
            vendor_code = card.vendor_code
            raw = card.raw_json if isinstance(card.raw_json, dict) else None
            variants = iter_size_variants_from_card(raw) if raw else []
            if not variants:
                skipped.append(
                    {
                        "marketplace": "wildberries",
                        "id": str(nm_id),
                        "vendor_code": vendor_code,
                        "reason": "no_size_variants",
                    }
                )
                continue
            try:
                conflict = await _card_has_vendor_code_conflict(
                    session, tenant_id, seller_id, nm_id, vendor_code, variants
                )
                if conflict:
                    skipped.append(
                        {
                            "marketplace": "wildberries",
                            "id": str(nm_id),
                            "vendor_code": vendor_code,
                            "reason": "vendor_code_conflict",
                        }
                    )
                    continue
                counts = await upsert_products_from_wb_cards(
                    session, tenant_id, seller_id, [raw]
                )
            except Exception:
                await session.rollback()
                logger.exception(
                    "seller_catalog.add_to_fulfillment: failed to add WB card %s for seller %s",
                    nm_id,
                    seller_id,
                )
                skipped.append(
                    {
                        "marketplace": "wildberries",
                        "id": str(nm_id),
                        "vendor_code": vendor_code,
                        "reason": "internal_error",
                    }
                )
                continue
            products_added = counts["products_created"] + counts["products_updated"]
            if products_added == 0:
                # Не наш конфликт-предчек (тот уже отсёк выше) — упсерт сам не
                # завёл и не обновил ни одного варианта (например, гонка
                # уникального индекса, которую не разрешил повторный поиск).
                skipped.append(
                    {
                        "marketplace": "wildberries",
                        "id": str(nm_id),
                        "vendor_code": vendor_code,
                        "reason": "not_added",
                    }
                )
                continue
            added.append(
                {
                    "marketplace": "wildberries",
                    "id": str(nm_id),
                    "vendor_code": vendor_code,
                    "products_added": products_added,
                }
            )

        # R13: a WB card just added may have an Ozon twin already sitting in
        # this seller's Ozon snapshot, unlinked. Link it now (never create —
        # the product already exists) so the twin stops showing as a separate
        # "not on fulfillment" row. Best-effort: it never touches, let alone
        # undoes, the WB cards already committed above.
        if any(a["marketplace"] == "wildberries" for a in added):
            await _link_unmatched_ozon_twins(session, tenant_id, seller_id)

    ozon_ids = _dedupe_preserve_order(ozon_product_ids)
    if ozon_ids:
        ozon_cards_by_id: dict[str, SellerOzonImportedCard] = {}
        for ozon_batch in chunked(sorted(set(ozon_ids)), 2000):
            ozon_stmt = select(SellerOzonImportedCard).where(
                SellerOzonImportedCard.tenant_id == tenant_id,
                SellerOzonImportedCard.seller_id == seller_id,
                SellerOzonImportedCard.ozon_product_id.in_(ozon_batch),
            )
            for ozon_card_row in (await session.execute(ozon_stmt)).scalars().all():
                ozon_cards_by_id[ozon_card_row.ozon_product_id] = ozon_card_row

        # Один контекст на весь запрос — не на карточку (WMS-538): иначе
        # каждая из до 500 карточек читала бы товары продавца заново.
        ozon_context = await build_ozon_match_context(session, tenant_id, seller_id)

        for ozon_id in ozon_ids:
            ozon_card = ozon_cards_by_id.get(ozon_id)
            if ozon_card is None:
                # Не своя карточка (чужой селлер/тенант) или её нет вовсе —
                # не раскрываем, есть ли она у кого-то другого (R14).
                skipped.append(
                    {
                        "marketplace": "ozon",
                        "id": ozon_id,
                        "vendor_code": None,
                        "reason": "not_found",
                    }
                )
                continue
            # Тот же порядок, что и для WB: поля карточки — в локальные
            # переменные до записи, чтобы skipped после отката не читал
            # атрибуты уже истёкшего ORM-объекта.
            vendor_code = ozon_card.offer_id
            raw = ozon_card.raw_json if isinstance(ozon_card.raw_json, dict) else None
            if raw is None:
                skipped.append(
                    {
                        "marketplace": "ozon",
                        "id": ozon_id,
                        "vendor_code": vendor_code,
                        "reason": "not_added",
                    }
                )
                continue
            result = OzonProductImportResult()
            try:
                await process_one_ozon_card(
                    session,
                    tenant_id,
                    seller_id,
                    raw,
                    ozon_context,
                    result,
                    allow_create=True,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "seller_catalog.add_to_fulfillment: failed to add Ozon card %s for seller %s",
                    ozon_id,
                    seller_id,
                )
                skipped.append(
                    {
                        "marketplace": "ozon",
                        "id": ozon_id,
                        "vendor_code": vendor_code,
                        "reason": "internal_error",
                    }
                )
                continue
            if result.links_created == 0 and result.links_matched == 0:
                # Не нашли товар и не завели (неоднозначный признак или у
                # карточки нет ни одного идентификатора) — та же причина, что
                # у аналогичного случая на стороне WB.
                skipped.append(
                    {
                        "marketplace": "ozon",
                        "id": ozon_id,
                        "vendor_code": vendor_code,
                        "reason": "not_added",
                    }
                )
                continue
            added.append(
                {
                    "marketplace": "ozon",
                    "id": ozon_id,
                    "vendor_code": vendor_code,
                    "products_added": result.products_created,
                }
            )

    return added, skipped


async def _link_unmatched_ozon_twins(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> None:
    """R13, WB→Ozon direction: link (never create) any not-yet-linked Ozon
    snapshot card that now matches a WB product just added in this request.
    The opposite direction (adding an Ozon card that matches an existing WB
    product) needs no extra step — ``process_one_ozon_card`` already searches
    every product of the seller, WB-origin included.
    """
    try:
        stmt = select(SellerOzonImportedCard).where(
            SellerOzonImportedCard.tenant_id == tenant_id,
            SellerOzonImportedCard.seller_id == seller_id,
            _ozon_not_on_fulfillment_condition(tenant_id, seller_id),
        )
        not_on_ff_cards = list((await session.execute(stmt)).scalars().all())
        if not not_on_ff_cards:
            return
        raw_cards = [
            card.raw_json for card in not_on_ff_cards if isinstance(card.raw_json, dict)
        ]
        if not raw_cards:
            return
        context = await build_ozon_match_context(session, tenant_id, seller_id)
        result = OzonProductImportResult()
        for raw in raw_cards:
            await process_one_ozon_card(
                session, tenant_id, seller_id, raw, context, result, allow_create=False
            )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "seller_catalog.add_to_fulfillment: failed to backfill Ozon twin links "
            "for seller %s",
            seller_id,
        )
