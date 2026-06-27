from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_AVAILABLE, MarkingPool
from app.models.notification import RECIPIENT_TYPE_SELLER, SEVERITY_CRITICAL
from app.models.tenant import Tenant
from app.services import marking_code_service as mc_svc
from app.services.notification_service import NotificationRecipient, notify

NOTIFICATION_TYPE_LOW_STOCK = "marking_low_stock"
_DEDUP_HOURS = 24


def _is_low_stock_breach(
    pool: MarkingPool,
    *,
    available: int,
    forecast_days: float | None,
) -> bool:
    if pool.low_stock_threshold is not None and available < pool.low_stock_threshold:
        return True
    return (
        pool.forecast_days_threshold is not None
        and forecast_days is not None
        and forecast_days < float(pool.forecast_days_threshold)
    )


async def _recent_low_stock_notification_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    pool_id: uuid.UUID,
) -> bool:
    from app.models.notification import Notification

    cutoff = datetime.now(UTC) - timedelta(hours=_DEDUP_HOURS)
    stmt = select(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_type == RECIPIENT_TYPE_SELLER,
        Notification.recipient_id == str(seller_id),
        Notification.type == NOTIFICATION_TYPE_LOW_STOCK,
        Notification.created_at >= cutoff,
    )
    for row in (await session.execute(stmt)).scalars():
        payload = row.payload_json or {}
        if payload.get("pool_id") == str(pool_id):
            return True
    return False


async def run_marking_low_stock_for_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> int:
    pools = list(
        (
            await session.execute(
                select(MarkingPool).where(MarkingPool.tenant_id == tenant_id)
            )
        ).scalars().all()
    )
    if not pools:
        return 0
    pool_ids = [p.id for p in pools]
    counts = await mc_svc._pool_status_counts(
        session, tenant_id, seller_id=None, pool_ids=pool_ids
    )
    consumption_map = await mc_svc._pool_consumption_7d_batch(
        session, tenant_id, pool_ids
    )
    sent = 0
    for pool in pools:
        pool_counts = counts.get(pool.id, {})
        available = mc_svc._status_count(pool_counts, STATUS_AVAILABLE)
        consumption_7d = consumption_map.get(pool.id, 0)
        forecast_days = mc_svc.compute_forecast_days(available, consumption_7d)
        if not _is_low_stock_breach(pool, available=available, forecast_days=forecast_days):
            continue
        if await _recent_low_stock_notification_exists(
            session, tenant_id, pool.seller_id, pool.id
        ):
            continue
        forecast_label = f"{forecast_days} д" if forecast_days is not None else "—"
        await notify(
            session,
            tenant_id,
            NotificationRecipient(RECIPIENT_TYPE_SELLER, str(pool.seller_id)),
            type=NOTIFICATION_TYPE_LOW_STOCK,
            severity=SEVERITY_CRITICAL,
            title=f"Мало кодов: {pool.title}",
            body=(
                f"Доступно {available}, прогноз {forecast_label}. "
                "Догрузите коды в пул."
            ),
            link="/app/seller/honest-sign",
            payload={"pool_id": str(pool.id), "gtin": pool.gtin},
        )
        sent += 1
    if sent:
        await session.commit()
    return sent


async def run_marking_low_stock_all_tenants() -> int:
    total = 0
    async with SessionLocal() as session:
        tenant_ids = list(
            (await session.execute(select(Tenant.id))).scalars().all()
        )
    for tenant_id in tenant_ids:
        async with SessionLocal() as session:
            total += await run_marking_low_stock_for_tenant(session, tenant_id)
    return total
