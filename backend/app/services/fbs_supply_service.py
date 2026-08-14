# ruff: noqa: RUF001
"""FBS supply assembly — preflight, atomic from-orders, legacy add, stickers."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_NEW,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_PVZ,
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_SOURCE_WMS,
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DRAFT,
    FbsSupply,
)
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
)
from app.services.catalog_service import get_warehouse
from app.services.fbs_packaging_integration_service import create_packaging_task_for_supply
from app.services.fbs_print_asset_storage import decode_png_payload
from app.services.fbs_sticker_code_service import sticker_code_from_wb_row
from app.services.fbs_supply_reconcile_service import (
    create_pending_operation,
    get_operation_by_idempotency,
    mark_operation_confirmed,
    mark_operation_failed,
    mark_operation_pending_confirmation,
    reconcile_supply_orders,
    request_hash_for_from_orders,
)
from app.services.fbs_supply_validator_service import (
    FbsSupplyValidationError,
    SupplyPreflightResult,
    load_orders_for_validation,
    preflight_to_dict,
    validate_supply_composition,
)
from app.services.fbs_wb_seller_lock_service import wb_seller_lock
from app.services.fbs_workspace_service import get_supply_workspace
from app.services.wildberries_client import (
    WildberriesClientError,
    add_order_to_marketplace_supply,
    add_orders_to_marketplace_supply,
    consume_next_mock_marketplace_supply_add_error,
    create_marketplace_supply,
    fetch_marketplace_order_stickers,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_errors import (
    log_wb_client_error,
    wb_error_context,
    wb_error_ref,
    wb_operator_message,
)
from app.services.wildberries_fbs_client import split_marketplace_order_id_batches

logger = logging.getLogger(__name__)

_VALID_DELIVERY_TYPES = {FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_DELIVERY_TYPE_PVZ}


class FbsSupplyError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        context: dict[str, Any] | None = None,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or code
        self.context = context or {}
        self.retryable = retryable
        self.http_status = http_status
        super().__init__(code)


@dataclass(frozen=True)
class PickingListItem:
    article: str
    sku_code: str | None
    size: str | None
    product_name: str
    quantity: int


@dataclass(frozen=True)
class StickerMeta:
    order_id: uuid.UUID
    wb_order_id: int
    sticker_code: str | None
    sticker_file: str | None
    asset_id: uuid.UUID | None = None


async def _order_has_ready_sticker_asset(
    session: AsyncSession, tenant_id: uuid.UUID, order: FbsOrder
) -> bool:
    from app.services.fbs_print_asset_service import _asset_file_ready, _find_order_sticker_asset

    asset = await _find_order_sticker_asset(session, tenant_id, order.id)
    return asset is not None and _asset_file_ready(asset)


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def _fbs_supply_error_from_wb(
    exc: WildberriesClientError,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    local_entity_id: uuid.UUID | str | None = None,
    wb_supply_id: str | None = None,
    event: str,
    retryable: bool | None = None,
    http_status: int | None = None,
    extra_context: dict[str, Any] | None = None,
) -> FbsSupplyError:
    ref = wb_error_ref()
    log_wb_client_error(
        logger,
        event,
        exc,
        tenant_id=tenant_id,
        seller_id=seller_id,
        local_entity_id=local_entity_id,
        wb_object_id=wb_supply_id,
        ref=ref,
    )
    extra: dict[str, Any] = {}
    if wb_supply_id is not None:
        extra["wb_supply_id"] = wb_supply_id
    if local_entity_id is not None:
        extra["local_entity_id"] = str(local_entity_id)
    if extra_context:
        extra.update(extra_context)
    return FbsSupplyError(
        _wb_error_code(exc),
        message=wb_operator_message(exc),
        context=wb_error_context(exc, ref=ref, extra=extra),
        retryable=exc.code == "transport_error" if retryable is None else retryable,
        http_status=http_status
        or (504 if exc.code == "transport_error" else 502),
    )


async def _require_marketplace_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSupplyError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsSupplyError("missing_marketplace_token")
    return token


async def _get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = False,
) -> FbsSupply | None:
    stmt = select(FbsSupply).where(
        FbsSupply.id == supply_id,
        FbsSupply.tenant_id == tenant_id,
    )
    if with_orders:
        stmt = stmt.options(
            selectinload(FbsSupply.orders).selectinload(FbsOrder.product)
        )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _issue_context(validation: SupplyPreflightResult) -> dict[str, Any]:
    reasons = sorted({issue.code for issue in validation.issues})
    order_ids = sorted({str(issue.order_id) for issue in validation.issues})
    return {"order_ids": order_ids, "reasons": reasons}


async def preflight_supply_composition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    order_ids: list[uuid.UUID],
    *,
    planned_delivery_type: str,
) -> dict[str, Any]:
    try:
        result = await validate_supply_composition(
            session,
            tenant_id,
            order_ids,
            planned_delivery_type=planned_delivery_type,
        )
    except FbsSupplyValidationError as exc:
        raise FbsSupplyError(exc.code) from exc
    return preflight_to_dict(result)


async def _bind_orders_to_supply(
    session: AsyncSession,
    supply: FbsSupply,
    orders: list[FbsOrder],
) -> None:
    for order in orders:
        order.supply_id = supply.id
        order.status = FBS_ORDER_STATUS_IN_SUPPLY
    if orders:
        supply.cargo_type = orders[0].cargo_type
    await session.flush()


def _partial_from_orders_summary(
    orders: list[FbsOrder],
    *,
    confirmed_wb_order_ids: set[int],
) -> dict[str, Any]:
    accepted_orders: list[dict[str, Any]] = []
    rejected_orders: list[dict[str, Any]] = []
    for order in orders:
        row = {
            "order_id": str(order.id),
            "wb_order_id": int(order.wb_order_id),
            "tracking_label": (
                "accepted"
                if int(order.wb_order_id) in confirmed_wb_order_ids
                else "not_confirmed"
            ),
            "wb_status": order.wb_status,
            "local_status": order.status,
            "remaining_deadline": order.deadline_at.isoformat(),
        }
        if int(order.wb_order_id) in confirmed_wb_order_ids:
            accepted_orders.append(
                {
                    **row,
                    "reason": "WB подтвердил заказ в составе поставки.",
                }
            )
        else:
            rejected_orders.append(
                {
                    **row,
                    "reason": "WB не подтвердил заказ после сверки состава поставки.",
                }
            )
    return {
        "accepted_orders": accepted_orders,
        "rejected_orders": rejected_orders,
    }


async def _complete_partial_from_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    operation: Any,
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    wb_supply_id: str,
    confirmed_wb_order_ids: set[int],
) -> dict[str, Any] | None:
    accepted_orders = [
        order for order in orders if int(order.wb_order_id) in confirmed_wb_order_ids
    ]
    if not accepted_orders:
        return None
    await _bind_orders_to_supply(session, supply, accepted_orders)
    partial_summary = _partial_from_orders_summary(
        orders,
        confirmed_wb_order_ids={int(order.wb_order_id) for order in accepted_orders},
    )
    await mark_operation_confirmed(
        session,
        operation,
        wb_supply_id=wb_supply_id,
        local_supply_id=supply.id,
        response_summary={
            "partial_confirmation": True,
            "requested_wb_order_ids": sorted(int(order.wb_order_id) for order in orders),
            "accepted_wb_order_ids": sorted(
                int(order.wb_order_id) for order in accepted_orders
            ),
            "rejected_wb_order_ids": sorted(
                int(order.wb_order_id)
                for order in orders
                if int(order.wb_order_id) not in confirmed_wb_order_ids
            ),
            "partial_rejection": partial_summary,
        },
    )
    workspace = await get_supply_workspace(session, tenant_id, supply.id)
    workspace["partial_rejection"] = partial_summary
    return workspace


async def _execute_wb_batch_add(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    wb_supply_id: str,
    wb_order_ids: list[int],
) -> None:
    for batch in split_marketplace_order_id_batches(wb_order_ids):
        await add_orders_to_marketplace_supply(
            http_client,
            api_token=api_token,
            supply_id=wb_supply_id,
            order_ids=batch,
        )


async def create_supply_from_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    order_ids: list[uuid.UUID],
    planned_delivery_type: str,
    planned_destination: dict[str, Any] | None,
    idempotency_key: str,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    if not idempotency_key.strip():
        raise FbsSupplyError("missing_idempotency_key", http_status=400)
    if not order_ids:
        raise FbsSupplyError("empty_order_set", http_status=400)

    request_hash = request_hash_for_from_orders(
        name=name,
        order_ids=order_ids,
        planned_delivery_type=planned_delivery_type,
    )

    try:
        stub_orders = await load_orders_for_validation(
            session, tenant_id, order_ids, for_update=False
        )
    except FbsSupplyValidationError as exc:
        raise FbsSupplyError(exc.code) from exc

    seller_id = stub_orders[0].seller_id
    existing_op = await get_operation_by_idempotency(session, seller_id, idempotency_key)
    if existing_op is not None:
        if existing_op.request_hash and existing_op.request_hash != request_hash:
            raise FbsSupplyError(
                "idempotency_key_reused",
                message="Ключ идемпотентности уже использован с другими параметрами.",
                retryable=False,
                http_status=409,
            )
        return await _resume_from_orders_operation(
            session,
            tenant_id,
            existing_op,
            orders=list(stub_orders),
            http_client=http_client,
        )

    try:
        preview = await validate_supply_composition(
            session,
            tenant_id,
            order_ids,
            planned_delivery_type=planned_delivery_type,
        )
    except FbsSupplyValidationError as exc:
        raise FbsSupplyError(exc.code) from exc
    if not preview.compatible:
        raise FbsSupplyError(
            "order_incompatible",
            message="Заказ нельзя добавить в выбранную поставку.",
            context=_issue_context(preview),
            retryable=False,
            http_status=409,
        )

    locked = await validate_supply_composition(
        session,
        tenant_id,
        order_ids,
        planned_delivery_type=planned_delivery_type,
        for_update=True,
    )
    if not locked.compatible:
        raise FbsSupplyError(
            "order_incompatible",
            message="Заказ нельзя добавить в выбранную поставку.",
            context=_issue_context(locked),
            retryable=False,
            http_status=409,
        )

    orders = list(locked.orders)
    summary = locked.summary
    assert summary is not None
    token = await _require_marketplace_token(session, tenant_id, seller_id)
    async with wb_seller_lock(session, seller_id, wait_timeout_sec=15.0) as wb_lock_acquired:
        if not wb_lock_acquired:
            raise FbsSupplyError(
                "operation_in_progress",
                message="WB-синхронизация по селлеру ещё идёт — повторите через несколько секунд.",
                retryable=True,
                http_status=503,
            )
        operation = await create_pending_operation(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_summary={
                "name": name,
                "order_ids": [str(oid) for oid in order_ids],
                "planned_delivery_type": planned_delivery_type,
            },
        )

        wb_office_id = None
        dest_name = None
        dest_zone = None
        if planned_destination:
            office_raw = planned_destination.get("office_id")
            wb_office_id = int(office_raw) if office_raw is not None else None
            name_raw = planned_destination.get("name")
            dest_name = name_raw if isinstance(name_raw, str) else None
            zone_raw = planned_destination.get("zone")
            dest_zone = zone_raw if isinstance(zone_raw, str) else None

        supply = FbsSupply(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=summary.wms_warehouse_id,
            wb_supply_id=f"PENDING-{operation.id}",
            name=name,
            source=FBS_SUPPLY_SOURCE_WMS,
            status=FBS_SUPPLY_STATUS_DRAFT,
            delivery_type=planned_delivery_type,
            cargo_type=summary.cargo_type,
            wb_office_id=wb_office_id,
            planned_destination_office_id=wb_office_id,
            planned_destination_name=dest_name,
            planned_destination_zone=dest_zone,
        )
        session.add(supply)
        await session.flush()
        operation.local_entity_type = "fbs_supply"
        operation.local_entity_id = supply.id
        await session.flush()

        try:
            wb_row = await create_marketplace_supply(http_client, api_token=token, name=name)
        except WildberriesClientError as exc:
            error = _fbs_supply_error_from_wb(
                exc,
                tenant_id=tenant_id,
                seller_id=seller_id,
                local_entity_id=supply.id,
                event="fbs supply from-orders WB create failed",
            )
            await mark_operation_failed(
                session,
                operation,
                error_code=error.code,
                error_context=error.context,
                local_supply_id=supply.id,
            )
            raise error from exc

        wb_supply_id_raw = wb_row.get("id")
        if wb_supply_id_raw is None:
            await mark_operation_failed(session, operation, error_code="wb_invalid_response")
            raise FbsSupplyError("wb_invalid_response", http_status=502)
        wb_supply_id = str(wb_supply_id_raw)
        supply.wb_supply_id = wb_supply_id
        operation.wb_object_id = wb_supply_id
        operation.wb_object_kind = "supply"
        await session.flush()

        wb_order_ids = [int(order.wb_order_id) for order in orders]
        try:
            mock_error = (
                settings.e2e_mock_wb_marketplace_supply_add_error_once
                or consume_next_mock_marketplace_supply_add_error()
            )
            settings.e2e_mock_wb_marketplace_supply_add_error_once = None
            if mock_error is not None:
                if mock_error == "transport_error":
                    settings.e2e_mock_wb_marketplace_supply_readback_error_once = (
                        "transport_error"
                    )
                raise WildberriesClientError(mock_error)
            await _execute_wb_batch_add(
                http_client,
                api_token=token,
                wb_supply_id=wb_supply_id,
                wb_order_ids=wb_order_ids,
            )
        except WildberriesClientError as exc:
            if exc.code == "transport_error":
                try:
                    state, confirmed = await reconcile_supply_orders(
                        http_client,
                        api_token=token,
                        wb_supply_id=wb_supply_id,
                        expected_wb_order_ids=set(wb_order_ids),
                    )
                except WildberriesClientError as reconcile_exc:
                    if reconcile_exc.code != "transport_error":
                        error = _fbs_supply_error_from_wb(
                            reconcile_exc,
                            tenant_id=tenant_id,
                            seller_id=seller_id,
                            local_entity_id=supply.id,
                            wb_supply_id=wb_supply_id,
                            event="fbs supply from-orders WB reconcile failed",
                            retryable=False,
                            http_status=502,
                        )
                        await mark_operation_failed(
                            session,
                            operation,
                            error_code=error.code,
                            error_context=error.context,
                            wb_supply_id=wb_supply_id,
                            local_supply_id=supply.id,
                        )
                        raise error from reconcile_exc
                    state, confirmed = WB_OPERATION_STATE_PENDING_CONFIRMATION, set()
                if state == WB_OPERATION_STATE_CONFIRMED:
                    await _bind_orders_to_supply(session, supply, orders)
                    await mark_operation_confirmed(
                        session,
                        operation,
                        wb_supply_id=wb_supply_id,
                        local_supply_id=supply.id,
                        response_summary={"wb_order_ids": sorted(confirmed)},
                    )
                    return await get_supply_workspace(session, tenant_id, supply.id)
                await mark_operation_pending_confirmation(
                    session,
                    operation,
                    wb_supply_id=wb_supply_id,
                    local_supply_id=supply.id,
                    error_code="wb_timeout",
                    error_context={"wb_supply_id": wb_supply_id},
                )
                raise FbsSupplyError(
                    "wb_timeout",
                    message="WB не подтвердил состав поставки — повторите операцию.",
                    context={
                        "wb_supply_id": wb_supply_id,
                        "operation_state": "pending_confirmation",
                    },
                    retryable=True,
                    http_status=504,
                ) from exc
            error = _fbs_supply_error_from_wb(
                exc,
                tenant_id=tenant_id,
                seller_id=seller_id,
                local_entity_id=supply.id,
                wb_supply_id=wb_supply_id,
                event="fbs supply from-orders WB add-orders failed",
                retryable=False,
                http_status=502,
            )
            await mark_operation_failed(
                session,
                operation,
                error_code=error.code,
                error_context=error.context,
                wb_supply_id=wb_supply_id,
                local_supply_id=supply.id,
            )
            raise error from exc

        state, _confirmed = await reconcile_supply_orders(
            http_client,
            api_token=token,
            wb_supply_id=wb_supply_id,
            expected_wb_order_ids=set(wb_order_ids),
        )
        if state != WB_OPERATION_STATE_CONFIRMED:
            await mark_operation_pending_confirmation(
                session,
                operation,
                wb_supply_id=wb_supply_id,
                local_supply_id=supply.id,
            )
            raise FbsSupplyError(
                "wb_pending_confirmation",
                message="WB не подтвердил состав поставки — повторите операцию.",
                context={"wb_supply_id": wb_supply_id, "supply_id": str(supply.id)},
                retryable=True,
                http_status=504,
            )

        await _bind_orders_to_supply(session, supply, orders)
        await mark_operation_confirmed(
            session,
            operation,
            wb_supply_id=wb_supply_id,
            local_supply_id=supply.id,
            response_summary={"wb_order_ids": wb_order_ids},
        )
        return await get_supply_workspace(session, tenant_id, supply.id)


async def _resume_from_orders_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    operation: Any,
    *,
    orders: list[FbsOrder],
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    if operation.state == WB_OPERATION_STATE_FAILED:
        raise FbsSupplyError(
            operation.error_code or "operation_failed",
            message="Предыдущая попытка создания поставки завершилась ошибкой.",
            context=dict(operation.error_context_json or {}),
            retryable=False,
            http_status=502,
        )
    if operation.local_entity_id is None or operation.wb_object_id is None:
        raise FbsSupplyError(
            "operation_incomplete",
            message="Операция создания поставки не завершена.",
            retryable=True,
            http_status=504,
        )
    supply = await _get_supply(session, tenant_id, operation.local_entity_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    token = await _require_marketplace_token(session, tenant_id, operation.seller_id)
    wb_order_ids = [int(order.wb_order_id) for order in orders]
    if operation.state == WB_OPERATION_STATE_PENDING_CONFIRMATION:
        state, _confirmed = await reconcile_supply_orders(
            http_client,
            api_token=token,
            wb_supply_id=operation.wb_object_id,
            expected_wb_order_ids=set(wb_order_ids),
        )
        if state != WB_OPERATION_STATE_CONFIRMED:
            try:
                await _execute_wb_batch_add(
                    http_client,
                    api_token=token,
                    wb_supply_id=operation.wb_object_id,
                    wb_order_ids=wb_order_ids,
                )
            except WildberriesClientError as exc:
                if exc.code == "transport_error":
                    log_wb_client_error(
                        logger,
                        "fbs supply from-orders WB resume add-orders timeout",
                        exc,
                        tenant_id=tenant_id,
                        seller_id=operation.seller_id,
                        local_entity_id=supply.id,
                        wb_object_id=operation.wb_object_id,
                        ref=wb_error_ref(),
                    )
                    raise FbsSupplyError(
                        "wb_timeout",
                        message="WB не подтвердил состав поставки — повторите операцию.",
                        context={"wb_supply_id": operation.wb_object_id},
                        retryable=True,
                        http_status=504,
                    ) from exc
                raise _fbs_supply_error_from_wb(
                    exc,
                    tenant_id=tenant_id,
                    seller_id=operation.seller_id,
                    local_entity_id=supply.id,
                    wb_supply_id=operation.wb_object_id,
                    event="fbs supply from-orders WB resume add-orders failed",
                    retryable=False,
                    http_status=502,
                ) from exc
            state, _confirmed = await reconcile_supply_orders(
                http_client,
                api_token=token,
                wb_supply_id=operation.wb_object_id,
                expected_wb_order_ids=set(wb_order_ids),
            )
        if state != WB_OPERATION_STATE_CONFIRMED:
            raise FbsSupplyError(
                "wb_pending_confirmation",
                message="WB не подтвердил состав поставки — повторите операцию.",
                context={"wb_supply_id": operation.wb_object_id},
                retryable=True,
                http_status=504,
            )
        await _bind_orders_to_supply(session, supply, orders)
        await mark_operation_confirmed(
            session,
            operation,
            wb_supply_id=operation.wb_object_id,
            local_supply_id=supply.id,
        )
        return await get_supply_workspace(session, tenant_id, supply.id)

    if operation.state == WB_OPERATION_STATE_CONFIRMED:
        bound = {int(o.wb_order_id) for o in supply.orders}
        missing = [o for o in orders if int(o.wb_order_id) not in bound]
        if missing:
            await _bind_orders_to_supply(session, supply, missing)
        return await get_supply_workspace(session, tenant_id, supply.id)

    raise FbsSupplyError(
        "operation_in_progress",
        message="Операция создания поставки ещё выполняется.",
        retryable=True,
        http_status=503,
    )


async def start_supply_work(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    if not supply.orders:
        raise FbsSupplyError("supply_empty", http_status=400)
    await create_packaging_task_for_supply(session, tenant_id, supply_id)
    if supply.status == FBS_SUPPLY_STATUS_DRAFT:
        supply.status = FBS_SUPPLY_STATUS_ASSEMBLING
        for order in supply.orders:
            if order.status == FBS_ORDER_STATUS_IN_SUPPLY:
                order.status = FBS_ORDER_STATUS_ASSEMBLING
        await session.flush()
    if http_client is not None:
        await _request_order_stickers_for_picking(session, tenant_id, supply, http_client)
    return await get_supply_workspace(session, tenant_id, supply_id)


async def _request_order_stickers_for_picking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
) -> None:
    missing = [order.id for order in supply.orders if not order.sticker_code]
    if not missing:
        return
    try:
        from app.services.fbs_print_asset_service import (
            FbsPrintAssetError,
            request_supply_print_batch,
        )

        await request_supply_print_batch(
            session,
            tenant_id,
            supply.id,
            kind="order_sticker",
            order_ids=missing,
            retry_missing=True,
            http_client=http_client,
        )
    except FbsPrintAssetError as exc:
        logger.warning(
            "fbs supply start-work sticker prefetch skipped supply %s: %s",
            supply.id,
            exc.code,
        )


async def create_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    name: str,
    delivery_type: str,
    cargo_type: str | None = None,
    wb_office_id: int | None = None,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    if delivery_type not in _VALID_DELIVERY_TYPES:
        raise FbsSupplyError("invalid_delivery_type")
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsSupplyError("seller_not_found")
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise FbsSupplyError("warehouse_not_found")

    token = await _require_marketplace_token(session, tenant_id, seller_id)
    try:
        wb_row = await create_marketplace_supply(http_client, api_token=token, name=name)
    except WildberriesClientError as exc:
        raise _fbs_supply_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=seller_id,
            event="fbs supply legacy WB create failed",
        ) from exc

    wb_supply_id_raw = wb_row.get("id")
    if wb_supply_id_raw is None:
        raise FbsSupplyError("wb_invalid_response")
    wb_supply_id = str(wb_supply_id_raw)

    supply = FbsSupply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_supply_id=wb_supply_id,
        name=name,
        source=FBS_SUPPLY_SOURCE_WMS,
        status=FBS_SUPPLY_STATUS_DRAFT,
        delivery_type=delivery_type,
        cargo_type=cargo_type,
        wb_office_id=wb_office_id,
    )
    session.add(supply)
    await session.flush()
    return supply


async def get_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    *,
    with_orders: bool = True,
) -> FbsSupply:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=with_orders)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    return supply


async def add_order_to_supply(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    order_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> FbsSupply:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    if supply.status != FBS_SUPPLY_STATUS_DRAFT:
        raise FbsSupplyError("supply_not_editable")

    order_stmt = (
        select(FbsOrder)
        .where(
            FbsOrder.id == order_id,
            FbsOrder.tenant_id == tenant_id,
            FbsOrder.seller_id == supply.seller_id,
        )
        .with_for_update()
    )
    order_result = await session.execute(order_stmt)
    order = order_result.scalar_one_or_none()
    if order is None:
        raise FbsSupplyError("order_not_found")
    if order.warehouse_id is None:
        raise FbsSupplyError("order_warehouse_unmapped")
    if order.warehouse_id != supply.warehouse_id:
        raise FbsSupplyError("order_warehouse_mismatch")
    if order.supply_id is not None and order.supply_id != supply_id:
        raise FbsSupplyError("order_already_in_supply")
    if order.status != FBS_ORDER_STATUS_NEW:
        raise FbsSupplyError("order_bad_status")
    if (
        order.supplier_status is not None
        and order.supplier_status.strip().lower() != FBS_ORDER_STATUS_NEW
    ):
        raise FbsSupplyError("order_bad_status")

    token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
    try:
        await add_order_to_marketplace_supply(
            http_client,
            api_token=token,
            supply_id=supply.wb_supply_id,
            order_id=int(order.wb_order_id),
        )
    except WildberriesClientError as exc:
        raise _fbs_supply_error_from_wb(
            exc,
            tenant_id=tenant_id,
            seller_id=supply.seller_id,
            local_entity_id=supply.id,
            wb_supply_id=supply.wb_supply_id,
            event="fbs supply legacy WB add-order failed",
            extra_context={"wb_order_id": int(order.wb_order_id)},
        ) from exc

    order.supply_id = supply.id
    order.status = FBS_ORDER_STATUS_IN_SUPPLY
    await session.flush()
    await session.refresh(supply, attribute_names=["orders"])
    return supply


async def get_picking_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
) -> list[PickingListItem]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")

    groups: dict[tuple[str, str | None, str | None, str], int] = defaultdict(int)
    for order in supply.orders:
        product = order.product
        article = order.wb_article or (product.sku_code if product is not None else "") or ""
        sku_code = product.sku_code if product is not None else None
        size = product.wb_size if product is not None and product.wb_size else None
        product_name = product.name if product is not None else (order.wb_article or "Unknown")
        key = (article, sku_code, size, product_name)
        groups[key] += 1

    items = [
        PickingListItem(
            article=article,
            sku_code=sku_code,
            size=size,
            product_name=product_name,
            quantity=qty,
        )
        for (article, sku_code, size, product_name), qty in sorted(groups.items())
    ]
    return items


async def fetch_and_cache_stickers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    force: bool = False,
) -> list[StickerMeta]:
    supply = await _get_supply(session, tenant_id, supply_id, with_orders=True)
    if supply is None:
        raise FbsSupplyError("supply_not_found")
    if not supply.orders:
        return []

    orders_to_fetch = []
    for order in supply.orders:
        if force:
            orders_to_fetch.append(order)
            continue
        if order.sticker_file:
            continue
        if await _order_has_ready_sticker_asset(session, tenant_id, order):
            continue
        orders_to_fetch.append(order)
    if orders_to_fetch:
        token = await _require_marketplace_token(session, tenant_id, supply.seller_id)
        order_ids = [int(order.wb_order_id) for order in orders_to_fetch]
        try:
            sticker_rows = await fetch_marketplace_order_stickers(
                http_client,
                api_token=token,
                order_ids=order_ids,
            )
        except WildberriesClientError as exc:
            raise _fbs_supply_error_from_wb(
                exc,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                local_entity_id=supply.id,
                wb_supply_id=supply.wb_supply_id,
                event="fbs supply WB stickers failed",
                extra_context={"wb_order_ids": order_ids},
            ) from exc

        by_wb_id: dict[int, dict[str, Any]] = {}
        for row in sticker_rows:
            oid_raw = row.get("orderId") or row.get("order_id")
            if oid_raw is not None:
                by_wb_id[int(oid_raw)] = row

        fetched_at = datetime.now(tz=UTC)
        for order in orders_to_fetch:
            sticker_row = by_wb_id.get(int(order.wb_order_id))
            if sticker_row is None:
                raise FbsSupplyError("wb_stickers_incomplete")
            sticker_code = sticker_code_from_wb_row(sticker_row)
            png_bytes = decode_png_payload(sticker_row.get("file"))
            if png_bytes is None:
                raise FbsSupplyError("wb_stickers_incomplete")
            from app.services.fbs_print_asset_service import upsert_order_sticker_asset_from_bytes

            await upsert_order_sticker_asset_from_bytes(
                session,
                tenant_id=tenant_id,
                seller_id=supply.seller_id,
                supply_id=supply.id,
                order=order,
                png_bytes=png_bytes,
                sticker_code=sticker_code,
                fetched_at=fetched_at,
            )

        still_missing = [
            order
            for order in orders_to_fetch
            if not order.sticker_file and not order.sticker_code
        ]
        if still_missing:
            raise FbsSupplyError("wb_stickers_incomplete")

    await session.flush()
    from app.services.fbs_print_asset_service import _find_order_sticker_asset

    metas: list[StickerMeta] = []
    for order in supply.orders:
        asset = await _find_order_sticker_asset(session, tenant_id, order.id)
        metas.append(
            StickerMeta(
                order_id=order.id,
                wb_order_id=int(order.wb_order_id),
                sticker_code=order.sticker_code,
                sticker_file=order.sticker_file,
                asset_id=asset.id if asset is not None else None,
            )
        )
    return metas
