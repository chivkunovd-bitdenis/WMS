"""FBS KIZ manual binding lookup by WB order sticker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fbs_order import (
    CHECK_STATUS_NEW,
    FBS_ORDER_MARKING_FROZEN_STATUSES,
    FBS_ORDER_MARKING_WRITE_STATUSES,
    MARKING_KIND_SGTIN,
    META_STATUS_ASSIGNED,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    FbsOrder,
    FbsOrderMarking,
    current_order_marking,
)
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_supply import FbsSupply
from app.models.marking_code import (
    EVENT_APPLIED,
    EVENT_VOIDED,
    STATUS_APPLIED,
    STATUS_AVAILABLE,
    STATUS_VOID,
    MarkingCode,
)
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services import fbs_marking_service as marking_svc
from app.services import marking_code_service as marking_code_svc
from app.services.ozon_kiz_service import OzonKizError
from app.services.ozon_kiz_service import commit_ozon_kiz as commit_ozon
from app.services.wb_card_enrichment import first_photo_url_from_card
from app.services.wildberries_client import put_marketplace_order_meta
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import delete_marketplace_order_meta

_MISSING_PRODUCT_NAME = "Товар не сопоставлен"
_POOL_MARKING_SOURCE = "pool"
_OPERATOR_MARKING_SOURCE = "operator"
_EXTERNAL_FBS_MARKING_SOURCE = "external_fbs"
_VOID_REPLACED_REASON = "replaced_by_external_fbs_kiz"
_VOID_OPERATOR_CANCEL_REASON = "отмена оператором"
_REPLACEMENT_RESTORE_FAILED = "wb_replacement_restore_failed"
_GS = "\x1d"
_AIM_PREFIXES = ("]d2", "]d1", "]Q1", "]Q3", "]C1")
_CIS_MIN_LENGTH = 19
_CIS_MAX_LENGTH = 256
_GS_LITERAL_SUBSTITUTES = ("<GS>", "{GS}", "\\x1d")
_GS_SINGLE_CHAR_SUBSTITUTES = frozenset(("~", "|", "#"))
_GS1_FIXED_AI_VALUE_LENGTHS: dict[str, int] = {
    "00": 18,
    "01": 14,
    "02": 14,
    "11": 6,
    "12": 6,
    "13": 6,
    "15": 6,
    "16": 6,
    "17": 6,
    "20": 2,
    **{f"310{decimal_places}": 6 for decimal_places in range(10)},
}
_GS1_VARIABLE_AI_MAX_LENGTHS: dict[str, int] = {
    "10": 20,
    "21": 20,
    "22": 29,
    "30": 8,
    "37": 8,
    "240": 30,
    "241": 30,
    "242": 6,
    "250": 30,
    "251": 30,
    "400": 30,
    "401": 30,
    "403": 30,
    "420": 20,
    "421": 15,
    "422": 3,
    "90": 30,
    "91": 90,
    "92": 90,
    "93": 90,
    "94": 90,
    "95": 90,
    "96": 90,
    "97": 90,
    "98": 90,
    "99": 90,
}
_GS1_AI_CODES = tuple(
    sorted(
        set(_GS1_FIXED_AI_VALUE_LENGTHS) | set(_GS1_VARIABLE_AI_MAX_LENGTHS),
        key=len,
        reverse=True,
    )
)
_GS1_INTERNAL_VARIABLE_AIS = frozenset(str(number) for number in range(91, 100))
_KEYBOARD_LAYOUT_PAIRS = (
    (
        "\u0451\u0439\u0446\u0443\u043a\u0435\u043d\u0433\u0448\u0449"
        "\u0437\u0445\u044a\u0444\u044b\u0432\u0430\u043f\u0440\u043e"
        "\u043b\u0434\u0436\u044d\u044f\u0447\u0441\u043c\u0438\u0442"
        "\u044c\u0431\u044e.",
        "`qwertyuiop[]asdfghjkl;'zxcvbnm,./",
    ),
    (
        "\u0401\u0419\u0426\u0423\u041a\u0415\u041d\u0413\u0428\u0429"
        "\u0417\u0425\u042a\u0424\u042b\u0412\u0410\u041f\u0420\u041e"
        "\u041b\u0414\u0416\u042d\u042f\u0427\u0421\u041c\u0418\u0422"
        "\u042c\u0411\u042e,",
        '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?',
    ),
    ('"\u2116;:?/', "@#$^&|"),
)
_KEYBOARD_LAYOUT_MAP = {
    ru_char: qwerty_char
    for ru_chars, qwerty_chars in _KEYBOARD_LAYOUT_PAIRS
    for ru_char, qwerty_char in zip(ru_chars, qwerty_chars, strict=True)
    if ru_char != qwerty_char
}
_KEYBOARD_LAYOUT_TRANSLATION = str.maketrans(_KEYBOARD_LAYOUT_MAP)
_KEYBOARD_LAYOUT_MARKERS = frozenset(
    char
    for char in _KEYBOARD_LAYOUT_MAP
    if "\u0400" <= char <= "\u04ff" or char == "\u2116"
)


class FbsKizError(Exception):
    def __init__(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
        message: str | None = None,
        persist_failure_state: bool = False,
    ) -> None:
        self.code = code
        self.context = context or {}
        self.message = message
        self.persist_failure_state = persist_failure_state
        super().__init__(code)


@dataclass(frozen=True)
class FbsKizProduct:
    name: str
    image_url: str | None
    barcode: str | None
    seller_article: str | None


@dataclass(frozen=True)
class FbsKizCurrentMarking:
    masked: str
    meta_status: str
    from_pool: bool


@dataclass(frozen=True)
class FbsKizLookup:
    order_id: uuid.UUID
    wb_order_id: int
    product: FbsKizProduct
    current_kiz: FbsKizCurrentMarking | None
    needs_confirmation: bool
    can_bind: bool
    block_reason: str | None


@dataclass(frozen=True)
class FbsKizValidateResult:
    ok: bool
    hints: list[str]


@dataclass(frozen=True)
class FbsKizCommitPair:
    order_id: uuid.UUID
    value: str
    confirmed: bool


@dataclass(frozen=True)
class FbsKizCommitRow:
    order_id: uuid.UUID
    status: str
    code: str
    message: str


@dataclass(frozen=True)
class _ValidatedKizPair:
    order: FbsOrder
    value: str
    hints: list[str]


@dataclass(frozen=True)
class _PackagingLineRef:
    line: PackagingTaskLine
    document_number: str | None


def normalize_scanned_sticker(raw: str) -> str:
    """Normalize scanner noise for WB sticker matching."""
    stripped = raw.strip()
    return "".join(ch for ch in stripped if ch != "\ufeff" and not ch.isspace())


def sticker_scan_candidates(raw: str) -> list[str]:
    """Варианты прочтения стикера: как пришёл и с развёрнутой раскладкой.

    Сканер работает как клавиатура: при активной русской раскладке он «печатает»
    кириллицу вместо латиницы, и код стикера «*DVNdzDVg» приезжает как «*ВМТвяВМп».
    Для Честного знака раскладка разворачивалась давно, для стикера — нет, и скан
    не находил заказ (бой 27.08.2026, поставка WB-GI-270121264).
    """
    base = normalize_scanned_sticker(raw)
    if not base:
        return []
    candidates = [base]
    if _has_keyboard_layout_noise(base):
        repaired = normalize_scanned_sticker(base.translate(_KEYBOARD_LAYOUT_TRANSLATION))
        if repaired and repaired != base:
            candidates.append(repaired)
    return candidates


def _match_gs1_ai(value: str, position: int) -> str | None:
    for ai in _GS1_AI_CODES:
        if value.startswith(ai, position):
            return ai
    return None


def _match_gs_substitute(value: str, position: int) -> str | None:
    for token in _GS_LITERAL_SUBSTITUTES:
        if value.startswith(token, position):
            return token
    char = value[position]
    if char in _GS_SINGLE_CHAR_SUBSTITUTES:
        return char
    return None


def _is_expected_next_ai(current_ai: str, next_ai: str) -> bool:
    if (
        current_ai in _GS1_INTERNAL_VARIABLE_AIS
        and next_ai in _GS1_INTERNAL_VARIABLE_AIS
    ):
        return int(next_ai) > int(current_ai)
    return next_ai != current_ai


def _restore_gs_substitutes(value: str) -> tuple[str, bool]:
    parts: list[str] = []
    position = 0
    changed = False

    while position < len(value):
        ai = _match_gs1_ai(value, position)
        if ai is None:
            parts.append(value[position])
            position += 1
            continue

        parts.append(ai)
        position += len(ai)
        fixed_value_length = _GS1_FIXED_AI_VALUE_LENGTHS.get(ai)
        if fixed_value_length is not None:
            value_end = min(len(value), position + fixed_value_length)
            parts.append(value[position:value_end])
            position = value_end
            continue

        field_start = position
        while position < len(value):
            if value[position] == _GS:
                parts.append(value[field_start : position + 1])
                position += 1
                break

            token = _match_gs_substitute(value, position)
            if token is not None:
                next_position = position + len(token)
                next_ai = _match_gs1_ai(value, next_position)
                if (
                    position > field_start
                    and next_ai is not None
                    and _is_expected_next_ai(ai, next_ai)
                ):
                    parts.append(value[field_start:position])
                    parts.append(_GS)
                    position = next_position
                    changed = True
                    break

            position += 1
        else:
            parts.append(value[field_start:])
            position = len(value)

    return "".join(parts), changed


def is_probably_cis(value: str) -> bool:
    return (
        _CIS_MIN_LENGTH <= len(value) <= _CIS_MAX_LENGTH
        and value.startswith("01")
        and len(value) >= 18
        and value[2:16].isdigit()
        and value[16:18] == "21"
    )


# --- I3: GS-разделители, вырезанные целиком браузерным полем ввода ---------
#
# _restore_gs_substitutes (выше) лечит другой случай: когда сканер настроен
# передавать разделитель ВИДИМЫМ символом-заменителем (F8/Alt+0029 в режимах
# сканера превращаются в "~", "<GS>" и т.п.) — тогда в строке остаётся след,
# по которому видно, где резать. Дефект I3 — хуже: HTML-поле ввода браузера
# самих 0x1D байтов не пропускает вообще, без всякой замены, и код склеивается
# без единого намёка на границу. Единственный способ понять, где резать —
# знать структуру КИЗ и разобрать её с конца.
#
# Структура полного КИЗ Честного знака (см. tasks/fbs-marketplace-orders/
# wb-docs/04-labeling/kiz-common-errors.md и verify-product-identifiers.md):
#   01<GTIN, 14 цифр>21<серийный номер, переменная длина>
#   91<проверочный код, ровно 4 символа>
#   92<криптоподпись: 44 символа для одежды, 88 — для обуви>
# Разделитель GS1 нужен только после переменных полей — перед 91 и перед 92,
# перед 91 разделитель не факультативен, WB кладёт его туда даже при том, что
# длина значения 91 сама по себе фиксирована (так делает реальный сканер,
# поэтому его и восстанавливаем на этом же месте).
#
# Искать подстроки "91"/"92" по всей строке нельзя — они регулярно попадают в
# серийный номер (пример есть в тестах: серийник "A91XB92YC7z" — с виду начало
# блока 91, а на деле обычные символы серии). Поэтому разбор идёт не поиском,
# а фиксированными смещениями ОТ КОНЦА СТРОКИ: пробуем оба известных варианта
# длины подписи (44 и 88), и засчитываем только тот, для которого на нужном
# месте от конца буквально стоят маркеры "91" и "92" — с учётом того, что
# длины 44 и 88 отличаются на 44 символа, а серийный номер по стандарту GS1 не
# длиннее 20 символов, оба варианта одновременно совпасть не могут: серийники,
# которые они бы предполагали, отличались бы на те же 44 символа, а в окно
# длиной 20 такая пара не поместится. Значит, если совпал ровно один вариант —
# структура однозначна.
_CIS_PREFIX_LENGTH = 18  # "01" + 14-значный GTIN + "21"
_CIS_SERIAL_MAX_LENGTH = _GS1_VARIABLE_AI_MAX_LENGTHS["21"]
_GS1_AI91_VALUE_LENGTH = 4
_CIS_SIGNATURE_LENGTHS = (44, 88)  # одежда, обувь
_GS_STRUCTURE_HINT = "gs_structure_restored"
_GS_UNRESTORABLE_HINT = "gs_unrestorable"


def _cis_prefix_ok(value: str) -> bool:
    return (
        len(value) >= _CIS_PREFIX_LENGTH
        and value.startswith("01")
        and value[2:16].isdigit()
        and value[16:18] == "21"
    )


def _restore_missing_gs_by_structure(value: str) -> tuple[str, bool, bool]:
    """Восстанавливает GS-разделители, вырезанные целиком, по структуре КИЗ.

    Возвращает (значение, восстановлено, неразбираемо). "Неразбираемо" — это
    не «ничего не нашли», а «похоже на длинный КИЗ без разделителей, но ни
    длина одежды, ни длина обуви не сошлись» — именно этот случай задача
    требует не пропускать молча дальше в WB.
    """
    if not _cis_prefix_ok(value):
        return value, False, False

    tail = value[_CIS_PREFIX_LENGTH:]

    # Раньше выход был по первому же найденному разделителю. Но сканер теряет
    # их по одному: код, у которого уцелел разделитель перед 91 и пропал перед
    # 92, не чинился и не браковался — молча уходил в WB на верную ошибку
    # sgtinNoGS. Поэтому структуру считаем по очищенному хвосту, а уцелевшие
    # разделители расставляем заново на положенные места.
    tail = tail.replace(_GS, "")
    had_separators = _GS in value[_CIS_PREFIX_LENGTH:]

    if len(tail) <= _CIS_SERIAL_MAX_LENGTH:
        # Похоже на короткий КИЗ без криптохвоста — валидный формат самого
        # WB (см. verify-product-identifiers.md, раздел «Короткий и длинный
        # КИЗ»). Разделитель перед последним полем GS1 не ставит никто —
        # он нужен только чтобы отделить одно переменное поле от следующего.
        return value, False, False

    candidates: list[tuple[str, str, str]] = []
    for signature_length in _CIS_SIGNATURE_LENGTHS:
        suffix_length = 2 + _GS1_AI91_VALUE_LENGTH + 2 + signature_length
        if len(tail) <= suffix_length:
            continue
        serial = tail[: len(tail) - suffix_length]
        block = tail[len(tail) - suffix_length :]
        if not (1 <= len(serial) <= _CIS_SERIAL_MAX_LENGTH):
            continue
        if block[0:2] != "91" or block[6:8] != "92":
            continue
        candidates.append((serial, block[2:6], block[8:]))

    if len(candidates) != 1:
        # Ноль совпадений — длина хвоста не подошла ни под один известный
        # формат подписи. Два совпадения математически не должны случаться
        # (см. комментарий выше), но если всё же случились — тоже не гадаем.
        # Код с уцелевшими разделителями оставляем как есть: структуру мы не
        # опознали, но и оснований звать её потерянной нет.
        return value, False, not had_separators

    serial, verification, signature = candidates[0]
    restored = f"{value[:_CIS_PREFIX_LENGTH]}{serial}{_GS}91{verification}{_GS}92{signature}"
    return restored, restored != value, False


def _tail_parses_with_own_separators(tail: str) -> bool:
    """Хвост уже разложен по полям GS1 своими разделителями.

    Канон обувного и одёжного КИЗа: серийник, затем блок 91 из четырёх
    символов, затем блок 92 с подписью известной длины. Если всё это уже
    отделено разделителями и сходится по длинам — структура опознана, и
    достраивать нечего.
    """

    parts = tail.split(_GS)
    if len(parts) < 2:
        return False
    serial, *blocks = parts
    if not 1 <= len(serial) <= _CIS_SERIAL_MAX_LENGTH:
        return False
    seen: set[str] = set()
    for block in blocks:
        tag = block[:2]
        if tag in seen:
            return False
        seen.add(tag)
        if tag == "91":
            if len(block) != 2 + _GS1_AI91_VALUE_LENGTH:
                return False
        elif tag == "92":
            if len(block) - 2 not in _CIS_SIGNATURE_LENGTHS:
                return False
        elif tag == "93":
            # Криптохвост под тегом 93: его длина зависит от категории товара
            # и нам не известна. Раз поле отделено разделителем — структуру
            # опознали до нас, и достраивать здесь нечего.
            if len(block) <= 2:
                return False
        else:
            return False
    # Криптохвост обязателен: без него это короткий КИЗ, его разбирает
    # отдельная ветка выше.
    return bool(seen & {"92", "93"})


def alternative_cis_reading(raw: str) -> str | None:
    """Второе законное прочтение кода, если достраивание было неоднозначным.

    ⛔ Развести два случая чистой функцией НЕЛЬЗЯ, и это доказуемо:

        21aXq7Tz9Km91K7pQ<GS>92<44>   ← сканер потерял разделитель, чинить надо
        21AB91ZZQQ<GS>92<44>          ← серийник сам кончается на 91+4, чинить нельзя

    Обе строки устроены одинаково: серийник, оканчивающийся на «91» плюс
    четыре символа, затем разделитель и блок 92. Никакого признака, по
    которому одну можно отличить от другой, в самом коде нет.

    Поэтому разбор оставляем как есть — он чинит частый случай, — а спор
    решаем данными: наш пул знает, какие коды мы выпускали. Функция отдаёт
    прочтение «оставить как пришло», чтобы вызывающий мог сверить оба
    варианта с пулом и выбрать существующий.

    Отдаёт None, когда спорить не о чем: достраивание ничего не поменяло или
    исходный код своими разделителями не разбирался.
    """

    value = raw.rstrip(" \t\r\n\v\f")
    value, _ = _strip_aim_prefix(value)
    value, _ = _restore_gs_substitutes(value)
    if not _cis_prefix_ok(value):
        return None
    if not _tail_parses_with_own_separators(value[_CIS_PREFIX_LENGTH:]):
        return None
    restored, changed, _ = _restore_missing_gs_by_structure(value)
    if not changed or restored == value:
        return None
    return value


def _has_keyboard_layout_noise(value: str) -> bool:
    return any(char in _KEYBOARD_LAYOUT_MARKERS for char in value)


def _strip_aim_prefix(value: str) -> tuple[str, bool]:
    for prefix in _AIM_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix) :], True
    return value, False


def normalize_scanned_cis(raw: str) -> tuple[str, list[str]]:
    # Пробельный хвост, который дописывает сканер: кроме пробела и перевода
    # строки бывает Tab, и лишний символ ломал разбор структуры кода. Список
    # символов задан явно: голый rstrip() в Python срезает и 0x1D — а это сам
    # разделитель GS1, и код, заканчивающийся на него, потерял бы разделитель.
    value = raw.rstrip(" \t\r\n\v\f")
    hints: list[str] = []

    value, aim_prefix_removed = _strip_aim_prefix(value)
    if aim_prefix_removed:
        hints.append("aim_prefix")

    value, gs_changed = _restore_gs_substitutes(value)
    if gs_changed:
        hints.append("gs_substitute")

    if _has_keyboard_layout_noise(value):
        repaired = value.translate(_KEYBOARD_LAYOUT_TRANSLATION)
        repaired, aim_prefix_removed_after_layout = _strip_aim_prefix(repaired)
        repaired, gs_changed_after_layout = _restore_gs_substitutes(repaired)
    else:
        repaired = value
        aim_prefix_removed_after_layout = False
        gs_changed_after_layout = False
    if repaired != value and is_probably_cis(repaired):
        value = repaired
        if aim_prefix_removed_after_layout and "aim_prefix" not in hints:
            hints.append("aim_prefix")
        hints.append("keyboard_layout")
        if gs_changed_after_layout and "gs_substitute" not in hints:
            hints.append("gs_substitute")

    # Последний шаг: разделитель вырезан целиком, без замены (I3). Идёт после
    # всех остальных репаров, на максимально уже вычищенном значении — если
    # раскладка или AIM-префикс мешали, они уже сняты выше.
    value, gs_structure_restored, gs_unrestorable = _restore_missing_gs_by_structure(value)
    if gs_structure_restored:
        hints.append(_GS_STRUCTURE_HINT)
    elif gs_unrestorable:
        hints.append(_GS_UNRESTORABLE_HINT)

    hint_order = {
        "aim_prefix": 0,
        "gs_substitute": 1,
        "keyboard_layout": 2,
        _GS_STRUCTURE_HINT: 3,
        _GS_UNRESTORABLE_HINT: 4,
    }
    hints.sort(key=hint_order.__getitem__)
    return value, hints


def _debug_visible(value: str) -> str:
    return value.replace(_GS, "<GS>")


def scan_debug(raw: str) -> dict[str, int | str]:
    return {
        "length": len(raw),
        "first8": _debug_visible(raw[:8]),
        "last8": _debug_visible(raw[-8:]),
    }


def _normalized_optional(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    normalized = normalize_scanned_sticker(raw)
    return normalized or None


def _find_order_by_sticker(orders: list[FbsOrder], sticker: str) -> FbsOrder | None:
    # Сначала — технический код стикера. Именно он закодирован во все QR и штрихкоды
    # печатной этикетки WB, и именно его выдаёт сканер (вид «*DUIkWJJF»). Проверено
    # 20.08.2026 декодированием реальной этикетки: раньше поиск шёл только по
    # человеческому номеру partA/partB, поэтому скан не находил заказ никогда.
    for order in orders:
        if _normalized_optional(order.sticker_barcode) == sticker:
            return order
    # Человеческий номер («5694425 3074») — если оператор вводит его руками с этикетки.
    for order in orders:
        if _normalized_optional(order.sticker_code) == sticker:
            return order
    # Штрихкод товара — запасной путь, когда стикер заказа ещё не получен.
    for order in orders:
        if _normalized_optional(order.wb_barcode) == sticker:
            return order
    return None


def _current_sgtin_marking(order: FbsOrder) -> FbsOrderMarking | None:
    return current_order_marking(list(order.markings), MARKING_KIND_SGTIN)


def _mask_kiz(value: str) -> str:
    return f"…{value[-6:]}"


async def _image_url_for_order(session: AsyncSession, order: FbsOrder) -> str | None:
    if order.wb_nm_id is None:
        return None
    stmt = (
        select(SellerWildberriesImportedCard.raw_json)
        .where(
            SellerWildberriesImportedCard.seller_id == order.seller_id,
            SellerWildberriesImportedCard.nm_id == int(order.wb_nm_id),
        )
        .limit(1)
    )
    raw = (await session.execute(stmt)).scalar_one_or_none()
    if isinstance(raw, dict):
        return first_photo_url_from_card(raw)
    return None


def _product_payload(order: FbsOrder, image_url: str | None) -> FbsKizProduct:
    product: Product | None = order.product
    # Тот же порядок, что и в списке заказов: карточка товара главнее задания WB —
    # иначе оператор видит внутренний код WB вместо штрихкода с коробки.
    barcode = (product.wb_barcode if product is not None else None) or order.wb_barcode
    seller_article = product.sku_code if product is not None else order.wb_article
    name = (
        product.name
        if product is not None
        else order.wb_article or _MISSING_PRODUCT_NAME
    )
    return FbsKizProduct(
        name=name,
        image_url=image_url,
        barcode=barcode,
        seller_article=seller_article,
    )


async def lookup_order_by_sticker(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    sticker: str,
) -> FbsKizLookup:
    candidates = sticker_scan_candidates(sticker)
    if not candidates:
        raise FbsKizError("sticker_not_found")

    stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.supply_id == supply_id,
        )
        .options(
            selectinload(FbsOrder.product),
            selectinload(FbsOrder.markings),
        )
        .order_by(FbsOrder.created_at, FbsOrder.id)
    )
    orders = list((await session.execute(stmt)).scalars().all())
    order = next(
        (
            found
            for candidate in candidates
            if (found := _find_order_by_sticker(orders, candidate)) is not None
        ),
        None,
    )
    if order is None:
        raise FbsKizError("sticker_not_found")

    if (
        order.status in FBS_ORDER_MARKING_FROZEN_STATUSES
        or order.status not in FBS_ORDER_MARKING_WRITE_STATUSES
    ):
        raise FbsKizError("order_frozen", context={"order_id": str(order.id)})

    current = _current_sgtin_marking(order)
    current_out = (
        FbsKizCurrentMarking(
            masked=_mask_kiz(current.value),
            meta_status=current.meta_status,
            from_pool=current.source == _POOL_MARKING_SOURCE,
        )
        if current is not None
        else None
    )
    image_url = await _image_url_for_order(session, order)
    return FbsKizLookup(
        order_id=order.id,
        wb_order_id=int(order.wb_order_id),
        product=_product_payload(order, image_url),
        current_kiz=current_out,
        needs_confirmation=current_out is not None,
        can_bind=True,
        block_reason=None,
    )


def _error_message(exc: FbsKizError) -> str:
    if exc.message:
        return exc.message
    if exc.code == "meta_validation_fail":
        reasons = exc.context.get("reasons")
        if isinstance(reasons, list) and reasons:
            first = reasons[0]
            if isinstance(first, dict):
                reason = first.get("reason")
                if isinstance(reason, str) and reason:
                    return reason
    return exc.code


def _marking_error_to_kiz(exc: marking_svc.FbsMarkingError) -> FbsKizError:
    return FbsKizError(exc.code, context=exc.context)


async def _get_order_for_kiz(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> FbsOrder:
    stmt = select(FbsOrder).where(
        FbsOrder.id == order_id,
        FbsOrder.tenant_id == tenant_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    order = (await session.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise FbsKizError("order_not_found")
    if (
        order.status in FBS_ORDER_MARKING_FROZEN_STATUSES
        or order.status not in FBS_ORDER_MARKING_WRITE_STATUSES
    ):
        raise FbsKizError("order_frozen", context={"order_id": str(order.id)})
    return order


def _plain(value: str) -> str:
    """Код без разделителей — то, чем один физический КИЗ равен другому.

    Разделители GS — это разметка, а не данные: один и тот же код склад мог
    сохранить и с ними, и без. До этой правки сверка шла по сырой строке, и
    представления не находили друг друга. На бою это живое: из 42 привязанных
    к заказам кодов 16 при пересканировании давали другую строку, в пуле —
    51 из 2886. Пикнув такой код в другой заказ, оператор не получал отказа
    «уже привязан», и один физический КИЗ уезжал в WB дважды.
    """

    return value.replace(_GS, "")


def _same_cis(column: Any, value: str) -> Any:
    """Условие «это тот же физический код», независимо от разделителей."""

    return func.replace(column, _GS, "") == _plain(value)


async def _ensure_kiz_not_bound_to_other_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    value: str,
) -> None:
    stmt = (
        select(FbsOrderMarking, FbsOrder)
        .join(FbsOrder, FbsOrder.id == FbsOrderMarking.order_id)
        .where(
            FbsOrderMarking.tenant_id == tenant_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
            _same_cis(FbsOrderMarking.value, value),
            FbsOrderMarking.meta_status != META_STATUS_REJECTED,
            FbsOrderMarking.order_id != order_id,
        )
        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
        .limit(1)
    )
    duplicate = (await session.execute(stmt)).first()
    if duplicate is None:
        return
    marking = duplicate[0]
    duplicate_order = duplicate[1]
    raise FbsKizError(
        "duplicate_kiz",
        context={
            "wb_order_id": int(duplicate_order.wb_order_id),
            "created_at": marking.created_at.isoformat(),
        },
    )


async def _get_marking_code_by_cis(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    value: str,
    *,
    for_update: bool = False,
) -> MarkingCode | None:
    # Внутри арендатора двух представлений одного кода нет: уникальный индекс
    # стоит на (tenant_id, cis_code), и проверка боевой базы дублей по
    # каноническому виду внутри арендатора не нашла ни одного.
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        _same_cis(MarkingCode.cis_code, value),
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _ensure_kiz_not_occupied_in_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    value: str,
) -> None:
    code = await _get_marking_code_by_cis(session, tenant_id, value)
    if code is None:
        return
    if code.seller_id != order.seller_id:
        raise FbsKizError("cross_seller_code")
    if (
        order.product_id is not None
        and code.product_id is not None
        and code.product_id != order.product_id
    ):
        raise FbsKizError("code_product_mismatch")
    if code.status != STATUS_AVAILABLE:
        raise FbsKizError(
            "duplicate_kiz",
            context={"marking_code_id": str(code.id), "status": code.status},
        )


async def _validate_kiz_pair(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    raw_value: str,
    *,
    for_update: bool = False,
    check_marking_code_occupancy: bool = True,
) -> _ValidatedKizPair:
    value, hints = normalize_scanned_cis(raw_value)
    if _GS_UNRESTORABLE_HINT in hints:
        # I3: похоже на длинный КИЗ без разделителей (склеенный сканером,
        # см. _restore_missing_gs_by_structure), но ни длина одежды, ни длина
        # обуви не сошлись — угадывать нельзя. Код не уходит дальше, оператору
        # называем причину словами, а не молча шлём WB на верную ошибку
        # sgtinNoGS.
        raise FbsKizError(
            "gs_separator_lost",
            context={"debug": scan_debug(raw_value)},
            message=(
                "Разделители кода потеряны при вводе, а структуру не удалось "
                "восстановить — отсканируйте Честный знак заново целиком"
            ),
        )
    if not is_probably_cis(value):
        raise FbsKizError(
            "not_a_kiz",
            context={"debug": scan_debug(raw_value)},
            message="not_a_kiz",
        )

    # Спор двух законных прочтений решаем нашим же пулом: если код с
    # достроенными разделителями нам неизвестен, а «как пришёл» — известен,
    # значит достраивание распилило чужой серийник, и брать надо исходный.
    # Без этого в WB уходил бы другой ЛОГИЧЕСКИЙ код при тех же байтах, и
    # оператор не увидел бы ничего: подмена границ полей молчалива.
    alternative = alternative_cis_reading(raw_value)
    if (
        alternative is not None
        and alternative != value
        and await _get_marking_code_by_cis(session, tenant_id, value) is None
        and await _get_marking_code_by_cis(session, tenant_id, alternative) is not None
    ):
        value = alternative

    order = await _get_order_for_kiz(
        session,
        tenant_id,
        order_id,
        for_update=for_update,
    )
    await _ensure_kiz_not_bound_to_other_order(session, tenant_id, order.id, value)
    if check_marking_code_occupancy:
        await _ensure_kiz_not_occupied_in_pool(session, tenant_id, order, value)
    return _ValidatedKizPair(order=order, value=value, hints=hints)


async def validate_kiz_pair(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    raw_value: str,
) -> FbsKizValidateResult:
    validated = await _validate_kiz_pair(session, tenant_id, order_id, raw_value)
    return FbsKizValidateResult(ok=True, hints=validated.hints)


async def _current_sgtin_marking_for_update(
    session: AsyncSession,
    order_id: uuid.UUID,
) -> FbsOrderMarking | None:
    stmt = (
        select(FbsOrderMarking)
        .where(
            FbsOrderMarking.order_id == order_id,
            FbsOrderMarking.kind == MARKING_KIND_SGTIN,
            FbsOrderMarking.meta_status != META_STATUS_REJECTED,
        )
        .options(selectinload(FbsOrderMarking.marking_code))
        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
        .limit(1)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _packaging_line_for_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
) -> _PackagingLineRef:
    fulfilled_stmt = (
        select(PackagingTaskLine, PackagingTask.document_number)
        .join(
            FbsPackagingFulfillment,
            FbsPackagingFulfillment.packaging_task_line_id == PackagingTaskLine.id,
        )
        .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
        .where(
            FbsPackagingFulfillment.tenant_id == tenant_id,
            FbsPackagingFulfillment.fbs_order_id == order.id,
            FbsPackagingFulfillment.undone_at.is_(None),
        )
        .order_by(FbsPackagingFulfillment.fulfilled_at.desc())
        .limit(1)
        .with_for_update()
    )
    fulfilled = (await session.execute(fulfilled_stmt)).first()
    if fulfilled is not None:
        return _PackagingLineRef(line=fulfilled[0], document_number=fulfilled[1])

    if order.supply_id is None or order.product_id is None:
        raise FbsKizError("packaging_line_not_found")

    supply_stmt = (
        select(PackagingTaskLine, PackagingTask.document_number)
        .join(PackagingTask, PackagingTask.id == PackagingTaskLine.task_id)
        .join(FbsSupply, FbsSupply.packaging_task_id == PackagingTask.id)
        .where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.id == order.supply_id,
            PackagingTaskLine.product_id == order.product_id,
        )
        .order_by(PackagingTaskLine.id)
        .limit(1)
        .with_for_update()
    )
    line = (await session.execute(supply_stmt)).first()
    if line is None:
        raise FbsKizError("packaging_line_not_found")
    return _PackagingLineRef(line=line[0], document_number=line[1])


async def _create_or_apply_external_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    value: str,
    line: PackagingTaskLine,
) -> MarkingCode:
    now = datetime.now(tz=UTC)
    code = MarkingCode(
        tenant_id=tenant_id,
        seller_id=order.seller_id,
        product_id=order.product_id,
        cis_code=value,
        source=_EXTERNAL_FBS_MARKING_SOURCE,
        status=STATUS_APPLIED,
        applied_at=now,
        packaging_task_line_id=line.id,
        pool_id=None,
        import_batch_id=None,
        label_artifact_pdf=None,
    )
    session.add(code)
    await session.flush()
    return code


async def _prepare_code_for_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    value: str,
    line: PackagingTaskLine,
) -> tuple[MarkingCode, bool]:
    try:
        pool_code = await marking_svc._claim_pool_code_if_present(
            session,
            tenant_id=tenant_id,
            order=order,
            cis_raw=value,
        )
    except marking_svc.FbsMarkingError as exc:
        raise _marking_error_to_kiz(exc) from exc
    if pool_code is not None:
        pool_code.packaging_task_line_id = line.id
        await session.flush()
        return pool_code, True
    return (
        await _create_or_apply_external_code(
            session,
            tenant_id,
            order,
            value,
            line,
        ),
        False,
    )


async def void_existing_sgtin_marking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    marking: FbsOrderMarking,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
    api_token: str | None = None,
    reason: str = _VOID_REPLACED_REASON,
) -> None:
    token = api_token or await marking_svc.require_marketplace_token(
        session, tenant_id, order.seller_id
    )
    await _delete_sgtin_from_wb(order, http_client, token)
    await _void_existing_sgtin_marking_locally(
        session,
        marking,
        actor_user_id=actor_user_id,
        reason=reason,
    )


async def _delete_sgtin_from_wb(
    order: FbsOrder,
    http_client: httpx.AsyncClient,
    api_token: str,
) -> None:
    try:
        await delete_marketplace_order_meta(
            http_client,
            api_token=api_token,
            order_id=int(order.wb_order_id),
            key=MARKING_KIND_SGTIN,
        )
    except WildberriesClientError as exc:
        raise FbsKizError(marking_svc._wb_error_code(exc)) from exc


async def _void_existing_sgtin_marking_locally(
    session: AsyncSession,
    marking: FbsOrderMarking,
    *,
    actor_user_id: uuid.UUID | None,
    reason: str,
) -> None:
    code = marking.marking_code
    if code is None and marking.marking_code_id is not None:
        code = await session.get(MarkingCode, marking.marking_code_id)
    if code is not None:
        line: PackagingTaskLine | None = None
        if code.packaging_task_line_id is not None:
            line = await session.get(PackagingTaskLine, code.packaging_task_line_id)
        code.status = STATUS_VOID
        await marking_code_svc.record_event(
            session,
            code=code,
            event_type=EVENT_VOIDED,
            actor=actor_user_id,
            packaging_task=line,
            reason=reason,
            source_process=marking_code_svc.MARKING_SOURCE_PACKING_FBS_PRINT,
        )
        if code.source == _EXTERNAL_FBS_MARKING_SOURCE and line is not None:
            line.qty_marking_external = max(0, int(line.qty_marking_external) - 1)

    await session.delete(marking)
    await session.flush()


async def _restore_previous_wb_marking(
    order: FbsOrder,
    marking: FbsOrderMarking,
    http_client: httpx.AsyncClient,
    api_token: str,
) -> None:
    await _delete_sgtin_from_wb(order, http_client, api_token)
    try:
        await put_marketplace_order_meta(
            http_client,
            api_token=api_token,
            order_id=int(order.wb_order_id),
            kind=MARKING_KIND_SGTIN,
            value=marking.value,
        )
    except WildberriesClientError as exc:
        raise FbsKizError(marking_svc._wb_error_code(exc)) from exc


async def _persist_failed_replacement_state(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    *,
    new_error_code: str,
    restore_error_code: str,
) -> None:
    await session.rollback()
    order = await _get_order_for_kiz(session, tenant_id, order_id, for_update=True)
    current = await _current_sgtin_marking_for_update(session, order.id)
    if current is None:
        raise FbsKizError("kiz_not_found", context={"order_id": str(order.id)})
    reason = (
        "replacement_failed_and_restore_failed: "
        f"new={new_error_code}; restore={restore_error_code}"
    )
    current.meta_status = META_STATUS_REPLACEMENT_REQUIRED
    current.reason = reason
    order.meta_details_json = {
        MARKING_KIND_SGTIN: {
            "status": META_STATUS_REPLACEMENT_REQUIRED,
            "value": current.value,
            "reason": reason,
        }
    }
    order.metadata_delivery_allowed = False
    order.metadata_last_checked_at = datetime.now(tz=UTC)
    await session.flush()


async def cancel_order_kiz(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> None:
    await session.rollback()
    try:
        order = await _get_order_for_kiz(session, tenant_id, order_id, for_update=True)
        current = await _current_sgtin_marking_for_update(session, order.id)
        if current is None:
            raise FbsKizError("kiz_not_found", context={"order_id": str(order.id)})
        await void_existing_sgtin_marking(
            session,
            tenant_id,
            order,
            current,
            http_client,
            actor_user_id=actor_user_id,
            reason=_VOID_OPERATOR_CANCEL_REASON,
        )
        await session.commit()
    except FbsKizError:
        await session.rollback()
        raise


async def _commit_one_kiz_pair(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    pair: FbsKizCommitPair,
    http_client: httpx.AsyncClient,
) -> None:
    validated = await _validate_kiz_pair(
        session,
        tenant_id,
        pair.order_id,
        pair.value,
        for_update=True,
        check_marking_code_occupancy=False,
    )
    order = validated.order
    if order.marketplace == "ozon":
        try:
            await commit_ozon(
                session, order, validated.value, pair.confirmed, actor_user_id, http_client
            )
        except OzonKizError as exc:
            raise FbsKizError(exc.code, message=exc.message) from exc
        return
    current = await _current_sgtin_marking_for_update(session, order.id)
    if (
        current is not None
        and current.value == validated.value
        and current.meta_status != META_STATUS_REJECTED
    ):
        return
    if current is not None and not pair.confirmed:
        raise FbsKizError("needs_confirmation", context={"current_kiz": _mask_kiz(current.value)})
    line_ref = await _packaging_line_for_order(session, tenant_id, order)
    code, from_pool = await _prepare_code_for_binding(
        session,
        tenant_id,
        order,
        validated.value,
        line_ref.line,
    )
    token = await marking_svc.require_marketplace_token(session, tenant_id, order.seller_id)
    await marking_code_svc.record_event(
        session,
        code=code,
        event_type=EVENT_APPLIED,
        actor=actor_user_id,
        document_number=line_ref.document_number,
        packaging_task=line_ref.line,
        source_process=marking_code_svc.MARKING_SOURCE_PACKING_FBS_PRINT,
    )
    marking = FbsOrderMarking(
        order_id=order.id,
        tenant_id=tenant_id,
        kind=MARKING_KIND_SGTIN,
        value=validated.value,
        source=_POOL_MARKING_SOURCE if from_pool else _OPERATOR_MARKING_SOURCE,
        check_status=CHECK_STATUS_NEW,
        meta_status=META_STATUS_ASSIGNED,
        marking_code_id=code.id,
        created_by_user_id=actor_user_id,
    )
    session.add(marking)
    await session.flush()
    new_error: FbsKizError | None = None
    try:
        if current is not None:
            await _delete_sgtin_from_wb(order, http_client, token)
        await marking_svc.attach_order_meta_to_wb_and_sync(
            session,
            tenant_id,
            order,
            marking,
            http_client,
            actor_user_id=actor_user_id,
            api_token=token,
        )
    except FbsKizError as exc:
        new_error = exc
    except marking_svc.FbsMarkingError as exc:
        new_error = _marking_error_to_kiz(exc)
    except WildberriesClientError as exc:
        new_error = FbsKizError(marking_svc._wb_error_code(exc))
    if new_error is not None:
        if current is None:
            raise new_error
        try:
            await _restore_previous_wb_marking(
                order,
                current,
                http_client,
                token,
            )
        except FbsKizError as restore_error:
            await _persist_failed_replacement_state(
                session,
                tenant_id,
                order.id,
                new_error_code=new_error.code,
                restore_error_code=restore_error.code,
            )
            raise FbsKizError(
                _REPLACEMENT_RESTORE_FAILED,
                context={
                    "new_error": new_error.code,
                    "restore_error": restore_error.code,
                },
                persist_failure_state=True,
            ) from restore_error
        raise new_error
    if current is not None:
        await _void_existing_sgtin_marking_locally(
            session,
            current,
            actor_user_id=actor_user_id,
            reason=_VOID_REPLACED_REASON,
        )
    previous_was_pool = current is not None and current.source == _POOL_MARKING_SOURCE
    if from_pool:
        if not previous_was_pool:
            line_ref.line.qty_marking_printed = int(line_ref.line.qty_marking_printed) + 1
    elif not previous_was_pool:
        line_ref.line.qty_marking_external = int(line_ref.line.qty_marking_external) + 1
    await session.flush()


def _ok_commit_row(order_id: uuid.UUID) -> FbsKizCommitRow:
    return FbsKizCommitRow(
        order_id=order_id,
        status="ok",
        code="ok",
        message="ok",
    )


def _error_commit_row(order_id: uuid.UUID, exc: FbsKizError) -> FbsKizCommitRow:
    return FbsKizCommitRow(
        order_id=order_id,
        status="error",
        code=exc.code,
        message=_error_message(exc),
    )


async def commit_kiz_pairs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    pairs: list[FbsKizCommitPair],
    idempotency_key: str,
    http_client: httpx.AsyncClient,
) -> list[FbsKizCommitRow]:
    del idempotency_key
    await session.rollback()

    rows: list[FbsKizCommitRow] = []
    for pair in pairs:
        try:
            await _commit_one_kiz_pair(
                session,
                tenant_id,
                actor_user_id,
                pair,
                http_client,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            rows.append(
                _error_commit_row(
                    pair.order_id,
                    FbsKizError("duplicate_kiz", context={"source": "db"}),
                )
            )
        except FbsKizError as exc:
            if exc.persist_failure_state:
                await session.commit()
            else:
                await session.rollback()
            rows.append(_error_commit_row(pair.order_id, exc))
        else:
            rows.append(_ok_commit_row(pair.order_id))

    return rows
