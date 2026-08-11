"""FBS post-delivery tracking: sync in-delivery supplies and partial acceptance summary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_DONE,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.services.wb_marketplace_orders_service import (
    WbMarketplaceOrdersError,
    _apply_wb_status_to_order,
    _supplier_status_from_row,
    _wb_status_from_row,
)
from app.services.wildberries_client import (
    WildberriesClientError,
    fetch_marketplace_orders_status,
)
from app.services.wildberries_credentials_service import (
    _seller_in_tenant,
    get_decrypted_marketplace_token,
)
from app.services.wildberries_fbs_client import split_marketplace_order_id_batches

TRACKING_STATUS_ACCEPTED = "accepted"
TRACKING_STATUS_SORTED = "sorted"
TRACKING_STATUS_PARTIALLY_REJECTED = "partially_rejected"
TRACKING_STATUS_CANCELLED = "cancelled"
TRACKING_STATUS_RETRY_REQUIRED = "retry_required"
TRACKING_STATUS_DONE = "done"
TRACKING_STATUS_IN_PROGRESS = "in_progress"

WB_REJECT_REASONS: dict[str, str] = {
    "declined_by_client": "Покупатель отменил заказ.",
    "cancelled_by_client": "Заказ отменён покупателем.",
    "defect": "Брак при приёмке маркетплейсом.",
}

TERMINAL_ORDER_STATUSES = frozenset(
    {
        FBS_ORDER_STATUS_DONE,
        FBS_ORDER_STATUS_CANCELLED,
        FBS_ORDER_STATUS_SORTED,
        FBS_ORDER_STATUS_DEFECT,
    }
)

STALE_SYNC_MULTIPLIER = 2


class FbsTrackingError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TrackingSyncResult:
    orders_updated: int
    supply_status: str


@dataclass(frozen=True)
class InDeliverySyncResult:
    supplies_synced: int
    orders_updated: int


def order_tracking_label(order: FbsOrder) -> str:
    if order.status == FBS_ORDER_STATUS_DONE:
        return TRACKING_STATUS_DONE
    if order.status == FBS_ORDER_STATUS_CANCELLED:
        return TRACKING_STATUS_CANCELLED
    if order.status == FBS_ORDER_STATUS_DEFECT:
        return TRACKING_STATUS_PARTIALLY_REJECTED
    if order.status == FBS_ORDER_STATUS_SORTED:
        return TRACKING_STATUS_ACCEPTED
    wb = (order.wb_status or "").strip().lower()
    if order.status == FBS_ORDER_STATUS_IN_DELIVERY and wb == "waiting":
        return TRACKING_STATUS_ACCEPTED
    return TRACKING_STATUS_IN_PROGRESS


def compute_supply_tracking_state(
    supply: FbsSupply,
    orders: list[FbsOrder],
) -> str:
    _ = supply
    if not orders:
        return TRACKING_STATUS_IN_PROGRESS
    labels = {order_tracking_label(order) for order in orders}
    if TRACKING_STATUS_PARTIALLY_REJECTED in labels or TRACKING_STATUS_CANCELLED in labels:
        if TRACKING_STATUS_ACCEPTED in labels or TRACKING_STATUS_DONE in labels:
            return TRACKING_STATUS_PARTIALLY_REJECTED
        if TRACKING_STATUS_CANCELLED in labels:
            return TRACKING_STATUS_CANCELLED
        return TRACKING_STATUS_PARTIALLY_REJECTED
    if TRACKING_STATUS_DONE in labels and len(labels) > 1:
        return TRACKING_STATUS_PARTIALLY_REJECTED
    if labels == {TRACKING_STATUS_DONE}:
        return TRACKING_STATUS_DONE
    if labels <= {TRACKING_STATUS_ACCEPTED, TRACKING_STATUS_SORTED, TRACKING_STATUS_DONE}:
        return TRACKING_STATUS_ACCEPTED
    return TRACKING_STATUS_IN_PROGRESS


def _reject_reason(order: FbsOrder) -> str:
    wb = (order.wb_status or "").strip().lower()
    if order.status == FBS_ORDER_STATUS_DEFECT:
        return WB_REJECT_REASONS["defect"]
    return WB_REJECT_REASONS.get(wb, "Отказ маркетплейса.")


def _remaining_deadline_iso(order: FbsOrder, server_now: datetime) -> str | None:
    if order.status in TERMINAL_ORDER_STATUSES and order.status != FBS_ORDER_STATUS_IN_DELIVERY:
        return None
    return order.deadline_at.isoformat()


def build_partial_rejection_summary(
    orders: list[FbsOrder],
    *,
    server_now: datetime | None = None,
) -> dict[str, Any]:
    _ = server_now
    accepted_orders: list[dict[str, Any]] = []
    rejected_orders: list[dict[str, Any]] = []
    for order in orders:
        label = order_tracking_label(order)
        row = {
            "order_id": str(order.id),
            "wb_order_id": int(order.wb_order_id),
            "tracking_label": label,
            "wb_status": order.wb_status,
            "local_status": order.status,
            "reason": _reject_reason(order) if label in {
                TRACKING_STATUS_PARTIALLY_REJECTED,
                TRACKING_STATUS_CANCELLED,
            } else None,
            "remaining_deadline": order.deadline_at.isoformat(),
        }
        if label in {TRACKING_STATUS_PARTIALLY_REJECTED, TRACKING_STATUS_CANCELLED}:
            rejected_orders.append(row)
        else:
            accepted_orders.append(row)
    return {
        "accepted_orders": accepted_orders,
        "rejected_orders": rejected_orders,
    }


def build_tracking_summary(
    supply: FbsSupply,
    orders: list[FbsOrder],
    *,
    server_now: datetime | None = None,
) -> dict[str, Any]:
    now = server_now or datetime.now(tz=UTC)
    status = compute_supply_tracking_state(supply, orders)
    return {
        "status": status,
        "orders": [
            {
                "order_id": str(order.id),
                "wb_order_id": int(order.wb_order_id),
                "tracking_label": order_tracking_label(order),
                "wb_status": order.wb_status,
                "local_status": order.status,
            }
            for order in orders
        ],
        "last_wb_sync_at": (
            supply.last_wb_sync_at.isoformat() if supply.last_wb_sync_at else None
        ),
        "checked_at": now.isoformat(),
    }


def is_tracking_sync_stale(
    last_wb_sync_at: datetime | None,
    *,
    server_now: datetime | None = None,
) -> bool:
    if last_wb_sync_at is None:
        return True
    now = server_now or datetime.now(tz=UTC)
    sync_at = last_wb_sync_at
    if sync_at.tzinfo is None:
        sync_at = sync_at.replace(tzinfo=UTC)
    age = (now - sync_at).total_seconds()
    return age > settings.fbs_statuses_sync_interval_sec * STALE_SYNC_MULTIPLIER


async def _resolve_marketplace_api_token(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> str:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsTrackingError("seller_not_found")
    token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if not token:
        raise FbsTrackingError("missing_marketplace_token")
    return token


async def _sync_supply_orders_from_wb(
    session: AsyncSession,
    supply: FbsSupply,
    http_client: httpx.AsyncClient,
    token: str,
) -> int:
    orders = list(supply.orders)
    if not orders:
        supply.last_wb_sync_at = datetime.now(tz=UTC)
        return 0

    processed = 0
    wb_ids = [int(order.wb_order_id) for order in orders]
    for batch in split_marketplace_order_id_batches(wb_ids):
        try:
            status_rows = await fetch_marketplace_orders_status(
                http_client,
                api_token=token,
                order_ids=batch,
            )
        except WildberriesClientError as exc:
            suffix = f"_{exc.status_code}" if exc.status_code else ""
            raise FbsTrackingError(f"wb_{exc.code}{suffix}") from exc

        by_id = {
            int(row["id"]): row for row in status_rows if row.get("id") is not None
        }
        for order in orders:
            if int(order.wb_order_id) not in batch:
                continue
            row = by_id.get(int(order.wb_order_id))
            if row is None:
                continue
            wb_status = _wb_status_from_row(row)
            supplier_status = _supplier_status_from_row(row)
            if wb_status is None and supplier_status is None:
                continue
            await _apply_wb_status_to_order(
                session,
                order,
                wb_status,
                supplier_status=supplier_status,
            )
            order.last_wb_sync_at = datetime.now(tz=UTC)
            processed += 1

    supply.last_wb_sync_at = datetime.now(tz=UTC)
    await _maybe_complete_supply(session, supply)
    await session.flush()
    return processed


async def _maybe_complete_supply(session: AsyncSession, supply: FbsSupply) -> None:
    if not supply.orders:
        return
    if all(order.status in TERMINAL_ORDER_STATUSES for order in supply.orders):
        supply.status = FBS_SUPPLY_STATUS_DONE


async def sync_supply_tracking(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    supply_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> TrackingSyncResult:
    stmt = (
        select(FbsSupply)
        .where(FbsSupply.id == supply_id, FbsSupply.tenant_id == tenant_id)
        .options(selectinload(FbsSupply.orders))
        .with_for_update()
    )
    result = await session.execute(stmt)
    supply = result.scalar_one_or_none()
    if supply is None:
        raise FbsTrackingError("supply_not_found")
    if supply.status != FBS_SUPPLY_STATUS_IN_DELIVERY:
        raise FbsTrackingError("supply_not_in_delivery")

    token = await _resolve_marketplace_api_token(session, tenant_id, supply.seller_id)
    try:
        updated = await _sync_supply_orders_from_wb(
            session, supply, http_client, token
        )
    except FbsTrackingError:
        raise
    except WbMarketplaceOrdersError as exc:
        raise FbsTrackingError(exc.code) from exc

    return TrackingSyncResult(orders_updated=updated, supply_status=supply.status)


async def sync_in_delivery_supplies(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> InDeliverySyncResult:
    stmt = (
        select(FbsSupply)
        .where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.status == FBS_SUPPLY_STATUS_IN_DELIVERY,
        )
        .options(selectinload(FbsSupply.orders))
        .order_by(FbsSupply.delivered_at.asc())
    )
    supplies = list((await session.execute(stmt)).scalars().all())
    supplies_synced = 0
    orders_updated = 0
    for supply in supplies:
        try:
            result = await sync_supply_tracking(
                session, tenant_id, supply.id, http_client
            )
            supplies_synced += 1
            orders_updated += result.orders_updated
        except FbsTrackingError:
            continue
    return InDeliverySyncResult(
        supplies_synced=supplies_synced,
        orders_updated=orders_updated,
    )


async def sync_in_delivery_supplies_for_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
) -> int:
    result = await sync_in_delivery_supplies(
        session, tenant_id, seller_id, http_client
    )
    return result.orders_updated
