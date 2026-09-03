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
import uuid
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
from app.models.product import Product
from app.models.seller import Seller
from app.services.billing_ledger_service import (
    PACKING_SERVICE_CODE,
    BillingLedgerError,
    product_billing_lines,
    record_operational_charge,
)
from app.services.operation_fact_service import OperationFactError, line_input, write_operation_fact

logger = logging.getLogger(__name__)

FBS_ORDER_SERVICE_CODE = "fbs_order"
CONFIRMED_STATUSES = frozenset({FBS_ORDER_STATUS_SORTED, FBS_ORDER_STATUS_DONE})
SOURCE_TYPE = "fbs_order"


async def _positions(session: AsyncSession, order: FbsOrder) -> list[tuple[uuid.UUID | None, int]]:
    """Позиции заказа: товар и количество.

    У Wildberries это одна штука одного товара, у Ozon в отправлении может быть
    несколько позиций.
    """
    rows = (
        await session.execute(
            select(FbsOrderProduct.product_id, FbsOrderProduct.quantity).where(
                FbsOrderProduct.order_id == order.id
            )
        )
    ).all()
    if rows:
        return [(row[0], int(row[1])) for row in rows]
    return [(order.product_id, 1)]


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
    positions = await _positions(session, order)
    quantity = sum(count for _, count in positions)

    # Связи заказа не трогаем через `order.seller` и `order.product`: заказы в
    # синхронизацию приходят голым запросом, ленивая подгрузка в асинхронном коде
    # бросает MissingGreenlet и роняет весь проход опроса статусов вместе с
    # блокировками на батч.
    seller_name = await session.scalar(
        select(Seller.name).where(Seller.id == order.seller_id)
    )
    product_ids = [product_id for product_id, _ in positions if product_id is not None]
    products: dict[uuid.UUID, Product] = {}
    if product_ids:
        products = {
            product.id: product
            for product in (
                await session.scalars(select(Product).where(Product.id.in_(product_ids)))
            ).all()
        }

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
            seller_name_snapshot=seller_name,
            warehouse_id=order.warehouse_id,
            marketplace=order.marketplace,
            document_type="fbs_order",
            document_id=order.id,
            document_number_snapshot=str(order.wb_order_id),
            occurred_at=moment,
            item_quantity=quantity,
            lines=[
                line_input(products.get(product_id) if product_id else None, product_id, count)
                for product_id, count in positions
            ],
        )
    except OperationFactError:
        # Факт — это летопись, а не деньги: если он не записался, начисление всё
        # равно должно уйти, иначе работа склада молча станет бесплатной.
        logger.exception("operation fact for fbs order failed: order_id=%s", order.id)

    try:
        # Упаковка идёт по тем же штукам, что и сборка заказа: заказ уехал —
        # значит он упакован. От событий упаковки и кнопки «всё упаковано»
        # начисление не зависит.
        for charged_service_code in (FBS_ORDER_SERVICE_CODE, PACKING_SERVICE_CODE):
            await record_operational_charge(
                session,
                tenant_id=order.tenant_id,
                seller_id=order.seller_id,
                source_type=SOURCE_TYPE,
                source_id=order.id,
                source="fbs",
                service_code=charged_service_code,
                quantity=Decimal(quantity),
                occurred_at=moment,
                performer_id=None,
                warehouse_id=order.warehouse_id,
                # Без строк ставка ищется только в старой таблице тарифов, а
                # матрица — единственный живой экран — пишет в новую:
                # начисление выходило с пустой суммой.
                lines=product_billing_lines(
                    (product_id, Decimal(count), {"fbs_order_id": str(order.id)})
                    for product_id, count in positions
                    if product_id is not None
                ),
            )
    except BillingLedgerError:
        logger.exception("fbs order charge failed: order_id=%s", order.id)
