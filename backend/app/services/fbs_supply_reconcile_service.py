"""FBS supply WB operation journal and reconcile helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_FAILED,
    WB_OPERATION_STATE_PENDING,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services.wildberries_errors import WildberriesClientError
from app.services.wildberries_fbs_client import fetch_marketplace_supply_order_ids

OPERATION_KIND_SUPPLY_FROM_ORDERS = "supply_from_orders"
OPERATION_KIND_CARGO_PLACES_CREATE = "cargo_places_create"
OPERATION_KIND_CARGO_PLACES_DELETE = "cargo_places_delete"
OPERATION_KIND_SUPPLY_DELIVER = "supply_deliver"
WB_RECONCILE_NOT_DELIVERED = "not_delivered"


def request_hash_for_from_orders(
    *,
    name: str,
    order_ids: list[uuid.UUID],
    planned_delivery_type: str,
) -> str:
    payload = {
        "name": name,
        "order_ids": sorted(str(oid) for oid in order_ids),
        "planned_delivery_type": planned_delivery_type,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def get_operation_by_idempotency(
    session: AsyncSession,
    seller_id: uuid.UUID,
    idempotency_key: str,
    *,
    operation_kind: str = OPERATION_KIND_SUPPLY_FROM_ORDERS,
) -> FbsWbOperation | None:
    stmt = select(FbsWbOperation).where(
        FbsWbOperation.seller_id == seller_id,
        FbsWbOperation.operation_kind == operation_kind,
        FbsWbOperation.idempotency_key == idempotency_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def request_hash_for_cargo_places(
    *,
    supply_id: uuid.UUID,
    count: int,
    boxes: list[dict[str, Any]],
) -> str:
    payload = {
        "supply_id": str(supply_id),
        "count": count,
        "boxes": boxes,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def get_cargo_operation_by_idempotency(
    session: AsyncSession,
    seller_id: uuid.UUID,
    idempotency_key: str,
) -> FbsWbOperation | None:
    return await get_operation_by_idempotency(
        session,
        seller_id,
        idempotency_key,
        operation_kind=OPERATION_KIND_CARGO_PLACES_CREATE,
    )


def request_hash_for_cargo_places_delete(
    *,
    supply_id: uuid.UUID,
    wb_trbx_ids: list[str],
) -> str:
    payload = {
        "supply_id": str(supply_id),
        "wb_trbx_ids": sorted(wb_trbx_ids),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def get_cargo_delete_operation_by_idempotency(
    session: AsyncSession,
    seller_id: uuid.UUID,
    idempotency_key: str,
) -> FbsWbOperation | None:
    return await get_operation_by_idempotency(
        session,
        seller_id,
        idempotency_key,
        operation_kind=OPERATION_KIND_CARGO_PLACES_DELETE,
    )


async def create_pending_cargo_delete_operation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    request_summary: dict[str, Any],
    local_supply_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None = None,
) -> FbsWbOperation:
    op = FbsWbOperation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        operation_kind=OPERATION_KIND_CARGO_PLACES_DELETE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_summary_json=request_summary,
        local_entity_type="fbs_supply",
        local_entity_id=local_supply_id,
        state=WB_OPERATION_STATE_PENDING,
        created_by_user_id=created_by_user_id,
    )
    session.add(op)
    await session.flush()
    return op


async def mark_cargo_delete_operation_confirmed(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    wb_supply_id: str | None,
    local_supply_id: uuid.UUID,
    response_summary: dict[str, Any] | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_CONFIRMED
    operation.wb_object_id = wb_supply_id
    operation.wb_object_kind = "supply" if wb_supply_id is not None else None
    operation.local_entity_type = "fbs_supply"
    operation.local_entity_id = local_supply_id
    operation.confirmed_at = datetime.now(tz=UTC)
    operation.response_summary_json = response_summary
    operation.error_code = None
    operation.error_context_json = None
    await session.flush()


def request_hash_for_deliver(
    *,
    supply_id: uuid.UUID,
    confirmed_preflight_version: str | None,
) -> str:
    payload = {
        "supply_id": str(supply_id),
        "confirmed_preflight_version": confirmed_preflight_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


async def get_deliver_operation_by_idempotency(
    session: AsyncSession,
    seller_id: uuid.UUID,
    idempotency_key: str,
) -> FbsWbOperation | None:
    return await get_operation_by_idempotency(
        session,
        seller_id,
        idempotency_key,
        operation_kind=OPERATION_KIND_SUPPLY_DELIVER,
    )


async def get_active_deliver_operation_for_supply(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    local_supply_id: uuid.UUID,
) -> FbsWbOperation | None:
    """Find a delivery already in flight or confirmed for this WB supply.

    The browser may rotate its idempotency key after a local failure.  The
    external mutation is nevertheless unique per supply, so recovery must be
    anchored to the supply as well as to the client-provided key.
    """
    stmt = (
        select(FbsWbOperation)
        .where(
            FbsWbOperation.tenant_id == tenant_id,
            FbsWbOperation.seller_id == seller_id,
            FbsWbOperation.operation_kind == OPERATION_KIND_SUPPLY_DELIVER,
            FbsWbOperation.local_entity_type == "fbs_supply",
            FbsWbOperation.local_entity_id == local_supply_id,
            FbsWbOperation.state.in_(
                {
                    WB_OPERATION_STATE_PENDING,
                    WB_OPERATION_STATE_PENDING_CONFIRMATION,
                    WB_OPERATION_STATE_CONFIRMED,
                }
            ),
        )
        .order_by(FbsWbOperation.created_at.desc(), FbsWbOperation.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_deliver_operations_for_supply(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    local_supply_id: uuid.UUID,
) -> list[FbsWbOperation]:
    """Все попытки передачи этой поставки — в любом состоянии, от старых к новым.

    Отличие от `get_active_deliver_operation_for_supply` в том, что сюда
    попадают и отказавшие попытки. Именно они нужны повтору Ozon: в их журнале
    лежит снимок того, что уже необратимо сделано в кабинете, и без него повтор
    отправил бы собранные отправления второй раз.

    Отдаём весь список, а не «последнюю»: у `created_at` в SQLite разрешение —
    секунда, и две попытки в одну секунду становятся неразличимы, после чего
    «последняя» выбирается случайным UUID. Складом такое решать нельзя, поэтому
    вызывающий код складывает снимки всех попыток.
    """
    stmt = (
        select(FbsWbOperation)
        .where(
            FbsWbOperation.tenant_id == tenant_id,
            FbsWbOperation.seller_id == seller_id,
            FbsWbOperation.operation_kind == OPERATION_KIND_SUPPLY_DELIVER,
            FbsWbOperation.local_entity_type == "fbs_supply",
            FbsWbOperation.local_entity_id == local_supply_id,
        )
        .order_by(FbsWbOperation.created_at.asc(), FbsWbOperation.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_pending_deliver_operation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    local_supply_id: uuid.UUID,
    confirmed_preflight_version: str | None,
    created_by_user_id: uuid.UUID | None = None,
) -> FbsWbOperation:
    op = FbsWbOperation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        operation_kind=OPERATION_KIND_SUPPLY_DELIVER,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_summary_json={
            "supply_id": str(local_supply_id),
            "confirmed_preflight_version": confirmed_preflight_version,
        },
        local_entity_type="fbs_supply",
        local_entity_id=local_supply_id,
        state=WB_OPERATION_STATE_PENDING,
        created_by_user_id=created_by_user_id,
    )
    session.add(op)
    await session.flush()
    return op


async def mark_deliver_operation_confirmed(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    wb_supply_id: str | None,
    local_supply_id: uuid.UUID,
) -> None:
    operation.state = WB_OPERATION_STATE_CONFIRMED
    operation.wb_object_id = wb_supply_id
    operation.wb_object_kind = "supply" if wb_supply_id is not None else None
    operation.local_entity_type = "fbs_supply"
    operation.local_entity_id = local_supply_id
    operation.confirmed_at = datetime.now(tz=UTC)
    operation.error_code = None
    operation.error_context_json = None
    await session.flush()


async def create_pending_cargo_operation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    request_summary: dict[str, Any],
    local_supply_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None = None,
) -> FbsWbOperation:
    op = FbsWbOperation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        operation_kind=OPERATION_KIND_CARGO_PLACES_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_summary_json=request_summary,
        local_entity_type="fbs_supply",
        local_entity_id=local_supply_id,
        state=WB_OPERATION_STATE_PENDING,
        created_by_user_id=created_by_user_id,
    )
    session.add(op)
    await session.flush()
    return op


async def mark_cargo_operation_confirmed(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    wb_supply_id: str,
    local_supply_id: uuid.UUID,
    response_summary: dict[str, Any] | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_CONFIRMED
    operation.wb_object_id = wb_supply_id
    operation.wb_object_kind = "supply"
    operation.local_entity_type = "fbs_supply"
    operation.local_entity_id = local_supply_id
    operation.confirmed_at = datetime.now(tz=UTC)
    operation.response_summary_json = response_summary
    operation.error_code = None
    operation.error_context_json = None
    await session.flush()


async def create_pending_operation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
    request_summary: dict[str, Any],
    created_by_user_id: uuid.UUID | None = None,
) -> FbsWbOperation:
    op = FbsWbOperation(
        tenant_id=tenant_id,
        seller_id=seller_id,
        operation_kind=OPERATION_KIND_SUPPLY_FROM_ORDERS,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_summary_json=request_summary,
        state=WB_OPERATION_STATE_PENDING,
        created_by_user_id=created_by_user_id,
    )
    session.add(op)
    await session.flush()
    return op


async def mark_operation_confirmed(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    wb_supply_id: str | None,
    local_supply_id: uuid.UUID,
    response_summary: dict[str, Any] | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_CONFIRMED
    operation.wb_object_id = wb_supply_id
    operation.wb_object_kind = "supply" if wb_supply_id is not None else None
    operation.local_entity_type = "fbs_supply"
    operation.local_entity_id = local_supply_id
    operation.confirmed_at = datetime.now(tz=UTC)
    operation.response_summary_json = response_summary
    operation.error_code = None
    operation.error_context_json = None
    await session.flush()


async def mark_operation_failed(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    error_code: str,
    error_context: dict[str, Any] | None = None,
    wb_supply_id: str | None = None,
    local_supply_id: uuid.UUID | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_FAILED
    operation.error_code = error_code
    operation.error_context_json = error_context
    operation.failed_at = datetime.now(tz=UTC)
    if wb_supply_id is not None:
        operation.wb_object_id = wb_supply_id
        operation.wb_object_kind = "supply"
    if local_supply_id is not None:
        operation.local_entity_type = "fbs_supply"
        operation.local_entity_id = local_supply_id
    await session.flush()


async def mark_operation_pending_confirmation(
    session: AsyncSession,
    operation: FbsWbOperation,
    *,
    wb_supply_id: str,
    local_supply_id: uuid.UUID,
    error_code: str = "wb_timeout",
    error_context: dict[str, Any] | None = None,
) -> None:
    operation.state = WB_OPERATION_STATE_PENDING_CONFIRMATION
    operation.wb_object_id = wb_supply_id
    operation.wb_object_kind = "supply"
    operation.local_entity_type = "fbs_supply"
    operation.local_entity_id = local_supply_id
    operation.error_code = error_code
    operation.error_context_json = error_context
    await session.flush()


async def fetch_wb_supply_order_ids(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    wb_supply_id: str,
    expected_order_ids: list[int] | None = None,
) -> list[int]:
    if settings.e2e_mock_wb_marketplace_supplies:
        if settings.e2e_mock_wb_marketplace_supply_readback_error_once is not None:
            error_code = settings.e2e_mock_wb_marketplace_supply_readback_error_once
            settings.e2e_mock_wb_marketplace_supply_readback_error_once = None
            raise WildberriesClientError(error_code)
        return list(expected_order_ids or [])
    return await fetch_marketplace_supply_order_ids(
        http_client,
        api_token=api_token,
        supply_id=wb_supply_id,
    )


async def reconcile_supply_orders(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    wb_supply_id: str,
    expected_wb_order_ids: set[int],
) -> tuple[str, set[int]]:
    """Returns (state, confirmed_wb_order_ids). state: confirmed | pending_confirmation."""
    try:
        wb_ids = await fetch_wb_supply_order_ids(
            http_client,
            api_token=api_token,
            wb_supply_id=wb_supply_id,
            expected_order_ids=sorted(expected_wb_order_ids),
        )
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            return WB_OPERATION_STATE_PENDING_CONFIRMATION, set()
        raise
    confirmed = set(wb_ids)
    if expected_wb_order_ids <= confirmed:
        return WB_OPERATION_STATE_CONFIRMED, confirmed
    if confirmed:
        return WB_OPERATION_STATE_PENDING_CONFIRMATION, confirmed
    return WB_OPERATION_STATE_PENDING_CONFIRMATION, set()


async def reconcile_supply_delivered(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    wb_supply_id: str,
) -> str:
    """Returns confirmed | pending_confirmation based on WB supply.done flag."""
    from app.services.wildberries_client import fetch_marketplace_supply_details

    try:
        details = await fetch_marketplace_supply_details(
            http_client,
            api_token=api_token,
            supply_id=wb_supply_id,
        )
    except WildberriesClientError as exc:
        if exc.code == "transport_error":
            return WB_OPERATION_STATE_PENDING_CONFIRMATION
        raise
    if details.done:
        return WB_OPERATION_STATE_CONFIRMED
    return WB_RECONCILE_NOT_DELIVERED
