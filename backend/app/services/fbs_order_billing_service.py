"""Тарификация сборки заказов FBS.

Заказ считается сделанной работой не тогда, когда мы нажали «передать», а тогда,
когда маркетплейс подтвердил, что забрал его: статусы `sorted` (WB отсортировал
у себя) и `done` (`wbStatus = sold`). Статусы `packed` и `in_delivery` ставит сам
склад нажатием кнопки — ошиблись кнопкой, и заказ уже оказался бы в счёте.

Считаем **за штуку товара**, а не за заказ: у Wildberries в заказе всегда одна
штука, у Ozon в отправлении может быть несколько позиций.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
    FbsOrderProduct,
)
from app.services.billing_ledger_service import BillingLedgerError, record_operational_charge
from app.services.operation_fact_service import OperationFactError, line_input, write_operation_fact

logger = logging.getLogger(__name__)

FBS_ORDER_SERVICE_CODE = "fbs_order"
CONFIRMED_STATUSES = frozenset({FBS_ORDER_STATUS_SORTED, FBS_ORDER_STATUS_DONE})
SOURCE_TYPE = "fbs_order"


async def _order_quantity(session: AsyncSession, order: FbsOrder) -> int:
    """Сколько штук товара уехало заказом."""
    positions = (
        await session.scalars(
            select(FbsOrderProduct.quantity).where(FbsOrderProduct.order_id == order.id)
        )
    ).all()
    if positions:
        return sum(int(quantity) for quantity in positions)
    # Заказ Wildberries — одна штука одного товара, отдельных позиций у него нет.
    return 1


async def record_fbs_order_confirmed(
    session: AsyncSession,
    order: FbsOrder,
    *,
    occurred_at: datetime | None = None,
) -> None:
    """Записать факт и начисление за собранный заказ. Повтор безопасен."""
    if order.status not in CONFIRMED_STATUSES:
        return
    if order.seller_id is None:
        return
    moment = occurred_at or datetime.now(UTC)
    quantity = await _order_quantity(session, order)

    try:
        await write_operation_fact(
            session,
            tenant_id=order.tenant_id,
            operation_code="fbs_order",
            billable_service_code=FBS_ORDER_SERVICE_CODE,
            source_kind=SOURCE_TYPE,
            source_event_id=order.id,
            idempotency_key=f"fbs-order:{order.id}",
            seller_id=order.seller_id,
            seller_name_snapshot=getattr(getattr(order, "seller", None), "name", None),
            warehouse_id=order.warehouse_id,
            marketplace=order.marketplace,
            document_type="fbs_order",
            document_id=order.id,
            document_number_snapshot=str(order.wb_order_id),
            occurred_at=moment,
            item_quantity=quantity,
            lines=[line_input(getattr(order, "product", None), order.product_id, quantity)],
        )
    except OperationFactError:
        # Факт — это летопись, а не деньги: если он не записался, начисление всё
        # равно должно уйти, иначе работа склада молча станет бесплатной.
        logger.exception("operation fact for fbs order failed: order_id=%s", order.id)

    try:
        await record_operational_charge(
            session,
            tenant_id=order.tenant_id,
            seller_id=order.seller_id,
            source_type=SOURCE_TYPE,
            source_id=order.id,
            source="fbs",
            service_code=FBS_ORDER_SERVICE_CODE,
            quantity=Decimal(quantity),
            occurred_at=moment,
            performer_id=None,
            warehouse_id=order.warehouse_id,
        )
    except BillingLedgerError:
        logger.exception("fbs order charge failed: order_id=%s", order.id)
