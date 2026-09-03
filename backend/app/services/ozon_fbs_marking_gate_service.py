"""Ozon-specific marking readiness and status projection."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from app.models.fbs_order import (
    CHECK_STATUS_CHECKING,
    CHECK_STATUS_ERROR,
    CHECK_STATUS_OK,
    META_STATUS_ACCEPTED,
    META_STATUS_PENDING,
    META_STATUS_REJECTED,
    META_STATUS_REPLACEMENT_REQUIRED,
    FbsOrder,
    FbsOrderMarking,
)

# Ключ признака «Ozon ответил про требования» живёт рядом с разбором
# отправления; здесь он только читается.
OZON_REQUIREMENTS_KEY = "ozon_requirements"


def _exemplar_id(marking: FbsOrderMarking) -> int | None:
    details = marking.meta_details_json if isinstance(marking.meta_details_json, dict) else {}
    value = details.get("exemplar_id")
    return value if isinstance(value, int) else None


def _created_at_key(marking: FbsOrderMarking) -> float:
    return marking.created_at.timestamp() if marking.created_at is not None else float("-inf")


def current_markings(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
) -> list[FbsOrderMarking]:
    """Select newest expected rows before evaluating their marketplace status."""
    positions = {position.id: position.quantity for position in order.product_positions}
    if not positions or any(quantity <= 0 for quantity in positions.values()):
        return []
    kinds = {
        str(kind).strip().lower()
        for kind in (order.required_meta_json or [])
        if str(kind).strip()
    } or {marking.kind for marking in markings}
    candidates = [
        marking
        for marking in markings
        if marking.kind in kinds
        and marking.order_product_id in positions
        and _exemplar_id(marking) is not None
    ]
    grouped: dict[tuple[str, Any], list[FbsOrderMarking]] = defaultdict(list)
    for marking in candidates:
        grouped[(marking.kind, marking.order_product_id)].append(marking)
    selected: list[FbsOrderMarking] = []
    for (kind, position_id), rows in grouped.items():
        del kind
        rows.sort(key=_created_at_key, reverse=True)
        expected = positions[position_id]
        if len(rows) <= expected:
            selected.extend(rows)
            continue
        cutoff = _created_at_key(rows[expected - 1])
        selected.extend(row for row in rows if _created_at_key(row) >= cutoff)
    return selected


def ozon_requirements_known(order: FbsOrder) -> bool:
    """Ответил ли Ozon по этому отправлению, нужна ли маркировка.

    Признак ставит разбор отправления (`ozon_fbs_sync_service`), когда в ответе
    Ozon действительно был объект `requirements`. Отличать «Ozon сказал: не
    нужна» от «мы не спрашивали» обязательно: раньше оба случая выглядели как
    пустой `required_meta_json`, и гейт выпускал отправление в обоих.
    """
    details = order.meta_details_json if isinstance(order.meta_details_json, dict) else {}
    return isinstance(details.get(OZON_REQUIREMENTS_KEY), dict)


def compute_delivery_allowed(order: FbsOrder, markings: list[FbsOrderMarking]) -> bool:
    required = {
        str(kind).strip().lower()
        for kind in (order.required_meta_json or [])
        if str(kind).strip()
    }
    if not required:
        # Пустое требование — разрешение только тогда, когда Ozon сам сказал,
        # что маркировка не нужна. Пока он этого не сказал, выпускать нельзя:
        # отправление с маркируемым товаром уехало бы без единого кода, а это
        # товар и регуляторный учёт, а не косметика экрана.
        return ozon_requirements_known(order)
    positions = {position.id: position.quantity for position in order.product_positions}
    if not positions or any(quantity <= 0 for quantity in positions.values()):
        return False
    selected = current_markings(order, markings)
    counts = Counter((marking.kind, marking.order_product_id) for marking in selected)
    if any(
        counts[(kind, position_id)] != quantity
        for kind in required
        for position_id, quantity in positions.items()
    ):
        return False
    exemplar_counts = Counter((marking.kind, _exemplar_id(marking)) for marking in selected)
    if any(count > 1 for count in exemplar_counts.values()):
        return False
    for marking in selected:
        details = marking.meta_details_json if isinstance(marking.meta_details_json, dict) else {}
        status = details.get("status")
        if (
            not isinstance(status, str)
            or status.strip().lower() != "ship_available"
            or marking.meta_status in {META_STATUS_REJECTED, META_STATUS_REPLACEMENT_REQUIRED}
            or (isinstance(marking.reason, str) and marking.reason.strip())
        ):
            return False
    return True


def apply_status(
    order: FbsOrder,
    markings: list[FbsOrderMarking],
    *,
    details: dict[str, Any],
    reason: str | None,
    accepted: bool,
    pending: bool,
) -> None:
    shared_details = {key: value for key, value in details.items() if key != "exemplar_id"}
    for marking in current_markings(order, markings):
        if marking.meta_status in {META_STATUS_REJECTED, META_STATUS_REPLACEMENT_REQUIRED}:
            continue
        own_details = (
            dict(marking.meta_details_json)
            if isinstance(marking.meta_details_json, dict)
            else {}
        )
        marking.meta_details_json = {**own_details, **shared_details}
        marking.reason = reason
        marking.meta_status = (
            META_STATUS_ACCEPTED
            if accepted
            else META_STATUS_PENDING
            if pending
            else META_STATUS_REJECTED
        )
        marking.check_status = (
            CHECK_STATUS_OK
            if accepted
            else CHECK_STATUS_CHECKING
            if pending
            else CHECK_STATUS_ERROR
        )


def delivery_message(order: FbsOrder, markings: list[FbsOrderMarking]) -> str:
    if not order.required_meta_json:
        if ozon_requirements_known(order):
            return "Ozon: маркировка не требуется."
        # Утверждать «не требуется» мы не вправе: требования отправления от
        # Ozon ещё не получены, значит мы просто не знаем.
        return (
            "Ozon ещё не сообщил, нужна ли маркировка по этому отправлению — "
            "обновите заказы Ozon."
        )
    if compute_delivery_allowed(order, markings):
        return "Ozon: маркировка подтверждена для всех товаров."
    return "Ozon не подтвердил маркировку для всех товаров отправления."
