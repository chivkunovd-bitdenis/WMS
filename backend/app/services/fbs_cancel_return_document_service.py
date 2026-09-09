"""WMS-111/112: persist cancellation evidence and create an existing draft return.

The order row lock serializes retries. Observation survives a failed document
savepoint; a later seller sync retries missing documents. Nothing here receives
stock. The original supply link is retained as evidence before detach, and its
current confirmed handover is read for both document creation and the registry.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.services.document_number_service import (
    DOC_TYPE_INBOUND,
    assign_display_number_if_missing,
    assign_document_number_if_missing,
)
from app.services.fbs_order_billing_service import confirmed_order_handover_dates
from app.services.inbound_intake_service import (
    OPERATION_TYPE_RETURN,
    STATUS_DRAFT,
)

logger = logging.getLogger(__name__)

# Existing order JSON holds cancellation evidence and the draft document link.
# The existing order row lock, not the marker alone, makes creation idempotent.
CANCEL_RETURN_META_KEY = "wb_cancel_return"
CANCEL_TIME_SOURCE_WB_PAYLOAD = "wb_payload"
CANCEL_TIME_SOURCE_OBSERVED_AT = "observed_at"
# Compatibility name for callers; new records explicitly mean WMS observation.
CANCEL_TIME_SOURCE_RECEIVED_AT = CANCEL_TIME_SOURCE_OBSERVED_AT

# Accepted event-time fields when provided; absence is explicitly labelled.
_CANCEL_TIME_ROW_KEYS: tuple[str, ...] = (
    "cancelledAt",
    "cancelled_at",
    "cancelAt",
    "cancelDate",
    "cancellationDate",
    "cancellation_date",
)

# Маркетплейс-строка ровно та, которую использует ручное создание возврата
# из inbound_intake_service.RETURN_MARKETPLACES. Не заводить новых значений —
# любые фильтры и биллинг ждут именно её.
_WB_MARKETPLACE = "wildberries"


@dataclass(frozen=True)
class CancelTime:
    """WB event time or first WMS observation, labelled and stored on the order."""

    at: datetime
    source: str


def _parse_iso(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return (raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)).astimezone(UTC)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)).astimezone(UTC)


def cancel_time_from_row(
    row: dict[str, Any] | None,
    *,
    received_at: datetime | None = None,
) -> CancelTime:
    """Prefer an explicit WB event time; otherwise use the WMS observation.

    Callers pass the observation captured before pagination, locks or cancellation
    side effects. Direct callers observe the cancellation when entering here.
    """
    if row is not None:
        for key in _CANCEL_TIME_ROW_KEYS:
            parsed = _parse_iso(row.get(key))
            if parsed is not None:
                return CancelTime(at=parsed, source=CANCEL_TIME_SOURCE_WB_PAYLOAD)
    fallback = received_at if received_at is not None else datetime.now(UTC)
    if fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=UTC)
    return CancelTime(at=fallback.astimezone(UTC), source=CANCEL_TIME_SOURCE_OBSERVED_AT)


def has_cancel_return_marker(order: FbsOrder) -> bool:
    """Уже ли создан документ возврата для этой отмены?"""
    details = order.meta_details_json or {}
    marker = details.get(CANCEL_RETURN_META_KEY)
    return isinstance(marker, dict) and bool(marker.get("inbound_request_id"))


def cancel_return_marker(order: FbsOrder) -> dict[str, Any] | None:
    details = order.meta_details_json or {}
    marker = details.get(CANCEL_RETURN_META_KEY)
    return marker if isinstance(marker, dict) else None


def cancelled_after_transfer(cancelled_at: datetime, transfer_at: datetime | None) -> bool | None:
    if transfer_at is None:
        return None
    return (_parse_iso(transfer_at) or transfer_at) <= (_parse_iso(cancelled_at) or cancelled_at)


async def cancellation_handover_dates(
    session: AsyncSession, tenant_id: uuid.UUID, orders: list[FbsOrder],
) -> dict[uuid.UUID, datetime]:
    dates = await confirmed_order_handover_dates(session, tenant_id, orders)
    original_ids: dict[uuid.UUID, uuid.UUID] = {}
    for order in orders:
        marker = cancel_return_marker(order) or {}
        try:
            original_ids[order.id] = uuid.UUID(str(marker.get("source_supply_id")))
        except ValueError:
            continue
    supplies = {supply.id: supply for supply in await session.scalars(
        select(FbsSupply).where(FbsSupply.tenant_id == tenant_id,
                                FbsSupply.id.in_(original_ids.values()))
    )} if original_ids else {}
    for order in orders:
        supply = supplies.get(original_ids[order.id]) if order.id in original_ids else None
        if (order.id not in dates and supply is not None
                and supply.seller_id == order.seller_id
                and supply.marketplace == order.marketplace
                and supply.delivered_at is not None):
            dates[order.id] = _parse_iso(supply.delivered_at) or supply.delivered_at
    return dates


async def was_transferred(session: AsyncSession, order: FbsOrder) -> bool:
    return order.id in await cancellation_handover_dates(session, order.tenant_id, [order])


async def _lines_for_order(
    session: AsyncSession,
    order: FbsOrder,
) -> list[tuple[uuid.UUID, int]]:
    """Товар и количество для строки возврата.

    Для WB в FBS-заказе всегда одна штука одного товара — это то, что уехало и
    может вернуться. Для многотоварных отправлений (не WB) берём каждую строку
    из FbsOrderProduct, чтобы шапка документа отражала всё уехавшее.
    """
    if order.product_id is not None:
        return [(order.product_id, 1)]
    result = await session.execute(
        select(FbsOrderProduct.product_id, FbsOrderProduct.quantity).where(
            FbsOrderProduct.order_id == order.id,
            FbsOrderProduct.product_id.is_not(None),
        )
    )
    return [
        (product_id, int(qty))
        for product_id, qty in result
        if product_id is not None
    ]


async def ensure_cancel_return_document(
    session: AsyncSession, order: FbsOrder, *, cancel_time: CancelTime,
) -> InboundIntakeRequest | None:
    """Lock/re-read evidence, persist observation, then isolate document writes.

    Do not refresh the whole object: callers have pending status changes. Read
    metadata under the lock before any autoflush can overwrite a concurrent
    marker from a stale ORM object. Caller owns the outer transaction.
    """
    if order.marketplace != "wb":
        return None
    with session.no_autoflush:
        stored = (await session.execute(select(FbsOrder.meta_details_json).where(
            FbsOrder.id == order.id, FbsOrder.tenant_id == order.tenant_id,
            FbsOrder.seller_id == order.seller_id,
        ).with_for_update())).one()
    details = dict(stored[0] or {})
    # Preserve this caller's pending edits to unrelated metadata without copying
    # a stale cancellation marker over the row just read under the lock.
    history = inspect(order).attrs.meta_details_json.history
    if history.has_changes():
        previous = dict(history.deleted[0] or {}) if history.deleted else {}
        pending = dict(history.added[0] or {}) if history.added else {}
        for key in (previous.keys() | pending.keys()) - {CANCEL_RETURN_META_KEY}:
            if previous.get(key) != pending.get(key):
                if key in pending:
                    details[key] = pending[key]
                else:
                    details.pop(key, None)
    marker = dict(details.get(CANCEL_RETURN_META_KEY) or {})
    if not marker.get("cancelled_at") or (
        cancel_time.source == CANCEL_TIME_SOURCE_WB_PAYLOAD
        and marker.get("cancelled_at_source") != CANCEL_TIME_SOURCE_WB_PAYLOAD
    ):
        marker.update(cancelled_at=cancel_time.at.astimezone(UTC).isoformat(),
                      cancelled_at_source=cancel_time.source)
    if not marker.get("source_supply_id") and order.supply_id is not None:
        marker["source_supply_id"] = str(order.supply_id)
    marker["wb_order_id"] = int(order.wb_order_id)
    details[CANCEL_RETURN_META_KEY] = marker
    order.meta_details_json = details
    # Observation and pending cancellation changes must survive a document error.
    await session.flush()
    existing_id = marker.get("inbound_request_id")
    if existing_id:
        try:
            return await session.get(InboundIntakeRequest, uuid.UUID(str(existing_id)))
        except ValueError:
            logger.error("wms111_invalid_return_reference order_id=%s", order.id)
            return None
    at = _parse_iso(marker.get("cancelled_at"))
    handover = (await cancellation_handover_dates(session, order.tenant_id, [order])).get(order.id)
    if at is None or cancelled_after_transfer(at, handover) is not True:
        return None
    order_id = order.id
    try:
        async with session.begin_nested():
            return await _create_document(session, order, marker)
    except Exception:
        # A rollback expires mutated ORM fields. Refresh explicitly before the
        # cancellation caller continues to detach and commit its own changes.
        await session.refresh(order)
        logger.exception("wms111_cancel_return_failed order_id=%s", order_id)
        return None


async def _create_document(
    session: AsyncSession, order: FbsOrder, marker: dict[str, Any],
) -> InboundIntakeRequest | None:
    if order.warehouse_id is None:
        logger.info(
            "wms111_cancel_return_skipped_no_warehouse order_id=%s wb_order_id=%s",
            order.id,
            order.wb_order_id,
        )
        return None
    lines = await _lines_for_order(session, order)
    if not lines:
        logger.info(
            "wms111_cancel_return_skipped_no_product order_id=%s wb_order_id=%s",
            order.id,
            order.wb_order_id,
        )
        return None

    req = InboundIntakeRequest(
        tenant_id=order.tenant_id,
        warehouse_id=order.warehouse_id,
        seller_id=order.seller_id,
        status=STATUS_DRAFT,
        operation_type=OPERATION_TYPE_RETURN,
        marketplace=_WB_MARKETPLACE,
        comment=(
            f"Автосоздан по отмене WB FBS-заказа №{order.wb_order_id}. "
            f"Физическая приёмка — отдельное действие оператора."
        ),
    )
    session.add(req)
    for product_id, qty in lines:
        session.add(
            InboundIntakeLine(
                request=req,
                product_id=product_id,
                expected_qty=int(qty),
                actual_qty=None,
                posted_qty=0,
                added_by_fulfillment=True,
            )
        )
    await assign_document_number_if_missing(session, order.tenant_id, DOC_TYPE_INBOUND, req)
    await assign_display_number_if_missing(session, order.tenant_id, DOC_TYPE_INBOUND, req)
    await session.flush()

    details = dict(order.meta_details_json or {})
    details[CANCEL_RETURN_META_KEY] = {
        **marker,
        "inbound_request_id": str(req.id),
        "created_at": datetime.now(UTC).isoformat(),
    }
    order.meta_details_json = details
    await session.flush()
    logger.info(
        "wms111_cancel_return_created order_id=%s wb_order_id=%s request_id=%s source=%s",
        order.id,
        order.wb_order_id,
        req.id,
        marker["cancelled_at_source"],
    )
    return req


async def maybe_create_cancel_return_document(
    session: AsyncSession,
    order: FbsOrder,
    *,
    row: dict[str, Any] | None = None,
    received_at: datetime | None = None,
) -> InboundIntakeRequest | None:
    """Record a WB cancellation, including those that do not need a return.

    received_at is retained as a keyword for existing callers; it denotes the
    time this response was observed by WMS, never a claimed WB event time.
    """
    return await ensure_cancel_return_document(
        session, order, cancel_time=cancel_time_from_row(row, received_at=received_at),
    )


async def retry_pending_cancel_returns(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID,
) -> None:
    """Retry recorded cancellations locally even though WB polling skips terminals.

    Legacy rows without evidence are deliberately excluded: retry time cannot
    be substituted for an unknown historical cancellation time.
    """
    meta = FbsOrder.meta_details_json[CANCEL_RETURN_META_KEY]
    orders = list(await session.scalars(select(FbsOrder).where(
        FbsOrder.tenant_id == tenant_id, FbsOrder.seller_id == seller_id,
        FbsOrder.marketplace == "wb", FbsOrder.status == FBS_ORDER_STATUS_CANCELLED,
        meta["cancelled_at"].as_string().is_not(None),
        meta["inbound_request_id"].as_string().is_(None),
    ).order_by(FbsOrder.id)))
    for order in orders:
        await maybe_create_cancel_return_document(session, order)
