"""Импорт каталога Ozon: товары, связки, габариты, вес, штрихкод и фото.

Каталога Ozon в системе не было вовсе. Селлер вводил Client-Id и Api-Key — и
дальше не происходило ничего: товары приходилось заводить руками, а связку
«карточка WMS ↔ карточка Ozon» человек ставил по одной штуке. Теперь импорт
ведёт себя как вайлдберрисовский: тянет все карточки кабинета, сам находит
среди наших товаров тот, о котором карточка, а чего не нашёл — заводит.

Данные у Ozon есть, полные. Живой вызов `/v4/product/info/attributes`
03.09.2026 вернул по каждой из десяти карточек кабинета габариты с единицей
измерения, вес с единицей, собственный штрихкод вида ``OZN<sku>``, артикул
продавца и оба идентификатора — `id` (product_id) и `sku`. Тот же ответ несёт
`primary_image` — ссылку на главное фото, которой у чисто озоновского товара
до сих пор не было ни на одном из пятнадцати экранов.

Как ставится связка (по убыванию надёжности, первое однозначное совпадение
выигрывает, при неоднозначности не связываем вовсе):

1. **Штрихкод.** Один и тот же физический товар на двух площадках несёт один
   код. Собственный штрихкод Ozon вида ``OZN<sku>`` из сравнения выкидываем: он
   выдан самим Ozon и в WMS его быть не может. Признак различает размеры — у
   каждого размера свой штрихкод.
2. **Артикул продавца.** `offer_id` карточки против `sku_code` товара. Артикул
   уникален внутри продавца ограничением базы, поэтому совпадение однозначно
   по построению.
3. **Разбор артикула, собранного переносом с Wildberries.** Артикулы кабинета
   собраны по формуле ``OZ`` + nmID + артикул продавца. Проверяем не разбором
   строки, а сборкой: складываем ожидаемый артикул из полей нашего товара и
   сравниваем целиком — тогда нечего угадывать про длину nmID. У размерного
   товара все размеры одной модели дают одну и ту же строку, совпадений выходит
   больше одного — такую карточку не связываем и не заводим, её объединит
   оператор руками.

Чем связка **не** ставится и почему: угадыванием по названию и близости строк.
Ошибочная склейка двух карточек сводит вместе чужие остатки, и разобрать это
потом дороже, чем не связать вовсе.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from sqlalchemy import String, cast, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services.catalog_service import OZON_PRIMARY_IMAGE_KEY, update_product_dimensions
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
    links_created: int = 0
    products_created: int = 0
    dimensions_applied: int = 0
    barcodes_applied: int = 0
    images_applied: int = 0
    product_ids_applied: int = 0
    skipped_unknown_units: int = 0
    skipped_manual_dimensions: int = 0
    # Карточки, по которым мы не связали и не завели ничего: либо признак дал
    # больше одного кандидата (размерный товар), либо товар с таким артикулом
    # уже есть и занят. Их объединяет оператор руками.
    unmatched_offer_ids: list[str] = field(default_factory=list)


class ProductMatchKey(NamedTuple):
    """Поля товара WMS, по которым вообще возможно сопоставление с Ozon."""

    product_id: uuid.UUID
    sku_code: str
    wb_barcode: str | None
    wb_nm_id: int | None
    wb_vendor_code: str | None


@dataclass(frozen=True)
class CardMatch:
    """Кому принадлежит карточка Ozon: конкретному товару, никому или неясно."""

    product_id: uuid.UUID | None = None
    ambiguous: bool = False


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


def _own_ozon_barcode(card: Mapping[str, Any]) -> str | None:
    """Штрихкод, который Ozon выдал сам: ``OZN`` плюс его же SKU."""
    sku = _text_or_none(card.get("sku"))
    return f"OZN{sku}" if sku is not None else None


def card_matchable_barcodes(card: Mapping[str, Any]) -> list[str]:
    """Штрихкоды карточки без собственного кода Ozon.

    Сравнивать ``OZN<sku>`` с нашими штрихкодами бессмысленно: этот код выдан
    самим Ozon и в карточке WMS его взяться неоткуда. Оставить его в сравнении —
    значит гарантированно не найти ни одного совпадения и молча завести дубль.
    """
    own = _own_ozon_barcode(card)
    return [code for code in card_barcodes(card) if code != own]


def card_primary_image_url(card: Mapping[str, Any]) -> str | None:
    """Главное фото карточки: `primary_image`, иначе первое из `images`.

    Ozon отдаёт главное фото отдельным полем, а если продавец его не выбрал —
    главным считается первое изображение массива. Порядок здесь ровно такой же,
    как у нас на экране: одна картинка, самая первая.
    """
    primary = card.get("primary_image")
    if isinstance(primary, list):
        # У соседней ручки (`/v3/product/info/list`) это поле — массив.
        primary = next((item for item in primary if _text_or_none(item)), None)
    text = _text_or_none(primary)
    if text is not None:
        return text
    images = card.get("images")
    if isinstance(images, list):
        for item in images:
            text = _text_or_none(item)
            if text is not None:
                return text
    return None


def oz_transfer_offer_id(product: ProductMatchKey) -> str | None:
    """Артикул, который получил бы этот товар при переносе с WB на Ozon.

    Собираем ожидаемую строку из своих полей и сравниваем целиком, вместо того
    чтобы разбирать чужую. Разбор потребовал бы знать, где кончается nmID и
    начинается артикул продавца, — а артикул продавца сам может начинаться с
    цифр, и точка разреза была бы догадкой.
    """
    if product.wb_nm_id is None or not product.wb_vendor_code:
        return None
    return f"OZ{product.wb_nm_id}{product.wb_vendor_code}"


class ProductMatchIndex(NamedTuple):
    """Товары продавца, разложенные по каждому признаку сопоставления.

    Без раскладки сопоставление получается квадратичным: у крупного продавца
    двенадцать тысяч карточек, и перебирать их заново на каждую карточку Ozon —
    десятки миллионов сравнений за один импорт.
    """

    by_barcode: dict[str, list[uuid.UUID]]
    by_sku_code: dict[str, list[uuid.UUID]]
    by_oz_transfer: dict[str, list[uuid.UUID]]


def build_match_index(products: Sequence[ProductMatchKey]) -> ProductMatchIndex:
    index = ProductMatchIndex({}, {}, {})
    for product in products:
        if product.wb_barcode:
            index.by_barcode.setdefault(product.wb_barcode, []).append(product.product_id)
        index.by_sku_code.setdefault(product.sku_code, []).append(product.product_id)
        transfer = oz_transfer_offer_id(product)
        if transfer is not None:
            index.by_oz_transfer.setdefault(transfer, []).append(product.product_id)
    return index


def match_card_to_product(
    card: Mapping[str, Any],
    index: ProductMatchIndex,
    taken_product_ids: set[uuid.UUID],
) -> CardMatch:
    """Найти товар WMS, о котором эта карточка Ozon.

    Признаки идут по убыванию надёжности; первое однозначное совпадение
    выигрывает. Если признак дал больше одного кандидата — останавливаемся и не
    связываем: следующий, более слабый признак в такой ситуации не уточнит
    ответ, а заменит его догадкой.

    Занятость товара другой карточкой Ozon проверяется **после** подсчёта
    кандидатов, а не до. Иначе вышло бы вот что: у модели девятнадцать размеров,
    восемнадцать уже разобраны — и оставшийся один выглядел бы однозначным
    ответом, хотя признак по-прежнему не различает размеры.
    """
    offer_id = _text_or_none(card.get("offer_id"))
    by_signal: list[list[uuid.UUID]] = [
        [pid for code in card_matchable_barcodes(card) for pid in index.by_barcode.get(code, [])],
        index.by_sku_code.get(offer_id, []) if offer_id is not None else [],
        index.by_oz_transfer.get(offer_id, []) if offer_id is not None else [],
    ]
    for hits in by_signal:
        unique = list(dict.fromkeys(hits))
        if len(unique) > 1:
            return CardMatch(ambiguous=True)
        if len(unique) == 1:
            # Товар уже отдан другой карточке Ozon — значит эта карточка не о нём.
            return CardMatch() if unique[0] in taken_product_ids else CardMatch(unique[0])
    return CardMatch()


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


def card_product_name(card: Mapping[str, Any]) -> str:
    """Название заводимого товара. Пустым оно быть не может, поле обязательное."""
    for key in ("name", "offer_id", "sku", "id"):
        text = _text_or_none(card.get(key))
        if text is not None:
            return text[:255]
    return "Товар Ozon"


def card_product_sku_code(card: Mapping[str, Any]) -> str | None:
    """Артикул заводимого товара: артикул продавца, иначе идентификаторы Ozon.

    Карточку без единого идентификатора заводить нельзя: следующий проход
    импорта не сможет её узнать и заведёт второй такой же товар.
    """
    for key in ("offer_id", "sku", "id"):
        text = _text_or_none(card.get(key))
        if text is not None:
            return text[:128]
    return None


async def _candidate_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[ProductMatchKey]:
    """Товары продавца, годные в кандидаты на связку.

    Берём только поля, по которым сравниваем: у крупного продавца в каталоге
    двенадцать тысяч карточек, и тянуть их целиком ради четырёх колонок незачем.
    """
    rows = await session.execute(
        select(
            Product.id,
            Product.sku_code,
            Product.wb_barcode,
            Product.wb_nm_id,
            Product.wb_vendor_code,
        ).where(Product.tenant_id == tenant_id, Product.seller_id == seller_id)
    )
    return [
        ProductMatchKey(
            product_id=row.id,
            sku_code=row.sku_code,
            wb_barcode=row.wb_barcode,
            wb_nm_id=row.wb_nm_id,
            wb_vendor_code=row.wb_vendor_code,
        )
        for row in rows
    ]


async def _link_card_to_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    card: Mapping[str, Any],
    index: ProductMatchIndex,
    taken_product_ids: set[uuid.UUID],
    result: OzonProductImportResult,
) -> ProductMarketplaceLink | None:
    """Привязка для карточки, которой её ещё не завели.

    Сначала ищем среди своих товаров. Не нашли — заводим озоновский товар:
    именно за этим селлер вводит ключи. Нашли больше одного — не делаем ничего:
    склеить не тот размер дороже, чем оставить карточку оператору.

    Товар и привязка появляются вместе, одной точкой сохранения: товар без
    привязки следующий проход импорта не узнает и заведёт второй такой же.

    Штрихкод карточки в `wb_barcode` заведённого товара не пишем: озоновские
    коды живут на привязке (`external_barcodes`), и сканер уже умеет искать по
    ней. Хранить один код в двух местах — верный способ развести их со временем.
    """
    match = match_card_to_product(card, index, taken_product_ids)
    if match.ambiguous:
        return None
    sku_code = card_product_sku_code(card)
    if match.product_id is None and sku_code is None:
        return None
    link = ProductMarketplaceLink(
        tenant_id=tenant_id,
        seller_id=seller_id,
        marketplace="ozon",
    )
    created_product = False
    try:
        async with session.begin_nested():
            product_id = match.product_id
            if product_id is None:
                assert sku_code is not None
                product = Product(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    name=card_product_name(card),
                    sku_code=sku_code,
                )
                session.add(product)
                await session.flush()
                product_id = product.id
                created_product = True
            link.product_id = product_id
            session.add(link)
            await session.flush()
    except IntegrityError:
        return None
    if created_product:
        result.products_created += 1
    result.links_created += 1
    return link


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
    """Притянуть каталог Ozon: связать, чего нет — завести, всё — обогатить."""
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
    # Товар, уже привязанный к карточке Ozon, второй раз привязать нельзя:
    # у привязки уникальность по (продавец, товар, маркетплейс), да и один товар
    # склада не бывает двумя карточками сразу.
    taken_product_ids = {link.product_id for link in links}
    index = build_match_index(await _candidate_products(session, tenant_id, seller_id))

    for card in cards:
        link = next((item for item in links if _link_matches(item, card)), None)
        if link is None:
            link = await _link_card_to_product(
                session, tenant_id, seller_id, card, index, taken_product_ids, result
            )
            if link is None:
                offer_id = _text_or_none(card.get("offer_id"))
                if offer_id is not None:
                    result.unmatched_offer_ids.append(offer_id)
                continue
            links.append(link)
            taken_product_ids.add(link.product_id)
        else:
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
        image_url = card_primary_image_url(card)
        if image_url is not None:
            provider_data = dict(link.provider_data or {})
            if provider_data.get(OZON_PRIMARY_IMAGE_KEY) != image_url:
                provider_data[OZON_PRIMARY_IMAGE_KEY] = image_url
                # JSON-колонка не отслеживает правку по месту: присваиваем целиком.
                link.provider_data = provider_data
                result.images_applied += 1

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
