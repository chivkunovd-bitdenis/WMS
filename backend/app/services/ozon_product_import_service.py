"""Импорт карточек Ozon: габариты, вес, штрихкод и product_id связанного товара.

Импорта каталога Ozon в системе не было вовсе. Следствие из этого одно, но
дорогое: у чисто озоновского товара нет габаритов, значит нет объёма, значит
литро-дни нулевые и строка начисления за хранение не создаётся — товар лежит на
складе бесплатно, пока оператор не внесёт обмер руками.

Данные у Ozon есть, полные. Живой вызов `/v4/product/info/attributes`
03.09.2026 вернул по каждой из десяти карточек кабинета габариты с единицей
измерения, вес с единицей, собственный штрихкод вида ``OZN<sku>``, артикул
продавца и оба идентификатора — `id` (product_id) и `sku`.

Что этот импорт **не** делает и почему: он не заводит товары. Связку товара WMS
с карточкой Ozon по-прежнему создаёт человек — правила именования, продавца и
внутреннего SKU здесь угадывать нельзя. Импорт обогащает то, что уже связано.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services.catalog_service import update_product_dimensions
from app.services.marketplace_provider import OzonMarketplaceProvider

PRODUCT_ATTRIBUTES_PATH = "/v4/product/info/attributes"
# Живой ответ отдаёт сто карточек за страницу; больше Ozon и не отдаёт.
ATTRIBUTES_PAGE_LIMIT = 100
MAX_ATTRIBUTE_PAGES = 100

DIMENSIONS_SOURCE_OZON = "ozon"

# Единицы, которые мы умеем приводить к нашим миллиметрам и граммам. Живьём
# кабинет отдаёт `mm` и `g`; остальное не угадываем, а честно пропускаем —
# ошибиться в габаритах дороже, чем не заполнить их.
_LENGTH_TO_MM: dict[str, float] = {"mm": 1.0, "cm": 10.0}
_WEIGHT_TO_G: dict[str, float] = {"g": 1.0, "kg": 1000.0}

# Источники обмера, которые импорт не имеет права затирать: ручной обмер
# оператора, объём тары и карточку Wildberries человек выбрал осознанно.
_OVERWRITABLE_SOURCES = frozenset({DIMENSIONS_SOURCE_OZON})


@dataclass
class OzonProductImportResult:
    cards_read: int = 0
    links_matched: int = 0
    dimensions_applied: int = 0
    barcodes_applied: int = 0
    product_ids_applied: int = 0
    skipped_unknown_units: int = 0
    skipped_manual_dimensions: int = 0
    unmatched_offer_ids: list[str] = field(default_factory=list)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


def card_dimensions_mm(card: Mapping[str, Any]) -> tuple[int, int, int] | None:
    """Габариты карточки в наших миллиметрах.

    У Ozon длина называется `depth`, а единица измерения приходит отдельным
    полем `dimension_unit` — гадать про неё не нужно и нельзя.
    """
    unit = (_text_or_none(card.get("dimension_unit")) or "").lower()
    factor = _LENGTH_TO_MM.get(unit)
    if factor is None:
        return None
    depth = _int_or_none(card.get("depth"))
    width = _int_or_none(card.get("width"))
    height = _int_or_none(card.get("height"))
    if depth is None or width is None or height is None:
        return None
    length_mm = round(depth * factor)
    width_mm = round(width * factor)
    height_mm = round(height * factor)
    if min(length_mm, width_mm, height_mm) <= 0:
        return None
    return length_mm, width_mm, height_mm


def card_weight_g(card: Mapping[str, Any]) -> int | None:
    unit = (_text_or_none(card.get("weight_unit")) or "").lower()
    factor = _WEIGHT_TO_G.get(unit)
    if factor is None:
        return None
    weight = _int_or_none(card.get("weight"))
    if weight is None or weight <= 0:
        return None
    return round(weight * factor)


def card_barcodes(card: Mapping[str, Any]) -> list[str]:
    """Собственный штрихкод Ozon вида ``OZN<sku>`` плюс всё, что рядом."""
    values: list[str] = []
    raw_list = card.get("barcodes")
    if isinstance(raw_list, list):
        for item in raw_list:
            text = _text_or_none(item)
            if text is not None and text not in values:
                values.append(text)
    single = _text_or_none(card.get("barcode"))
    if single is not None and single not in values:
        values.append(single)
    return values


async def find_product_ids_by_marketplace_barcode(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    codes: list[str],
    *,
    seller_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """Найти товар по штрихкоду маркетплейса, которого нет в наших полях.

    Ozon присваивает товару собственный штрихкод вида ``OZN<sku>`` — это живой
    факт, проверенный по всем десяти карточкам кабинета. Наши сканеры ищут
    ровно по двум полям товара, `wb_barcode` и `sku_code`, поэтому кладовщик,
    поднёсший сканер к коробке с озоновской этикеткой, получал «объект с таким
    кодом не найден».

    Поле под эти штрихкоды в схеме было (`external_barcodes`) и стояло пустым:
    ни одной записи, ни одного чтения. Теперь его заполняет импорт карточек, а
    эта функция — единственный читатель, общий для всех сканеров.

    Вызывать её нужно **только когда обычный поиск ничего не нашёл**: путь
    Wildberries тогда не меняется ни поведением, ни ценой запроса.
    """
    normalized = [code.strip() for code in codes if code and code.strip()]
    if not normalized:
        return []
    conditions = [
        ProductMarketplaceLink.external_sku.in_(normalized),
        ProductMarketplaceLink.external_offer_id.in_(normalized),
    ]
    # `external_barcodes` — JSON-массив строк; сравнение по тексту с кавычками
    # работает одинаково в SQLite и PostgreSQL и не даёт ложных совпадений по
    # части кода.
    for code in normalized:
        conditions.append(
            cast(ProductMarketplaceLink.external_barcodes, String).like(f'%"{code}"%')
        )
    stmt = select(ProductMarketplaceLink.product_id).where(
        ProductMarketplaceLink.tenant_id == tenant_id,
        ProductMarketplaceLink.is_active.is_(True),
        or_(*conditions),
    )
    if seller_id is not None:
        stmt = stmt.where(ProductMarketplaceLink.seller_id == seller_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return list(dict.fromkeys(rows))


async def fetch_product_cards(
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
) -> list[dict[str, Any]]:
    """Пройти каталог Ozon постранично и вернуть карточки как есть."""
    cards: list[dict[str, Any]] = []
    last_id = ""
    for _ in range(MAX_ATTRIBUTE_PAGES):
        payload: dict[str, Any] = {
            "filter": {"visibility": "ALL"},
            "limit": ATTRIBUTES_PAGE_LIMIT,
        }
        if last_id:
            payload["last_id"] = last_id
        raw = await provider.call(
            client_id=client_id,
            api_key=api_key,
            path=PRODUCT_ATTRIBUTES_PATH,
            payload=payload,
        )
        if not isinstance(raw, dict):
            break
        page = raw.get("result")
        rows = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
        cards.extend(rows)
        next_id = raw.get("last_id")
        last_id = next_id if isinstance(next_id, str) else ""
        if not last_id or len(rows) < ATTRIBUTES_PAGE_LIMIT:
            break
    return cards


def _link_matches(link: ProductMarketplaceLink, card: Mapping[str, Any]) -> bool:
    sku = _text_or_none(card.get("sku"))
    offer_id = _text_or_none(card.get("offer_id"))
    product_id = _text_or_none(card.get("id"))
    return bool(
        (sku is not None and link.external_sku == sku)
        or (offer_id is not None and link.external_offer_id == offer_id)
        or (product_id is not None and link.external_product_id == product_id)
    )


async def import_ozon_product_cards(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    provider: OzonMarketplaceProvider,
    *,
    client_id: str,
    api_key: str,
    commit: bool = True,
) -> OzonProductImportResult:
    """Обогатить связанные с Ozon товары данными карточки маркетплейса."""
    cards = await fetch_product_cards(provider, client_id=client_id, api_key=api_key)
    result = OzonProductImportResult(cards_read=len(cards))
    if not cards:
        return result

    links = list(
        (
            await session.execute(
                select(ProductMarketplaceLink).where(
                    ProductMarketplaceLink.tenant_id == tenant_id,
                    ProductMarketplaceLink.seller_id == seller_id,
                    ProductMarketplaceLink.marketplace == "ozon",
                    ProductMarketplaceLink.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    for card in cards:
        link = next((item for item in links if _link_matches(item, card)), None)
        if link is None:
            offer_id = _text_or_none(card.get("offer_id"))
            if offer_id is not None:
                result.unmatched_offer_ids.append(offer_id)
            continue
        result.links_matched += 1

        # `product_id` и `sku` у Ozon — разные числа, и публикация остатков
        # подписывается именно product_id. Раньше поля под него не заполнял никто.
        product_id = _text_or_none(card.get("id"))
        if product_id is not None and link.external_product_id != product_id:
            link.external_product_id = product_id
            result.product_ids_applied += 1
        sku = _text_or_none(card.get("sku"))
        if sku is not None and not link.external_sku:
            link.external_sku = sku
        offer_id = _text_or_none(card.get("offer_id"))
        if offer_id is not None and not link.external_offer_id:
            link.external_offer_id = offer_id
        barcodes = card_barcodes(card)
        if barcodes and list(link.external_barcodes or []) != barcodes:
            link.external_barcodes = barcodes
            result.barcodes_applied += 1

        product = await session.get(Product, link.product_id)
        if product is None:
            continue
        dimensions = card_dimensions_mm(card)
        weight_g = card_weight_g(card)
        if dimensions is None:
            if card.get("depth") is not None or card.get("width") is not None:
                result.skipped_unknown_units += 1
            continue
        if product.dimensions_source is not None and (
            product.dimensions_source not in _OVERWRITABLE_SOURCES
        ):
            # Обмер, выбранный человеком, импорт не трогает.
            result.skipped_manual_dimensions += 1
            continue
        length_mm, width_mm, height_mm = dimensions
        await update_product_dimensions(
            session,
            tenant_id,
            product.id,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=height_mm,
            weight_g=weight_g,
            weight_g_set=weight_g is not None,
            source=DIMENSIONS_SOURCE_OZON,
            author_user_id=None,
            commit=False,
        )
        result.dimensions_applied += 1

    if commit:
        await session.commit()
    else:
        await session.flush()
    return result
