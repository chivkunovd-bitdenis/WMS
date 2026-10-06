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

import asyncio
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any, Literal, TypeVar

from sqlalchemy import (
    JSON,
    ColumnElement,
    Connection,
    Select,
    String,
    Text,
    and_,
    case,
    cast,
    exists,
    false,
    func,
    literal,
    or_,
    select,
    text,
    type_coerce,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
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
from app.services.wb_honest_sign_service import WbCategoryCatalog
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards

logger = logging.getLogger(__name__)

OnFulfillmentFilter = Literal["all", "yes", "no"]
MarketplaceFilter = Literal["wildberries", "ozon"]

# Python str.strip() whitespace, shared by SQLite/PostgreSQL trim so SQL
# category/size labels match the existing displayed labels (including NBSP).
_DISPLAY_WHITESPACE = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)

# Тот же порядок величины, что и у пачек nmID/product_id в других местах
# каталога (см. catalog_service.ID_IN_BATCH_SIZE) — но контракт /seller-catalog
# ограничивает запрос на добавление 500 идентификаторами, так что здесь это
# скорее документирует лимит контракта, чем защищает от IN-запроса на тысячи id.
ADD_TO_FULFILLMENT_MAX_IDS = 500

_T = TypeVar("_T")

# F1 (review-astra-1/2, блокер): два запроса с разными nmID, но одним и тем
# же вычисленным артикулом/ШК, проходят _card_has_vendor_code_conflict
# одновременно — ни один ещё не создал товар, конфликта не видно. Дальше
# upsert_products_from_wb_cards разрешает гонку уникального индекса своим
# штатным повторным поиском и молча переписывает найденный товар под вторую
# карточку (её nmID, ШК, название) — карточка, которую вторая карточка
# должна была получить отказ, вместо этого ворует чужую. Внутренности
# upsert_products_from_wb_cards трогать нельзя (граница WMS-535); общий
# замок обмена (marketplace_seller_lock_service), который держит WB/Ozon
# синк и от которого явно предостерёг ревьюер (владельческий случай B01 —
# он не должен блокировать FBS), тоже не подходит и не переиспользуется —
# отдельное пространство ключей.
#
# Боевой API — два процесса (`uvicorn --workers 2`, WMS-538), поэтому
# внутрипроцессный asyncio.Lock ниже сам по себе гонку МЕЖДУ процессами не
# закрывает — он только экономит поход в PostgreSQL для гонки внутри одного
# процесса; реальная межпроцессная защита — только advisory-lock.
#
# Раунд 1 брал сессионный pg_advisory_lock прямо на рабочей AsyncSession —
# класс утечки WMS-435. upsert коммитит на каждый размер карточки отдельно;
# после commit SQLAlchemy возвращает физическое соединение в пул, а
# следующий запрос той же сессии может получить уже ДРУГОЕ соединение.
# Сессионный лок остаётся висеть на первом, отданном в пул навсегда:
# pg_advisory_unlock на втором соединении просто не находит, что снимать
# (возвращает false). Транзакционный pg_advisory_xact_lock тоже не годится:
# он снялся бы на первом же внутреннем коммите, не защитив остальные
# размеры многоразмерной карточки. Правильный уровень — отдельное
# закреплённое соединение (не рабочая session), которое берёт лок и само же
# его снимает, живёт ровно на время операции и не возвращается в пул, если
# снятие не удалось.
_wb_claim_locks: dict[tuple[uuid.UUID, uuid.UUID], asyncio.Lock] = {}

# Ждать замок ограниченное время, а не бесконечно: зависший запрос на одном
# воркере не должен вечно держать открытым соединение другого воркера.
_WB_CLAIM_LOCK_WAIT_SEC = 5.0
_WB_CLAIM_LOCK_POLL_SEC = 0.1


class WbClaimLockTimeout(RuntimeError):
    """Не удалось получить замок притязания на карточку WB за отведённое время."""


def _wb_claim_lock(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> asyncio.Lock:
    key = (tenant_id, seller_id)
    lock = _wb_claim_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _wb_claim_locks[key] = lock
    return lock


def _wb_claim_advisory_key(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> int:
    digest = hashlib.sha256(f"wms548:wb-claim:{tenant_id}:{seller_id}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


@asynccontextmanager
async def _wb_card_identity_claim(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> AsyncIterator[None]:
    """Serialize one seller's "is this sku/barcode free — then claim it" WB
    section end to end, so a concurrent card for a different nmID can never
    observe "free" before the first card's write is visible (WMS-548 F1, А12).

    The advisory lock is acquired and released on its own dedicated
    connection (``bind.connect()``), never on the caller's ``session`` —
    that connection is held open for the whole ``yield``, independent of
    however many times ``session`` itself commits inside it (WMS-435 class
    of leak: a session-scoped lock taken on a connection that gets handed
    back to the pool by an intervening commit is a lock nobody can ever
    release again).
    """
    async with _wb_claim_lock(tenant_id, seller_id):
        bind = session.bind
        if bind is None or bind.dialect.name != "postgresql":
            # SQLite (тесты): нет отдельного процесса, с которым нужно
            # делить advisory-lock — внутрипроцессный лок выше уже
            # сериализовал секцию для реальной асинхронной гонки.
            yield
            return
        key = _wb_claim_advisory_key(tenant_id, seller_id)
        engine = bind.engine if isinstance(bind, AsyncConnection) else bind
        async with engine.connect() as lock_conn:
            acquired = await _try_acquire_advisory_lock(
                lock_conn, key, wait_sec=_WB_CLAIM_LOCK_WAIT_SEC, poll_sec=_WB_CLAIM_LOCK_POLL_SEC
            )
            if not acquired:
                raise WbClaimLockTimeout(
                    f"WB claim lock not acquired within {_WB_CLAIM_LOCK_WAIT_SEC}s "
                    f"for seller {seller_id}"
                )
            try:
                yield
            finally:
                await _release_advisory_lock(lock_conn, key, seller_id=seller_id)


async def _try_acquire_advisory_lock(
    connection: Any, key: int, *, wait_sec: float, poll_sec: float
) -> bool:
    deadline = monotonic() + wait_sec
    while True:
        result = await connection.execute(text("select pg_try_advisory_lock(:key)"), {"key": key})
        if bool(result.scalar()):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(poll_sec, remaining))


async def _release_advisory_lock(connection: Any, key: int, *, seller_id: uuid.UUID) -> None:
    """Best-effort unlock; the connection is never returned to the pool alive
    if we cannot confirm the lock was actually released on it (WMS-435).
    """
    try:
        result = await connection.execute(text("select pg_advisory_unlock(:key)"), {"key": key})
        if not bool(result.scalar()):
            # Снятие вернуло false — лок не был удержан этим соединением
            # (не должно происходить при корректной работе, но если
            # случилось — соединение непредсказуемо, в пул не возвращаем).
            logger.error(
                "seller_catalog.add_to_fulfillment: pg_advisory_unlock returned false "
                "for seller %s — invalidating the lock connection instead of pooling it",
                seller_id,
            )
            await connection.invalidate()
    except Exception:
        logger.exception(
            "seller_catalog.add_to_fulfillment: failed to release WB claim lock "
            "for seller %s",
            seller_id,
        )
        try:
            await connection.invalidate()
        except Exception:
            logger.exception(
                "seller_catalog.add_to_fulfillment: failed to invalidate the WB claim "
                "lock connection for seller %s",
                seller_id,
            )


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
                # WMS-548 F6: до добавления карточки её ШК находится через JSON
                # снимка; после добавления это единственное место, где Ozon-ШК
                # вообще хранится (в Product.wb_barcode их не копируем — один
                # код в двух местах расходится со временем), иначе товар
                # переставал находиться по своему ШК сразу после выбора.
                cast(ProductMarketplaceLink.external_barcodes, String).ilike(
                    f'%"{normalized}"%'
                ),
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


async def _catalog_fields(session: AsyncSession) -> tuple[Any, Any, Any, Any, Any]:
    """SQL equivalents of the displayed category and WB size labels.

    Keep JSON expansion correlated: variants never multiply catalog rows.
    SQLite's built-in lower is ASCII-only; a connection-local function gives
    the same Cyrillic comparison as PostgreSQL without writing to the database.
    """
    sqlite = session.get_bind().dialect.name == "sqlite"
    if sqlite:
        connection = await session.connection()

        def register_lower(conn: Connection) -> None:
            dbapi = conn.connection.dbapi_connection
            assert dbapi is not None
            dbapi.create_function(
                "catalog_lower",
                1,
                lambda value: value.lower() if value is not None else None,
                deterministic=True,
            )

        await connection.run_sync(register_lower)
    raw = SellerWildberriesImportedCard.raw_json
    sizes_json = raw["sizes"]
    array_type = func.json_type(sizes_json) if sqlite else func.json_typeof(sizes_json)
    sizes_json = case(
        (array_type == "array", sizes_json),
        else_=(literal("[]") if sqlite else cast(literal("[]"), JSON)),
    )
    entries = (
        func.json_each(sizes_json).table_valued("key", "value", "type")
        if sqlite
        else func.json_array_elements(sizes_json).table_valued(
            "value", with_ordinality="ordinality"
        )
    )
    ordinal = entries.c.key if sqlite else entries.c.ordinality
    entry_type = entries.c.type if sqlite else func.json_typeof(entries.c.value)
    entry = type_coerce(
        case(
            (entry_type == "object", entries.c.value),
            else_=(literal("{}") if sqlite else cast(literal("{}"), JSON)),
        ),
        JSON,
    )
    label = func.coalesce(
        *(
            case(
                (
                    (func.json_type(entry[key]) if sqlite else func.json_typeof(entry[key]))
                    == ("text" if sqlite else "string"),
                    func.nullif(func.trim(entry[key].as_string(), _DISPLAY_WHITESPACE), ""),
                ),
                else_=None,
            )
            for key in ("techSize", "wbSize")
        ),
    )
    labels = (
        select(label.label("label"))
        .select_from(entries)
        .where(label.is_not(None))
        .group_by(label)
        .order_by(func.min(ordinal))
        .correlate(SellerWildberriesImportedCard)
        .subquery()
    )
    aggregate = (
        func.group_concat(labels.c.label, ", ") if sqlite else func.string_agg(labels.c.label, ", ")
    )
    card_size = select(aggregate).select_from(labels).scalar_subquery()
    skus_json = entry["skus"]
    skus_type = func.json_type(skus_json) if sqlite else func.json_typeof(skus_json)
    skus_json = case(
        (skus_type == "array", skus_json),
        else_=(literal("[]") if sqlite else cast(literal("[]"), JSON)),
    )
    skus = (
        func.json_each(skus_json) if sqlite else func.json_array_elements_text(skus_json)
    ).table_valued("value")
    stored_barcode = (
        select(ProductBarcode.barcode)
        .where(
            ProductBarcode.tenant_id == Product.tenant_id,
            ProductBarcode.seller_id == Product.seller_id,
            ProductBarcode.product_id == Product.id,
            ProductBarcode.source == "wb",
        )
        .order_by(ProductBarcode.barcode, ProductBarcode.id)
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )
    primary_barcode = func.coalesce(func.nullif(func.trim(Product.wb_barcode), ""), stored_barcode)
    barcode_matches = exists(
        select(1)
        .select_from(skus)
        .where(func.trim(cast(skus.c.value, String)) == primary_barcode)
        .correlate(entries, Product)
    )
    count = (
        select(func.count())
        .select_from(entries)
        .correlate(SellerWildberriesImportedCard)
        .scalar_subquery()
    )
    fallback_size = (
        select(label)
        .select_from(entries)
        .where(label.is_not(None), or_(barcode_matches, count == 1))
        .order_by(ordinal)
        .limit(1)
        .correlate(Product, SellerWildberriesImportedCard)
        .scalar_subquery()
    )
    product_size = func.coalesce(
        func.nullif(func.trim(Product.wb_size, _DISPLAY_WHITESPACE), ""), fallback_size
    )
    category = func.coalesce(
        *(
            case(
                (
                    (func.json_type(raw[key]) if sqlite else func.json_typeof(raw[key]))
                    == ("text" if sqlite else "string"),
                    func.nullif(func.trim(raw[key].as_string(), _DISPLAY_WHITESPACE), ""),
                ),
                else_=None,
            )
            for key in ("subjectName", "subject_name")
        ),
    )
    return category, product_size, card_size, entries, label


def _exact_catalog_filters(value: Any, requested: str | None, sqlite: bool) -> list[Any]:
    normalized = (requested or "").strip().lower()
    if not normalized:
        return []
    lower = func.catalog_lower if sqlite else func.lower
    return [lower(func.trim(value)) == normalized]


def _catalog_extra_filters(
    tenant_id: uuid.UUID,
    article: str | None,
    size: str | None,
    stock_only: bool,
    sqlite: bool,
    product_size: Any,
    entries: Any,
    label: Any,
) -> tuple[list[Any], list[Any], list[Any]]:
    products = _exact_catalog_filters(Product.wb_vendor_code, article, sqlite)
    products.extend(_exact_catalog_filters(product_size, size, sqlite))
    wb = _exact_catalog_filters(SellerWildberriesImportedCard.vendor_code, article, sqlite)
    if (size or "").strip():
        wb.append(
            exists(
                select(1)
                .select_from(entries)
                .where(*_exact_catalog_filters(label, size, sqlite))
                .correlate(SellerWildberriesImportedCard)
            )
        )
    ozon = _exact_catalog_filters(SellerOzonImportedCard.offer_id, article, sqlite)
    if (size or "").strip():
        ozon.append(false())
    if stock_only:
        quantity = (
            select(func.sum(InventoryBalance.quantity))
            .where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == Product.id,
            )
            .correlate(Product)
            .scalar_subquery()
        )
        products.append(quantity > 0)
        wb.append(false())
        ozon.append(false())
    return products, wb, ozon


async def list_seller_catalog_page(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    search: str | None = None,
    category: str | None = None,
    article: str | None = None,
    size: str | None = None,
    stock_only: bool = False,
    group_by: Literal["category_article_size"] | None = None,
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

    subject, product_size, card_size, entries, label = await _catalog_fields(session)
    product_extra, wb_extra, ozon_extra = _catalog_extra_filters(
        tenant_id, article, size, stock_only,
        session.get_bind().dialect.name == "sqlite", product_size, entries, label,
    )
    product_filters.extend(product_extra)
    wb_card_filters.extend(wb_extra)
    ozon_card_filters.extend(ozon_extra)

    product_branch = (
        select(
            literal("product").label("kind"),
            subject.label("group_category"),
            Product.wb_vendor_code.label("group_article"),
            product_size.label("group_size"),
            Product.sku_code.label("sort_key"),
            cast(Product.id, String).label("raw_key"),
        )
        .select_from(Product)
        .outerjoin(SellerWildberriesImportedCard, card_join)
        .where(*product_filters)
    )
    wb_card_branch = select(
        literal("wb_card").label("kind"),
        subject.label("group_category"),
        SellerWildberriesImportedCard.vendor_code.label("group_article"),
        card_size.label("group_size"),
        func.coalesce(
            SellerWildberriesImportedCard.vendor_code,
            cast(SellerWildberriesImportedCard.nm_id, String),
        ).label("sort_key"),
        cast(SellerWildberriesImportedCard.nm_id, String).label("raw_key"),
    ).where(*wb_card_filters)
    ozon_card_branch = select(
        literal("ozon_card").label("kind"),
        literal(None, String).label("group_category"),
        SellerOzonImportedCard.offer_id.label("group_article"),
        literal(None, String).label("group_size"),
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

    order = [universe_subq.c.sort_key, universe_subq.c.kind, universe_subq.c.raw_key]
    if group_by == "category_article_size":
        order = [
            func.coalesce(universe_subq.c.group_category, ""),
            func.coalesce(universe_subq.c.group_article, ""),
            func.coalesce(universe_subq.c.group_size, ""),
            universe_subq.c.kind, universe_subq.c.raw_key,
        ]
    page_stmt = (
        select(universe_subq.c.kind, universe_subq.c.raw_key)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    )
    page_rows = list((await session.execute(page_stmt)).all())

    # PostgreSQL требует, чтобы выражение в ORDER BY при SELECT DISTINCT было
    # ровно тем же элементом плана, что и в списке выборки — два раздельных
    # вызова .as_string() дают два разных bind-параметра и валят запрос
    # InvalidColumnReference (SQLite этого не проверяет и не ловит). Заводим
    # выражение один раз и переиспользуем объект везде.
    subject_expr = SellerWildberriesImportedCard.raw_json["subjectName"].as_string()
    category_stmt = (
        select(subject_expr)
        .where(
            SellerWildberriesImportedCard.tenant_id == tenant_id,
            SellerWildberriesImportedCard.seller_id == seller_id,
            subject_expr.is_not(None),
            subject_expr != "",
        )
        .distinct()
        .order_by(subject_expr)
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
    article: str | None = None,
    size: str | None = None,
    stock_only: bool = False,
    group_by: Literal["category_article_size"] | None = None,
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

    _subject, product_size, _card_size, entries, label = await _catalog_fields(session)
    product_extra, wb_extra, ozon_extra = _catalog_extra_filters(
        tenant_id, article, size, stock_only,
        session.get_bind().dialect.name == "sqlite", product_size, entries, label,
    )
    product_filters.extend(product_extra)
    wb_card_filters.extend(wb_extra)
    ozon_card_filters.extend(ozon_extra)

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
    marking_catalog: WbCategoryCatalog | None = None,
    marking_catalog_error: str | None = None,
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
    added_wb_nm_ids: list[int] = []
    if nm_ids:
        if marking_catalog_error is not None:
            logger.warning(
                "seller_catalog.add_to_fulfillment: WB marking catalog unavailable "
                "seller=%s; clothing inference deferred",
                seller_id,
            )
        cards_by_nm: dict[int, SellerWildberriesImportedCard] = {}
        for batch in chunked(sorted(set(nm_ids)), 2000):
            stmt = select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.tenant_id == tenant_id,
                SellerWildberriesImportedCard.seller_id == seller_id,
                SellerWildberriesImportedCard.nm_id.in_(batch),
            )
            for card_row in (await session.execute(stmt)).scalars().all():
                cards_by_nm[int(card_row.nm_id)] = card_row

        # WMS-548 F3: карточки читаются в простые значения одним проходом,
        # до первого апсерта. upsert_products_from_wb_cards коммитит на
        # каждый размер отдельно, а неудача другой карточки в этом же цикле
        # коммитит откат — он истекает атрибуты ВСЕХ объектов сессии, в том
        # числе ещё не обработанных карточек из cards_by_nm. Чтение
        # card.vendor_code/raw_json такого объекта после чужого отката
        # запускало ленивую подгрузку и падало MissingGreenlet вместо
        # честного skipped для всех карточек после сбойной.
        card_data_by_nm: dict[int, tuple[str | None, dict[str, Any] | None]] = {
            nm: (card.vendor_code, card.raw_json if isinstance(card.raw_json, dict) else None)
            for nm, card in cards_by_nm.items()
        }

        for nm_id in nm_ids:
            card_data = card_data_by_nm.get(nm_id)
            if card_data is None:
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
            vendor_code, raw = card_data
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
                # WMS-548 F1: конфликт-предчек и апсерт — одна атомарная
                # секция на весь seller: другая карточка того же продавца не
                # может пройти свой предчек, пока эта не закончила запись.
                async with _wb_card_identity_claim(session, tenant_id, seller_id):
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
                        session,
                        tenant_id,
                        seller_id,
                        [raw],
                        marking_catalog=marking_catalog,
                        marking_catalog_error=marking_catalog_error,
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
            added_wb_nm_ids.append(nm_id)

        # R13: a WB card just added may have an Ozon twin already sitting in
        # this seller's Ozon snapshot, unlinked. Link it now (never create —
        # the product already exists) so the twin stops showing as a separate
        # "not on fulfillment" row. Best-effort: it never touches, let alone
        # undoes, the WB cards already committed above.
        if added_wb_nm_ids:
            added_product_ids = list(
                (
                    await session.scalars(
                        select(Product.id).where(
                            Product.tenant_id == tenant_id,
                            Product.seller_id == seller_id,
                            Product.wb_nm_id.in_(added_wb_nm_ids),
                        )
                    )
                ).all()
            )
            await _link_unmatched_ozon_twins(session, tenant_id, seller_id, added_product_ids)

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

        # WMS-548 F3: тот же приём, что и для WB — простые значения одним
        # проходом, не трогая карточку повторно после отката другой.
        ozon_card_data_by_id: dict[str, tuple[str | None, dict[str, Any] | None]] = {
            ozon_id: (
                ozon_card.offer_id,
                ozon_card.raw_json if isinstance(ozon_card.raw_json, dict) else None,
            )
            for ozon_id, ozon_card in ozon_cards_by_id.items()
        }

        # Один контекст на весь запрос — не на карточку (WMS-538): иначе
        # каждая из до 500 карточек читала бы товары продавца заново.
        ozon_context = await build_ozon_match_context(session, tenant_id, seller_id)

        for ozon_id in ozon_ids:
            ozon_card_data = ozon_card_data_by_id.get(ozon_id)
            if ozon_card_data is None:
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
            vendor_code, raw = ozon_card_data
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
                # WMS-548 F3: откат истёк ссылки, закешированные в
                # ozon_context (links_by_*) — следующая карточка этой же
                # порции читала бы их атрибуты и падала MissingGreenlet.
                # Пересобираем контекст с нуля перед следующей итерацией.
                ozon_context = await build_ozon_match_context(session, tenant_id, seller_id)
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
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    added_product_ids: Sequence[uuid.UUID],
) -> None:
    """R13, WB→Ozon direction: link (never create) any not-yet-linked Ozon
    snapshot card that now matches one of the WB products just added in this
    request. The opposite direction (adding an Ozon card that matches an
    existing WB product) needs no extra step — ``process_one_ozon_card``
    already searches every product of the seller, WB-origin included.

    WMS-548 F5: reads only Ozon snapshot rows that could possibly match one
    of ``added_product_ids`` (by the same offer_id/sku/barcode signals
    ``match_card_to_product`` itself uses) — not every not-yet-linked Ozon
    card of the seller. A seller with thousands of unrelated Ozon cards must
    not pay for scanning all of them on every single WB card added.
    """
    if not added_product_ids:
        return
    try:
        rows = (
            await session.execute(
                select(
                    Product.sku_code,
                    Product.wb_barcode,
                    Product.wb_nm_id,
                    Product.wb_vendor_code,
                ).where(
                    Product.tenant_id == tenant_id,
                    Product.seller_id == seller_id,
                    Product.id.in_(added_product_ids),
                )
            )
        ).all()
        candidate_offer_ids: set[str] = set()
        candidate_barcodes: set[str] = set()
        for sku_code, wb_barcode, wb_nm_id, wb_vendor_code in rows:
            if sku_code:
                candidate_offer_ids.add(sku_code)
            # Та же сборка, что и oz_transfer_offer_id в ozon_product_import_
            # service (не импортируем ради одного товара с UUID-заглушкой,
            # который эта функция всё равно не использует).
            if wb_nm_id is not None and wb_vendor_code:
                candidate_offer_ids.add(f"OZ{wb_nm_id}{wb_vendor_code}")
            if wb_barcode:
                candidate_barcodes.add(wb_barcode)
        if not candidate_offer_ids and not candidate_barcodes:
            return

        candidate_conditions: list[Any] = []
        if candidate_offer_ids:
            candidate_conditions.append(
                SellerOzonImportedCard.offer_id.in_(candidate_offer_ids)
            )
        for barcode in candidate_barcodes:
            candidate_conditions.append(
                cast(SellerOzonImportedCard.raw_json, Text).ilike(f'%"{barcode}"%')
            )

        stmt = select(SellerOzonImportedCard).where(
            SellerOzonImportedCard.tenant_id == tenant_id,
            SellerOzonImportedCard.seller_id == seller_id,
            _ozon_not_on_fulfillment_condition(tenant_id, seller_id),
            or_(*candidate_conditions),
        )
        candidate_cards = list((await session.execute(stmt)).scalars().all())
        if not candidate_cards:
            return
        raw_cards = [
            card.raw_json for card in candidate_cards if isinstance(card.raw_json, dict)
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
