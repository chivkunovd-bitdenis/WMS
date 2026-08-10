"""FBS KIZ manual binding lookup by WB order sticker."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
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
    FbsOrder,
    FbsOrderMarking,
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
from app.services.wb_card_enrichment import first_photo_url_from_card
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import delete_marketplace_order_meta

_MISSING_PRODUCT_NAME = "Товар не сопоставлен"
_POOL_MARKING_SOURCE = "pool"
_OPERATOR_MARKING_SOURCE = "operator"
_EXTERNAL_FBS_MARKING_SOURCE = "external_fbs"
_VOID_REPLACED_REASON = "replaced_by_external_fbs_kiz"
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
    ('"\u2116;:?', "@#$^&"),
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
    ) -> None:
        self.code = code
        self.context = context or {}
        self.message = message
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
    if current_ai in _GS1_INTERNAL_VARIABLE_AIS:
        return next_ai in _GS1_INTERNAL_VARIABLE_AIS and int(next_ai) > int(current_ai)
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


def _has_keyboard_layout_noise(value: str) -> bool:
    return any(char in _KEYBOARD_LAYOUT_MARKERS for char in value)


def _repair_keyboard_layout(value: str) -> str | None:
    if not _has_keyboard_layout_noise(value):
        return None
    repaired = value.translate(_KEYBOARD_LAYOUT_TRANSLATION)
    if repaired != value and is_probably_cis(repaired):
        return repaired
    return None


def normalize_scanned_cis(raw: str) -> tuple[str, list[str]]:
    value = raw.rstrip(" \r\n")
    hints: list[str] = []

    for prefix in _AIM_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix) :]
            hints.append("aim_prefix")
            break

    value, gs_changed = _restore_gs_substitutes(value)
    if gs_changed:
        hints.append("gs_substitute")

    repaired = _repair_keyboard_layout(value)
    if repaired is not None:
        value = repaired
        hints.append("keyboard_layout")
        value, gs_changed_after_layout = _restore_gs_substitutes(value)
        if gs_changed_after_layout and "gs_substitute" not in hints:
            hints.append("gs_substitute")

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
    for order in orders:
        if _normalized_optional(order.sticker_code) == sticker:
            return order
    for order in orders:
        if _normalized_optional(order.wb_barcode) == sticker:
            return order
    # A third variant (partA+partB from the WB sticker) is deliberately not implemented:
    # we store neither part, and what the printed sticker's QR actually encodes is unknown
    # until the hardware check in TASK.md section 8. Add it together with persisting
    # partA/partB once a real scan proves it is needed.
    return None


def _current_sgtin_marking(order: FbsOrder) -> FbsOrderMarking | None:
    candidates = [
        marking
        for marking in order.markings
        if marking.kind == MARKING_KIND_SGTIN and marking.meta_status != META_STATUS_REJECTED
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda marking: (marking.created_at, marking.id.hex))


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
    barcode = order.wb_barcode or (product.wb_barcode if product is not None else None)
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
    normalized_sticker = normalize_scanned_sticker(sticker)
    if not normalized_sticker:
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
    order = _find_order_by_sticker(orders, normalized_sticker)
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
            FbsOrderMarking.value == value,
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
    stmt = select(MarkingCode).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.cis_code == value,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def _ensure_kiz_not_occupied_in_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    value: str,
) -> None:
    code = await _get_marking_code_by_cis(session, tenant_id, value)
    if code is not None and code.status != STATUS_AVAILABLE:
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
) -> _ValidatedKizPair:
    value, hints = normalize_scanned_cis(raw_value)
    if not is_probably_cis(value):
        raise FbsKizError(
            "not_a_kiz",
            context={"debug": scan_debug(raw_value)},
            message="not_a_kiz",
        )

    order = await _get_order_for_kiz(
        session,
        tenant_id,
        order_id,
        for_update=for_update,
    )
    await _ensure_kiz_not_bound_to_other_order(session, tenant_id, order.id, value)
    await _ensure_kiz_not_occupied_in_pool(session, tenant_id, value)
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
    code = await _get_marking_code_by_cis(
        session,
        tenant_id,
        value,
        for_update=True,
    )
    if code is not None and code.status != STATUS_AVAILABLE:
        raise FbsKizError(
            "duplicate_kiz",
            context={"marking_code_id": str(code.id), "status": code.status},
        )
    if code is None:
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
    else:
        code.seller_id = order.seller_id
        code.product_id = order.product_id
        code.source = _EXTERNAL_FBS_MARKING_SOURCE
        code.status = STATUS_APPLIED
        code.applied_at = now
        code.packaging_task_line_id = line.id
        code.pool_id = None
        code.import_batch_id = None
        code.label_artifact_pdf = None
    await session.flush()
    return code


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
    try:
        await delete_marketplace_order_meta(
            http_client,
            api_token=token,
            order_id=int(order.wb_order_id),
            key=MARKING_KIND_SGTIN,
        )
    except WildberriesClientError as exc:
        raise FbsKizError(marking_svc._wb_error_code(exc)) from exc

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
        )
        if marking.source == _OPERATOR_MARKING_SOURCE and line is not None:
            line.qty_marking_external = max(0, int(line.qty_marking_external) - 1)

    await session.delete(marking)
    await session.flush()


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
    )
    order = validated.order
    current = await _current_sgtin_marking_for_update(session, order.id)
    if (
        current is not None
        and current.value == validated.value
        and current.meta_status != META_STATUS_REJECTED
    ):
        # Idempotent replay: this exact pair is already bound, e.g. the client retried
        # after a network timeout. Re-binding it would void a healthy code and ask the
        # operator to confirm a change that is not a change.
        return
    if current is not None and not pair.confirmed:
        raise FbsKizError(
            "needs_confirmation",
            context={"current_kiz": _mask_kiz(current.value)},
        )

    token = await marking_svc.require_marketplace_token(
        session, tenant_id, order.seller_id
    )
    if current is not None:
        await void_existing_sgtin_marking(
            session,
            tenant_id,
            order,
            current,
            http_client,
            actor_user_id=actor_user_id,
            api_token=token,
        )

    line_ref = await _packaging_line_for_order(session, tenant_id, order)
    code = await _create_or_apply_external_code(
        session,
        tenant_id,
        order,
        validated.value,
        line_ref.line,
    )
    await marking_code_svc.record_event(
        session,
        code=code,
        event_type=EVENT_APPLIED,
        actor=actor_user_id,
        document_number=line_ref.document_number,
        packaging_task=line_ref.line,
    )
    marking = FbsOrderMarking(
        order_id=order.id,
        tenant_id=tenant_id,
        kind=MARKING_KIND_SGTIN,
        value=validated.value,
        source=_OPERATOR_MARKING_SOURCE,
        check_status=CHECK_STATUS_NEW,
        meta_status=META_STATUS_ASSIGNED,
        marking_code_id=code.id,
        created_by_user_id=actor_user_id,
    )
    session.add(marking)
    await session.flush()

    try:
        await marking_svc.attach_order_meta_to_wb_and_sync(
            session,
            tenant_id,
            order,
            marking,
            http_client,
            api_token=token,
        )
    except marking_svc.FbsMarkingError as exc:
        raise _marking_error_to_kiz(exc) from exc

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
            await session.rollback()
            rows.append(_error_commit_row(pair.order_id, exc))
        else:
            rows.append(_ok_commit_row(pair.order_id))

    return rows
