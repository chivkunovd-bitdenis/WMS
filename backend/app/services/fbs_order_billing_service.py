"""Тарификация сборки заказов FBS.

Начисляем при подтверждённой передаче поставки маркетплейсу. Сам по себе
импортированный статус WB, включая `sorted` и `done`, не доказывает передачу
через WMS. Повторное подтверждение использует сохранённую дату передачи.

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
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
    FbsOrderProduct,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.product import Product
from app.models.seller import Seller
from app.services.billing_ledger_service import (
    PACKING_SERVICE_CODE,
    BillingLedgerError,
    product_billing_lines,
    record_operational_charge,
)
from app.services.marketplace_scope import order_display_number
from app.services.operation_fact_service import OperationFactError, line_input, write_operation_fact

logger = logging.getLogger(__name__)

FBS_ORDER_SERVICE_CODE = "fbs_order"
CONFIRMED_STATUSES = frozenset(
    {FBS_ORDER_STATUS_IN_DELIVERY, FBS_ORDER_STATUS_SORTED, FBS_ORDER_STATUS_DONE}
)
SOURCE_TYPE = "fbs_order"


async def confirmed_order_handover_dates(
    session: AsyncSession, tenant_id: uuid.UUID, orders: list[FbsOrder]
) -> dict[uuid.UUID, datetime]:
    """Persisted successful handovers, never an imported order status/date."""
    own_orders = [order for order in orders if order.tenant_id == tenant_id]
    if not own_orders:
        return {}
    by_id = {order.id: order for order in own_orders}
    operations = list(await session.scalars(
        select(FbsWbOperation).where(
            FbsWbOperation.tenant_id == tenant_id,
            FbsWbOperation.seller_id.in_(
                {order.seller_id for order in own_orders if order.seller_id}
            ),
            FbsWbOperation.operation_kind == "supply_deliver",
            FbsWbOperation.state == "confirmed",
            FbsWbOperation.local_entity_type == "fbs_supply",
            FbsWbOperation.confirmed_at.is_not(None),
        )
    ))
    supply_ids = {order.supply_id for order in own_orders if order.supply_id is not None}
    supply_ids.update(op.local_entity_id for op in operations if op.local_entity_id is not None)
    supplies = {
        supply.id: supply
        for supply in await session.scalars(
            select(FbsSupply).where(
                FbsSupply.tenant_id == tenant_id,
                FbsSupply.id.in_(supply_ids),
            )
        )
    }
    result: dict[uuid.UUID, datetime] = {}

    def remember(order: FbsOrder, moment: datetime) -> None:
        moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        result[order.id] = min(result.get(order.id, moment), moment)

    for order in own_orders:
        supply = supplies.get(order.supply_id) if order.supply_id else None
        if (
            supply is not None
            and supply.seller_id == order.seller_id
            and supply.marketplace == order.marketplace
            and supply.delivered_at is not None
        ):
            remember(order, supply.delivered_at)
    operation_by_id = {op.id: op for op in operations}
    ledger_orders: dict[uuid.UUID, list[uuid.UUID]] = {}
    if operation_by_id:
        for op_id, order_id in await session.execute(
            select(
                FbsShipmentReversalLedger.wb_operation_id,
                FbsShipmentReversalLedger.fbs_order_id,
            )
            .where(
                FbsShipmentReversalLedger.tenant_id == tenant_id,
                FbsShipmentReversalLedger.fbs_order_id.in_(by_id),
                FbsShipmentReversalLedger.wb_operation_id.in_(operation_by_id),
            )
        ):
            ledger_orders.setdefault(op_id, []).append(order_id)
    proven_orders: set[uuid.UUID] = set()
    for op in operations:
        summary = op.request_summary_json or {}
        checkpoint = summary.get("checkpoint_source_plan")
        # Source resolutions are only the mapped write-off subset. Their absence
        # must not discard linked unmapped orders that were handed over too.
        raw_rows = checkpoint.get("resolutions", []) if isinstance(checkpoint, dict) else []
        candidate_ids = list(ledger_orders.get(op.id, []))
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if isinstance(row, dict):
                    try:
                        candidate_ids.append(uuid.UUID(str(row.get("fbs_order_id"))))
                    except ValueError:
                        continue
        for order_id in candidate_ids:
            candidate = by_id.get(order_id)
            supply = supplies.get(op.local_entity_id) if op.local_entity_id else None
            if (
                candidate is not None and candidate.seller_id == op.seller_id
                and (supply is None or supply.marketplace == candidate.marketplace)
                and op.confirmed_at is not None
            ):
                # Confirmed operation is stronger evidence than a mutable link.
                if candidate.id not in proven_orders:
                    result.pop(candidate.id, None)
                    remember(candidate, op.confirmed_at)
                    proven_orders.add(candidate.id)
                else:
                    remember(candidate, op.confirmed_at)
    return result


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


def order_work_moment(order: FbsOrder) -> datetime:
    """Когда склад сделал работу по заказу, а не когда мы об этом узнали.

    Раньше здесь стоял момент обработки, и это тихо ломало деньги: опрос
    статусов приносит подтверждения WB пачками, в том числе по заказам
    двухнедельной давности, — и вся плата за две недели падала одним днём. На
    боевой базе так получилось 1577 записей «Империи ФФ», все датированные
    одним числом.

    Порядок источников: когда упаковали, иначе когда подобрали, иначе когда
    заказ появился у маркетплейса. Первые два — сама работа склада, третий
    заполнен всегда и отличается от неё на день-два.
    """
    for moment in (order.packed_at, order.picked_at, order.created_at_wb):
        if moment is not None:
            return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return datetime.now(UTC)


async def record_fbs_order_confirmed(
    session: AsyncSession,
    order: FbsOrder,
    *,
    occurred_at: datetime | None = None,
    confirmed_handover_at: datetime | None = None,
) -> None:
    """Записать факт и начисление за собранный заказ. Повтор безопасен."""
    if order.status not in CONFIRMED_STATUSES:
        return
    # Только внутренний путь подтверждённой передачи вправе начислить раньше
    # sorted/done; импорт внешнего in_delivery сам по себе недостаточен.
    if order.status == FBS_ORDER_STATUS_IN_DELIVERY and confirmed_handover_at is None:
        return
    if order.seller_id is None:
        return
    handover_at = confirmed_handover_at or (
        await confirmed_order_handover_dates(session, order.tenant_id, [order])
    ).get(order.id)
    if order.marketplace == "wb":
        if handover_at is None:
            return
        moment = handover_at
    else:
        # WMS-406 changes WB; retain Ozon's existing confirmed-status contract.
        moment = confirmed_handover_at or occurred_at or handover_at or order_work_moment(order)
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
            # Номер так, как его называет маркетплейс заказа: у Ozon в
            # `wb_order_id` лежит синтезированный отрицательный хеш, по которому
            # заказ не найти ни у нас, ни в кабинете.
            document_number_snapshot=order_display_number(order),
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
                respect_billing_start=False,
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


async def charge_handed_over_orders(
    session: AsyncSession, orders: list[FbsOrder], *, occurred_at: datetime
) -> None:
    """Начислить после успешной передачи, не откатывая её при ошибке денег."""
    for order in orders:
        order_id = order.id
        try:
            async with session.begin_nested():
                await record_fbs_order_confirmed(
                    session, order, confirmed_handover_at=occurred_at
                )
        except Exception:
            logger.exception("fbs handover charge skipped: order_id=%s", order_id)
