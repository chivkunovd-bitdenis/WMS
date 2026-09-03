"""FBS order cancellation and status sync helpers."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
)
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_supply import FbsSupply
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT
from app.services import inventory_service as inv_svc
from app.services.fbs_shipment_source_service import reversal_source_from_ledger
from app.services.marketplace_scope import is_wildberries, wrong_marketplace_message
from app.services.wb_marketplace_orders_service import (
    WbMarketplaceOrdersError,
    _release_reservation,
    _resolve_marketplace_api_token,
    sync_order_statuses,
)
from app.services.wildberries_client import (
    WildberriesClientError,
    cancel_marketplace_order,
)
from app.services.wildberries_errors import (
    log_wb_client_error,
    wb_error_context,
    wb_error_ref,
    wb_operator_message,
)

logger = logging.getLogger(__name__)

NON_CANCELLABLE_STATUSES = frozenset(
    {
        FBS_ORDER_STATUS_IN_DELIVERY,
        FBS_ORDER_STATUS_DONE,
        FBS_ORDER_STATUS_SORTED,
        FBS_ORDER_STATUS_DEFECT,
    }
)

# WB-статус поставщика "собрано и передано". Как только он появился на заказе,
# посылка физически уехала на приёмку WB — вернуться она может только через
# отдельный документ возврата (в системе пока нет), а не автоматическим
# сторнированием списания.
SUPPLIER_STATUS_COMPLETE = "complete"


class FbsCancellationError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        super().__init__(code)


async def reverse_fbs_shipment_if_needed(
    session: AsyncSession,
    order: FbsOrder,
    *,
    actor_user_id: uuid.UUID | None = None,
    skip_if_supplier_complete: bool = True,
) -> bool:
    """Reverse one packed physical unit exactly once; caller owns the order lock.

    `skip_if_supplier_complete` — параметр, а не жёстко зашитая проверка внутри,
    потому что у функции два вызывающих (ручная отмена оператором и обработка
    статусов от WB) и им может понадобиться разное поведение в будущем. Сейчас
    оба вызова используют безопасное значение по умолчанию: если поставка уже
    передана WB (`FbsSupply.delivered_at` заполнен) либо WB ещё сообщает
    `supplier_status == "complete"`, возвращать штуку на склад нельзя, иначе
    остаток завышается на товар, которого на складе нет.
    """
    stmt = (
        select(FbsShipmentReversalLedger)
        .where(
            FbsShipmentReversalLedger.tenant_id == order.tenant_id,
            FbsShipmentReversalLedger.fbs_order_id == order.id,
        )
        .with_for_update()
    )
    ledger = (await session.execute(stmt)).scalar_one_or_none()
    if (
        ledger is None
        or ledger.shipment_movement_id is None
        or ledger.reversed_at is not None
    ):
        return False

    # Факт передачи поставки — надёжный признак того, что товар физически
    # покинул склад. `order.supplier_status` для этого недостаточен: WB после
    # передачи меняет его на `cancel`/`confirm`, и проверка только на
    # `complete` перестаёт срабатывать.
    supply_delivered = False
    if order.wb_supply_id:
        supply = (
            await session.execute(
                select(FbsSupply).where(
                    FbsSupply.tenant_id == order.tenant_id,
                    FbsSupply.wb_supply_id == order.wb_supply_id,
                )
            )
        ).scalar_one_or_none()
        supply_delivered = supply is not None and supply.delivered_at is not None

    supplier_status = (order.supplier_status or "").strip().lower()
    already_handed_over = (
        supply_delivered or supplier_status == SUPPLIER_STATUS_COMPLETE
    )
    if skip_if_supplier_complete and already_handed_over:
        # Посылка уже у WB — трогать склад нельзя. Помечаем запись журнала
        # обработанной без движения по складу (reversal_movement_id остаётся
        # пустым), иначе она будет пытаться вернуться на каждом следующем
        # обходе синка статусов.
        logger.warning(
            "fbs_reversal_skipped_after_handover order=%s supply=%s "
            "delivered=%s status=%s",
            order.wb_order_id,
            order.wb_supply_id,
            supply_delivered,
            supplier_status,
        )
        ledger.reversed_at = datetime.now(UTC)
        await session.flush()
        return False

    from app.services import stock_direction_service

    positions = list(ledger.ozon_positions_json or [])
    if not positions:
        source = reversal_source_from_ledger(ledger)
        positions = [
            {
                "product_id": str(source.product_id),
                "storage_location_id": str(source.storage_location_id),
                "container_kind": source.container_kind,
                "container_id": (
                    str(source.container_id) if source.container_id is not None else None
                ),
                "quantity": source.quantity,
            }
        ]
    reversal_movement = None
    for position in positions:
        product_id = uuid.UUID(str(position["product_id"]))
        storage_location_id = uuid.UUID(str(position["storage_location_id"]))
        container_kind = position.get("container_kind")
        container_id_raw = position.get("container_id")
        container_id = uuid.UUID(str(container_id_raw)) if container_id_raw else None
        quantity = int(str(position["quantity"]))
        movement = await inv_svc.record_movement_and_adjust_balance(
            session,
            tenant_id=order.tenant_id,
            product_id=product_id,
            storage_location_id=storage_location_id,
            quantity_delta=quantity,
            movement_type=MOVEMENT_TYPE_FBS_SHIPMENT,
            actor_user_id=actor_user_id,
            container_kind=container_kind,  # type: ignore[arg-type]
            container_id=container_id,
        )
        if reversal_movement is None:
            reversal_movement = movement
        await stock_direction_service.restore_fbs_pool(
            session,
            order.tenant_id,
            product_id,
            quantity,
        )
    ledger.reversed_at = datetime.now(UTC)
    await session.flush()
    ledger.reversal_movement_id = reversal_movement.id if reversal_movement is not None else None
    await session.flush()
    return True


def penalty_band_for_order(created_at_wb: datetime) -> str:
    """WB cancel penalty window band (logged only in MVP)."""
    now = datetime.now(tz=UTC)
    created = (
        created_at_wb if created_at_wb.tzinfo is not None else created_at_wb.replace(tzinfo=UTC)
    )
    hours = (now - created).total_seconds() / 3600.0
    if hours < 13:
        return "lt13"
    if hours < 18:
        return "13_18"
    if hours < 120:
        return "18_120"
    return "gt120"


async def cancel_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> FbsOrder:
    stmt = (
        select(FbsOrder)
        .where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    order = res.scalar_one_or_none()
    if order is None:
        raise FbsCancellationError("order_not_found")

    if order.status == FBS_ORDER_STATUS_CANCELLED:
        return order

    if order.status in NON_CANCELLABLE_STATUSES:
        raise FbsCancellationError("order_not_cancellable")

    # Отмена уходит настоящим PATCH в кабинет Wildberries и не смотрит на
    # маркетплейс заказа. У заказа Ozon `wb_order_id` — синтезированный
    # отрицательный хеш, и такой запрос ушёл бы в чужой кабинет с заведомо
    # несуществующим номером. Пока своей отмены для Ozon нет, останавливаемся
    # здесь: не отменить честнее, чем отменить не там.
    if not is_wildberries(order):
        raise FbsCancellationError(
            "marketplace_not_supported",
            message=wrong_marketplace_message(order, "Отмена заказа"),
        )

    band = penalty_band_for_order(order.created_at_wb)
    logger.info(
        "fbs_cancel_penalty_band order_id=%s wb_order_id=%s band=%s",
        order.id,
        order.wb_order_id,
        band,
    )

    try:
        api_token = await _resolve_marketplace_api_token(session, tenant_id, order.seller_id)
    except WbMarketplaceOrdersError as exc:
        raise FbsCancellationError(
            exc.code,
            message=exc.message,
            context=exc.context,
            retryable=exc.retryable,
        ) from exc

    try:
        await cancel_marketplace_order(
            http_client,
            api_token=api_token,
            order_id=int(order.wb_order_id),
        )
    except WildberriesClientError as exc:
        suffix = f"_{exc.status_code}" if exc.status_code else ""
        ref = wb_error_ref()
        log_wb_client_error(
            logger,
            "fbs order WB cancel failed",
            exc,
            tenant_id=tenant_id,
            seller_id=order.seller_id,
            local_entity_id=order.id,
            wb_object_id=order.wb_order_id,
            ref=ref,
        )
        raise FbsCancellationError(
            f"wb_{exc.code}{suffix}",
            message=wb_operator_message(exc),
            context=wb_error_context(
                exc,
                ref=ref,
                extra={"order_id": str(order.id), "wb_order_id": order.wb_order_id},
            ),
            retryable=exc.code == "transport_error",
        ) from exc

    order.status = FBS_ORDER_STATUS_CANCELLED
    order.wb_status = "cancelled"
    await reverse_fbs_shipment_if_needed(
        session,
        order,
        actor_user_id=actor_user_id,
    )
    from app.services.fbs_packaging_integration_service import (
        detach_cancelled_order_from_supply,
    )

    await detach_cancelled_order_from_supply(
        session,
        tenant_id,
        order,
        actor_user_id=actor_user_id,
    )
    await _release_reservation(session, order)
    await session.flush()
    return order


async def sync_seller_order_statuses(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
) -> int:
    try:
        api_token = await _resolve_marketplace_api_token(session, tenant_id, seller_id)
    except WbMarketplaceOrdersError as exc:
        raise FbsCancellationError(
            exc.code,
            message=exc.message,
            context=exc.context,
            retryable=exc.retryable,
        ) from exc
    try:
        updated = await sync_order_statuses(
            session,
            tenant_id,
            seller_id,
            http_client,
            api_token,
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return updated
    except WbMarketplaceOrdersError as exc:
        raise FbsCancellationError(
            exc.code,
            message=exc.message,
            context=exc.context,
            retryable=exc.retryable,
        ) from exc
