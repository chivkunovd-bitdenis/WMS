"""Event-driven publication of FBS availability to connected marketplaces.

WMS owns the number in the seller's cabinet: `PUT /api/v3/stocks/{warehouseId}` overwrites
whatever WB had. So every movement that changes availability — intake, shipment, write-off,
transfer, an FBS order reserve — has to be followed by a fresh publish, otherwise WB keeps
selling against a stale figure.

Publication is deliberately kept *outside* the movement transaction. It talks to an external
API over the network, and a slow or failing WB must never roll back a warehouse operation that
already happened physically. Callers therefore only register an intent
(`schedule_seller_stock_publish`); the actual work fires after the transaction commits.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import httpx
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.services.marketplace_seller_lock_service import marketplace_seller_lock

logger = logging.getLogger(__name__)

_PENDING_KEY = "fbs_stock_publish_pending"
_HOOKED_KEY = "fbs_stock_publish_hooked"


async def publish_seller_stocks_now(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> None:
    """Republish independently for every connected provider after movement commit."""
    from app.services.fbs_autopoll_service import (
        list_marketplace_poll_targets,
        sync_marketplace_stocks_for_target,
    )

    async with SessionLocal() as target_session:
        all_targets = await list_marketplace_poll_targets(target_session)
    targets = [
        target
        for target in all_targets
        if target.tenant_id == tenant_id and target.seller_id == seller_id
    ]

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            try:
                async with (
                    SessionLocal() as session,
                    AsyncSession(bind=session.bind) as lock_session,
                    marketplace_seller_lock(
                        lock_session, target.seller_id, target.marketplace,
                        wait_timeout_sec=30,
                    ) as acquired,
                ):
                    if not acquired:
                        logger.warning(
                            "fbs stock publish deferred: seller=%s marketplace=%s busy",
                            seller_id, target.marketplace,
                        )
                        continue
                    result = await sync_marketplace_stocks_for_target(
                        session,
                        target,
                        http_client,
                    )
                    await session.commit()
            except Exception:
                # One provider must never roll back the physical movement or suppress
                # publication to another provider. Periodic reconcile remains the safety net.
                logger.exception(
                    "fbs stock publish failed for seller %s marketplace %s (tenant %s)",
                    seller_id,
                    target.marketplace,
                    tenant_id,
                )
                continue
            logger.info(
                "fbs stock publish done: seller=%s marketplace=%s bindings=%s "
                "targeted=%s confirmed=%s errors=%s",
                seller_id,
                target.marketplace,
                result.bindings_processed,
                result.products_targeted,
                result.products_confirmed,
                result.binding_errors,
            )


def _dispatch(tenant_id: uuid.UUID, seller_id: uuid.UUID) -> None:
    """Hand the publish off to Celery, or to the running loop when there is no broker."""
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_fbs_stock_publish_seller_task

        run_fbs_stock_publish_seller_task.delay(str(tenant_id), str(seller_id))
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "fbs stock publish skipped for seller %s: no celery broker and no event loop",
            seller_id,
        )
        return
    # Keep a reference so the task is not garbage-collected mid-flight.
    task = loop.create_task(publish_seller_stocks_now(tenant_id, seller_id))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


async def drain_background_stock_publish_tasks() -> None:
    """Wait for in-process publish jobs before test schema teardown."""
    while _BACKGROUND_TASKS:
        tasks = tuple(_BACKGROUND_TASKS)
        await asyncio.gather(*tasks, return_exceptions=True)
        # gather over already finished tasks may not yield to their callbacks.
        # Remove this completed batch explicitly so teardown cannot busy-loop.
        _BACKGROUND_TASKS.difference_update(tasks)


def schedule_seller_stock_publish(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
) -> None:
    """Queue an FBS stock publish for this seller, to run once the transaction commits.

    Safe to call many times inside one operation: duplicates collapse, so a 40-line
    intake produces one publish per seller, not forty.
    """
    if seller_id is None:
        return
    pending: set[tuple[uuid.UUID, uuid.UUID]] = session.info.setdefault(_PENDING_KEY, set())
    pending.add((tenant_id, seller_id))
    if session.info.get(_HOOKED_KEY):
        return
    session.info[_HOOKED_KEY] = True

    sync_session = session.sync_session

    @event.listens_for(sync_session, "after_commit")
    def _after_commit(_session: object) -> None:
        queued = session.info.get(_PENDING_KEY)
        if not queued:
            return
        session.info[_PENDING_KEY] = set()
        for queued_tenant_id, queued_seller_id in queued:
            _dispatch(queued_tenant_id, queued_seller_id)

    @event.listens_for(sync_session, "after_rollback")
    def _after_rollback(_session: object) -> None:
        session.info[_PENDING_KEY] = set()
