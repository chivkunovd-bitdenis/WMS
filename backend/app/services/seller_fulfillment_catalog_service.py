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

Only the WB half of the WMS-548 contract lives here. Ozon support (a new
snapshot table, ``ozon_product_ids`` in the add call, Ozon rows in the page)
is WMS-548 D3 and extends this module; until then ``marketplace="ozon"``
yields no not-on-fulfillment rows and any ``ozon_product_ids`` passed to
``add_cards_to_fulfillment`` come back skipped with ``ozon_not_supported_yet``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

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
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services.catalog_service import chunked, marketplace_scope_condition
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


def _dedupe_preserve_order(values: list[int]) -> list[int]:
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

    product_filters: list[Any] = [Product.tenant_id == tenant_id, Product.seller_id == seller_id]
    if marketplace_condition is not None:
        product_filters.append(marketplace_condition)
    product_filters.extend(_product_search_filters(tenant_id, search))
    product_filters.extend(_card_category_filters(category))

    card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    # Снимка карточек Ozon нет — та часть заведена в WMS-548 D3. До неё
    # marketplace=ozon просто не находит карточек, которых ещё нет на ФФ.
    if marketplace == "ozon":
        card_filters.append(false())
    card_filters.extend(_card_search_filters(search))
    card_filters.extend(_card_category_filters(category))

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
    card_branch = select(
        literal("wb_card").label("kind"),
        func.coalesce(
            SellerWildberriesImportedCard.vendor_code,
            cast(SellerWildberriesImportedCard.nm_id, String),
        ).label("sort_key"),
        cast(SellerWildberriesImportedCard.nm_id, String).label("raw_key"),
    ).where(*card_filters)

    universe: Any
    if on_fulfillment == "yes":
        universe = product_branch
    elif on_fulfillment == "no":
        universe = card_branch
    else:
        universe = union_all(product_branch, card_branch)
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
    scope_card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    if marketplace == "ozon":
        scope_card_filters.append(false())
    scope_total = int(
        await session.scalar(
            select(func.count()).select_from(Product).where(*scope_product_filters)
        )
        or 0
    ) + int(
        await session.scalar(
            select(func.count())
            .select_from(SellerWildberriesImportedCard)
            .where(*scope_card_filters)
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
    for kind, raw_key in page_rows:
        if kind == "product":
            product_ids.append(uuid.UUID(raw_key))
        else:
            nm_ids.append(int(raw_key))

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
        else:
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

    product_filters: list[Any] = [Product.tenant_id == tenant_id, Product.seller_id == seller_id]
    if marketplace_condition is not None:
        product_filters.append(marketplace_condition)
    product_filters.extend(_product_search_filters(tenant_id, search))
    product_filters.extend(_card_category_filters(category))

    card_filters: list[Any] = [
        SellerWildberriesImportedCard.tenant_id == tenant_id,
        SellerWildberriesImportedCard.seller_id == seller_id,
        _not_on_fulfillment_condition(tenant_id, seller_id),
    ]
    if marketplace == "ozon":
        card_filters.append(false())
    card_filters.extend(_card_search_filters(search))
    card_filters.extend(_card_category_filters(category))

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
        card_stmt = select(SellerWildberriesImportedCard.nm_id).where(*card_filters)
        keys.extend(f"wb:{nm_id}" for nm_id in (await session.scalars(card_stmt)).all())
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

    # Ozon: снимка карточек ещё нет (WMS-548 D3) — идентификаторы принимаем по
    # контракту, чтобы фронт D4/D5 не падал, но честно ничего не заводим.
    for ozon_id in dict.fromkeys(ozon_product_ids):
        skipped.append(
            {
                "marketplace": "ozon",
                "id": ozon_id,
                "vendor_code": None,
                "reason": "ozon_not_supported_yet",
            }
        )

    return added, skipped
