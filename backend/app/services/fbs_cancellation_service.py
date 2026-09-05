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
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
)
from app.services.marketplace_provider import MarketplaceProviderError, provider_error_message
from app.services.marketplace_scope import (
    MARKETPLACE_OZON,
    is_wildberries,
    wrong_marketplace_message,
)
from app.services.ozon_fbs_process_service import (
    CANCEL_REASON_OUT_OF_STOCK,
    OzonFbsProcessError,
    cancel_posting,
)
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
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
    """Отмена не приходует товар: после проведения нужен документ возврата.

    Оставлена совместимая точка вызова для обработчиков WB/Ozon. До проведения
    физического движения нет, освобождение существующего резерва выполняется
    общей операцией остатков.
    """
    return False


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


async def _finish_local_cancellation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Локальная часть отмены — одна на все маркетплейсы.

    Сторнирование отгрузки, отцепление от поставки и снятие резерва работают с
    нашими таблицами и о маркетплейсе ничего не знают. Раньше этот блок был
    вписан в вайлдберрисовскую ветку, и озоновской отмене пришлось бы его
    повторить — то есть завести второе место, где легко забыть про резерв.
    """
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


# Отметка в `meta_details_json` заказа о том, что в кабинете Ozon отмена уже
# состоялась. Она и есть журнал сверки: отмена у Ozon необратима («восстановить
# заказ не получится»), а локальная часть — сторнирование, отцепление от
# поставки, снятие резерва — может упасть после неё. Без отметки повтор ушёл бы
# в кабинет второй раз, а без повтора WMS навсегда считал бы заказ активным.
OZON_CANCELLATION_KEY = "ozon_cancellation"


def ozon_cancelled_externally(order: FbsOrder) -> bool:
    details = order.meta_details_json or {}
    return isinstance(details.get(OZON_CANCELLATION_KEY), dict)


async def _cancel_ozon_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order: FbsOrder,
    *,
    reason_id: int | None,
    reason_message: str | None,
) -> None:
    """Отменить отправление в кабинете Ozon — до того, как отменим у себя.

    Порядок именно такой: сначала маркетплейс, потом мы. Если отменить сначала
    локально, а Ozon откажет, покупатель останется с активным заказом, которого
    на складе уже нет.

    Сразу после ответа Ozon факт отмены коммитится отдельно. Иначе он живёт
    только внутри открытой транзакции запроса, и падение локальной части
    стирает его вместе с ней: в кабинете заказ отменён, у нас активен, и найти
    расхождение нечем.

    Рубильник боевого транспорта проверяется явно. Без него выключенный Ozon
    отдал бы локальный фейк, тот вернул бы пустой ответ, и оператор получил бы
    «Ozon не подтвердил отмену» вместо честного «боевой транспорт не включён».
    """
    if ozon_cancelled_externally(order):
        # Кабинет уже отменил заказ в прошлой попытке; повторять необратимую
        # мутацию нельзя, доделываем только локальную часть.
        return
    if not ozon_live_api_enabled():
        raise FbsCancellationError(
            "ozon_live_cancel_blocked",
            message=(
                "Отмена в Ozon выключена настройкой: боевой транспорт Ozon не включён. "
                "Заказ не отменён ни в кабинете, ни у нас."
            ),
        )
    try:
        client_id, api_key = await MarketplaceAccountService(session).stored_credentials(
            tenant_id,
            order.seller_id,
        )
    except MarketplaceAccountError as exc:
        raise FbsCancellationError(exc.code, message="Нет доступа к кабинету Ozon.") from exc
    effective_reason = CANCEL_REASON_OUT_OF_STOCK if reason_id is None else reason_id
    try:
        await cancel_posting(
            build_ozon_provider(),
            client_id=client_id,
            api_key=api_key,
            posting_number=order.external_order_id or "",
            reason_id=effective_reason,
            reason_message=reason_message,
        )
    except OzonFbsProcessError as exc:
        raise FbsCancellationError(exc.code, message=exc.message) from exc
    except MarketplaceProviderError as exc:
        raise FbsCancellationError(
            exc.code,
            message=provider_error_message(exc),
            retryable=exc.status_code in {429, 500, 502, 503, 504},
        ) from exc
    details = dict(order.meta_details_json or {})
    details[OZON_CANCELLATION_KEY] = {
        "cancelled_at": datetime.now(UTC).isoformat(),
        "reason_id": effective_reason,
        "reason_message": (reason_message or "").strip() or None,
        "posting_number": order.external_order_id,
    }
    order.meta_details_json = details
    await session.commit()


async def _lock_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
) -> FbsOrder | None:
    stmt = (
        select(FbsOrder)
        .where(FbsOrder.id == order_id, FbsOrder.tenant_id == tenant_id)
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def cancel_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    actor_user_id: uuid.UUID | None,
    reason_id: int | None = None,
    reason_message: str | None = None,
) -> FbsOrder:
    """Отменить FBS-заказ в кабинете маркетплейса и у себя.

    `reason_id`/`reason_message` относятся только к Ozon: у него причина —
    обязательное поле метода отмены, и подходящих причин у отправления обычно
    несколько. Без параметра оставалась бы одна зашитая — «товар закончился», и
    упакованный заказ с браком уезжал бы в кабинет под чужой причиной. У WB
    метод отмены причину не принимает вовсе, поэтому там аргумент не участвует.
    """
    order = await _lock_order(session, tenant_id, order_id)
    if order is None:
        raise FbsCancellationError("order_not_found")

    if order.status == FBS_ORDER_STATUS_CANCELLED:
        return order

    if order.status in NON_CANCELLABLE_STATUSES:
        raise FbsCancellationError("order_not_cancellable")

    # Отмена уходит настоящим запросом в кабинет того маркетплейса, которому
    # принадлежит заказ. Раньше развилки здесь не было вовсе: озоновский заказ
    # уезжал PATCH-ом в чужой вайлдберрисовский кабинет с отрицательным хешем
    # вместо номера. Теперь у Ozon свой путь, а маркетплейс, которого мы не
    # умеем, по-прежнему останавливается: не отменить честнее, чем отменить не
    # там.
    if not is_wildberries(order):
        if getattr(order, "marketplace", None) == MARKETPLACE_OZON:
            await _cancel_ozon_order(
                session,
                tenant_id,
                order,
                reason_id=reason_id,
                reason_message=reason_message,
            )
            # Отметка об отмене в кабинете коммитится, а коммит снимает замок с
            # заказа. Берём его заново и перепроверяем: параллельная попытка
            # могла за это время доделать локальную часть, и повторять
            # сторнирование поверх неё нельзя.
            relocked = await _lock_order(session, tenant_id, order_id)
            if relocked is None:
                raise FbsCancellationError("order_not_found")
            order = relocked
            if order.status == FBS_ORDER_STATUS_CANCELLED:
                return order
            await _finish_local_cancellation(
                session,
                tenant_id,
                order,
                actor_user_id=actor_user_id,
            )
            return order
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

    await _finish_local_cancellation(session, tenant_id, order, actor_user_id=actor_user_id)
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
