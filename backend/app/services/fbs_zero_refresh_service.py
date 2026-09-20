"""Schedule WB zero refresh from its confirmation, independent of reconcile phase."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.services.marketplace_seller_lock_service import marketplace_seller_lock

logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task[None]] = set()


async def refresh_binding_zero_stocks(
    tenant_id: uuid.UUID, seller_id: uuid.UUID, binding_id: uuid.UUID,
) -> None:
    from app.services.fbs_stock_sync_service import sync_binding_stocks

    try:
        async with (
            SessionLocal() as session,
            httpx.AsyncClient() as client,
            AsyncSession(bind=session.bind) as lock_session,
            marketplace_seller_lock(
                lock_session, seller_id, "wb", wait_timeout_sec=30,
            ) as acquired,
        ):
            if not acquired:
                return
            binding = await session.get(FbsWarehouseBinding, binding_id)
            if binding is None or binding.marketplace != "wb":
                return
            await sync_binding_stocks(
                session, tenant_id, seller_id, binding, client, zero_refresh_only=True,
            )
    except Exception:
        # The normal reconcile cycle retries failures and recovers lost timers.
        logger.exception("WB zero refresh failed for binding %s", binding_id)


def schedule_binding_zero_refresh(
    tenant_id: uuid.UUID, seller_id: uuid.UUID, binding_id: uuid.UUID, due_at: datetime,
) -> None:
    """Queue only after confirmed readback; skipped passes create no extra timers."""
    try:
        if settings.celery_broker_url:
            from app.tasks.background_jobs import run_fbs_zero_refresh_task

            run_fbs_zero_refresh_task.apply_async(
                args=[str(tenant_id), str(seller_id), str(binding_id)], eta=due_at,
            )
            return
        loop = asyncio.get_running_loop()

        def dispatch() -> None:
            task = loop.create_task(refresh_binding_zero_stocks(tenant_id, seller_id, binding_id))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)

        loop.call_later(max(0.0, (due_at - datetime.now(UTC)).total_seconds()), dispatch)
    except Exception:
        logger.exception("Could not schedule WB zero refresh for binding %s", binding_id)
