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
