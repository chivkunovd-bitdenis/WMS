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


def _exemplar_id(marking: FbsOrderMarking) -> int | None:
    details = marking.meta_details_json if isinstance(marking.meta_details_json, dict) else {}
    value = details.get("exemplar_id")
    return value if isinstance(value, int) else None


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
        rows.sort(
            key=lambda marking: (str(marking.created_at), str(marking.id)),
            reverse=True,
        )
        selected.extend(rows[: positions[position_id]])
    return selected


def compute_delivery_allowed(order: FbsOrder, markings: list[FbsOrderMarking]) -> bool:
    required = {
        str(kind).strip().lower()
        for kind in (order.required_meta_json or [])
        if str(kind).strip()
    }
    if not required:
        return True
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
        return "Ozon: маркировка не требуется."
    if compute_delivery_allowed(order, markings):
        return "Ozon: маркировка подтверждена для всех товаров."
    return "Ozon не подтвердил маркировку для всех товаров отправления."
