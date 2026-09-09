"""WMS-111/WMS-112: automatic return document after a confirmed-transfer cancel.

Owner directive 2026-09-10 (see AGENTS.md "ВТОРОЕ ГЛАВНОЕ ПРАВИЛО"): reuse the
existing return-document family. WMS already has a return kind — it is the
same `InboundIntakeRequest` used for a manual return, distinguished by
`operation_type = "return"` and `marketplace = "wildberries"`. This module
creates that same request automatically when the sole legitimate trigger fires:
the buyer has cancelled a WB FBS order that WMS had already handed over.

Why this stays a "document, not a movement":

* The card explicitly says the created document must NOT increment stock.
  Physical acceptance is a separate operator action. Here we only leave a
  draft in the `draft` status with lines whose `expected_qty` is the shipped
  quantity and `posted_qty=0` — the intake service only touches stock when
  `posted_qty` moves, which is guarded by the operator's scan flow.
* The transfer boundary is checked against existing state
  (`confirmed_order_handover_dates`, the same signal billing already trusts),
  not by adding a new "was_transferred" flag on the order.
* The idempotency key is the natural WB order id: it is already unique per
  seller for FBS. The first successful creation writes a marker into the
  order's `meta_details_json`; every retry sees that marker and returns the
  existing request. No separate table, no separate counter.
* The cancel-time is honestly stored: WB payload's `cancelledAt` when present,
  otherwise the moment WMS observed the cancel — with the source recorded next
  to it so a reader can tell them apart. No synthesised historic timestamps.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderProduct
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

# Ключ в meta_details_json заказа, куда пишется факт создания документа
# возврата. Он же — источник идемпотентности: повторный вызов на том же заказе
# видит этот ключ и не заводит второй документ.
CANCEL_RETURN_META_KEY = "wb_cancel_return"

# Источники времени отмены. WB в открытой части API момент отмены заказа не
# отдаёт вовсе, но мы предусмотрительно читаем `cancelledAt`, если он появится в
# полезной нагрузке. Иначе фиксируем момент, когда WMS увидел отмену, и явным
# маркером сообщаем читателю: время не от WB.
CANCEL_TIME_SOURCE_WB_PAYLOAD = "wb_payload"
CANCEL_TIME_SOURCE_RECEIVED_AT = "received_at"

# Известные ключи в строках WB, где мог бы жить момент отмены. Проверяем все —
# WB может добавить одно из них, а мы не будем гадать.
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
    """Момент отмены плюс маркер, откуда он взят.

    Хранится вместе с документом возврата — сам момент нужен реестру отмен
    (WMS-112), а маркер источника обязателен: без него читатель не отличит
    честный WB-момент от нашего received-at, и это уже приводило к спорам.
    """

    at: datetime
    source: str


def _parse_iso(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def cancel_time_from_row(
    row: dict[str, Any] | None,
    *,
    received_at: datetime | None = None,
) -> CancelTime:
    """Достать момент отмены из строки WB или взять received-at.

    `received_at` можно передать явно для тестов; в проде это всегда
    `datetime.now(UTC)`. Публично отдаём только время в UTC.
    """
    if row is not None:
        for key in _CANCEL_TIME_ROW_KEYS:
            parsed = _parse_iso(row.get(key))
            if parsed is not None:
                return CancelTime(at=parsed, source=CANCEL_TIME_SOURCE_WB_PAYLOAD)
    fallback = received_at if received_at is not None else datetime.now(UTC)
    if fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=UTC)
    return CancelTime(at=fallback, source=CANCEL_TIME_SOURCE_RECEIVED_AT)


def has_cancel_return_marker(order: FbsOrder) -> bool:
    """Уже ли создан документ возврата для этой отмены?"""
    details = order.meta_details_json or {}
    marker = details.get(CANCEL_RETURN_META_KEY)
    return isinstance(marker, dict) and bool(marker.get("inbound_request_id"))


def cancel_return_marker(order: FbsOrder) -> dict[str, Any] | None:
    details = order.meta_details_json or {}
    marker = details.get(CANCEL_RETURN_META_KEY)
    return marker if isinstance(marker, dict) else None


async def was_transferred(
    session: AsyncSession,
    order: FbsOrder,
) -> bool:
    """Была ли уже подтверждённая передача поставки маркетплейсу.

    Один в один сигнал, которым пользуется биллинг (`confirmed_order_handover_dates`).
    Никакого нового флага заводить нельзя: одна и та же величина, посчитанная в
    двух местах, обязательно разъедется.
    """
    handovers = await confirmed_order_handover_dates(session, order.tenant_id, [order])
    return order.id in handovers


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
    session: AsyncSession,
    order: FbsOrder,
    *,
    cancel_time: CancelTime,
) -> InboundIntakeRequest | None:
    """Создать документ возврата ровно один раз для отмены после передачи.

    Возвращает уже созданный (или только что созданный) документ. Возвращает
    None, если создать нельзя по причине, которую документ поправить не может:
    заказу не назначен склад (тогда физически возвращать некуда), или у заказа
    нет привязки к товару — в обоих случаях эту дырку закрывает оператор, а не
    автоматика. Функция не бросает исключений, чтобы отмена не падала из-за
    невозможности завести приёмку-возврат.

    Никаких движений остатка: документ создаётся в статусе DRAFT со строкой
    `expected_qty` и `posted_qty=0`. Физическая приёмка — отдельное действие
    оператора, оно и передвигает остаток.
    """
    existing_marker = cancel_return_marker(order)
    if existing_marker is not None:
        request_id_raw = existing_marker.get("inbound_request_id")
        if isinstance(request_id_raw, str):
            try:
                existing_id = uuid.UUID(request_id_raw)
            except ValueError:
                existing_id = None
            if existing_id is not None:
                existing = await session.get(InboundIntakeRequest, existing_id)
                if existing is not None:
                    return existing
        # Маркер оказался повреждённым (внутрилежащий UUID нечитаем или строку
        # удалили руками из базы). Молча его пересоздавать нельзя — это
        # спрячет расхождение. Логируем и возвращаем None: следующая попытка
        # либо получит корректный маркер, либо снова придёт сюда и разберём.
        logger.warning(
            "wms111_cancel_return_marker_broken order_id=%s marker=%s",
            order.id,
            existing_marker,
        )
        return None

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
        "inbound_request_id": str(req.id),
        "wb_order_id": int(order.wb_order_id),
        "cancelled_at": cancel_time.at.isoformat(),
        "cancelled_at_source": cancel_time.source,
        "created_at": datetime.now(UTC).isoformat(),
    }
    order.meta_details_json = details
    await session.flush()
    logger.info(
        "wms111_cancel_return_created order_id=%s wb_order_id=%s request_id=%s source=%s",
        order.id,
        order.wb_order_id,
        req.id,
        cancel_time.source,
    )
    return req


async def maybe_create_cancel_return_document(
    session: AsyncSession,
    order: FbsOrder,
    *,
    row: dict[str, Any] | None = None,
    received_at: datetime | None = None,
) -> InboundIntakeRequest | None:
    """Точка входа для внешнего кода.

    Собирает воедино три проверки:
      1) отмена относится к WB (для Ozon возвратом занимается отдельный сервис),
      2) заказ уже был передан (иначе документ возврата не нужен — товар не
         покидал склад),
      3) документ ещё не создавался (маркер в meta_details_json).

    После этого просит `ensure_cancel_return_document` создать документ.
    Ошибка на любом шаге не должна валить внешнюю транзакцию: отмена в кабинете
    маркетплейса уже необратима, локальная часть обязана дойти до конца, а
    документ возврата в худшем случае заведёт оператор руками, как и раньше.
    """
    if order.marketplace != "wb":
        return None
    if not await was_transferred(session, order):
        return None
    cancel_time = cancel_time_from_row(row, received_at=received_at)
    try:
        return await ensure_cancel_return_document(
            session,
            order,
            cancel_time=cancel_time,
        )
    except Exception:
        logger.exception(
            "wms111_cancel_return_failed order_id=%s wb_order_id=%s",
            order.id,
            order.wb_order_id,
        )
        return None


__all__ = [
    "CANCEL_RETURN_META_KEY",
    "CANCEL_TIME_SOURCE_RECEIVED_AT",
    "CANCEL_TIME_SOURCE_WB_PAYLOAD",
    "CancelTime",
    "cancel_return_marker",
    "cancel_time_from_row",
    "ensure_cancel_return_document",
    "has_cancel_return_marker",
    "maybe_create_cancel_return_document",
    "was_transferred",
]
