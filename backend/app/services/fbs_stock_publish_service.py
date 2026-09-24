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
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.services.marketplace_seller_lock_service import marketplace_seller_lock

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.fbs_autopoll_service import SellerPollTarget

_PENDING_KEY = "fbs_stock_publish_pending"
_HOOKED_KEY = "fbs_stock_publish_hooked"
_EVENT_PUBLISH_ATTEMPTS = 3
_EVENT_PUBLISH_RETRY_SECONDS = 1.0
_EVENT_FOLLOW_UP_WAIT_SECONDS = 30.0


@dataclass
class _CoalescedPublish:
    task: asyncio.Task[None] | None = None
    rerun_requested: bool = False


_COALESCED_REQUESTS: dict[
    tuple[uuid.UUID, uuid.UUID, str | None], _CoalescedPublish
] = {}


async def _publish_seller_stocks_pass(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str | None = None,
) -> None:
    """Republish independently for every connected provider after movement commit."""
    from app.services.fbs_autopoll_service import (
        _MARKETPLACE_BACKOFF,
        SellerPollTarget,
        list_marketplace_poll_targets,
        sync_marketplace_stocks_for_target,
    )

    async with SessionLocal() as target_session:
        all_targets = await list_marketplace_poll_targets(target_session)
        enabled_marketplaces = set(
            await target_session.scalars(
                select(FbsWarehouseBinding.marketplace)
                .where(
                    FbsWarehouseBinding.tenant_id == tenant_id,
                    FbsWarehouseBinding.seller_id == seller_id,
                    FbsWarehouseBinding.is_active.is_(True),
                    FbsWarehouseBinding.stock_sync_enabled.is_(True),
                )
                .distinct()
            )
        )
    targets_by_marketplace = {
        target.marketplace: target
        for target in all_targets
        if target.tenant_id == tenant_id and target.seller_id == seller_id
    }
    # Order polling may omit an unserved WB warehouse, but `served` is not a
    # publication switch. Every active stock binding remains an event target.
    for enabled_marketplace in enabled_marketplaces:
        targets_by_marketplace.setdefault(
            enabled_marketplace,
            SellerPollTarget(tenant_id, seller_id, enabled_marketplace),
        )
    targets = [
        target
        for target in targets_by_marketplace.values()
        if marketplace is None or target.marketplace == marketplace
    ]

    async def publish_target_once(
        target: SellerPollTarget, http_client: httpx.AsyncClient
    ) -> None:
        async with AsyncExitStack() as coalescing_stack:
            follow_up_claimed = False
            attempt = 1
            while attempt <= _EVENT_PUBLISH_ATTEMPTS:
                provider_backoff = _MARKETPLACE_BACKOFF.remaining_seconds(target.marketplace)
                if provider_backoff > 0:
                    await asyncio.sleep(provider_backoff)
                lock_wait_timeout = (
                    _EVENT_FOLLOW_UP_WAIT_SECONDS if follow_up_claimed else 0.0
                )
                try:
                    async with (
                        SessionLocal() as session,
                        AsyncSession(bind=session.bind) as lock_session,
                        marketplace_seller_lock(
                            lock_session,
                            target.seller_id,
                            target.marketplace,
                            wait_timeout_sec=lock_wait_timeout,
                        ) as acquired,
                    ):
                        if not acquired and not follow_up_claimed:
                            # Cross-process/Celery coalescing without a table:
                            # one contender owns the follow-up advisory lock and
                            # waits for the active publisher; every later event
                            # joins that pending pass by returning immediately.
                            follow_up_session = await coalescing_stack.enter_async_context(
                                SessionLocal()
                            )
                            follow_up_lock_session = await coalescing_stack.enter_async_context(
                                AsyncSession(bind=follow_up_session.bind)
                            )
                            follow_up_claimed = await coalescing_stack.enter_async_context(
                                marketplace_seller_lock(
                                    follow_up_lock_session,
                                    target.seller_id,
                                    f"{target.marketplace}:event-follow-up",
                                    wait_timeout_sec=0,
                                )
                            )
                            if not follow_up_claimed:
                                logger.info(
                                    "fbs stock publish coalesced: seller=%s marketplace=%s",
                                    seller_id,
                                    target.marketplace,
                                )
                                return
                            continue
                        if not acquired:
                            logger.warning(
                                "fbs stock publish follow-up timed out: "
                                "seller=%s marketplace=%s wait_seconds=%s",
                                seller_id,
                                target.marketplace,
                                _EVENT_FOLLOW_UP_WAIT_SECONDS,
                            )
                            return
                        if follow_up_claimed:
                            # The waiting pass now owns the main lock. Release its
                            # follow-up claim before provider I/O so an event that
                            # arrives during this pass can reserve the next pass.
                            await coalescing_stack.aclose()
                            follow_up_claimed = False
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
                        "fbs stock publish transient failure for seller %s "
                        "marketplace %s (tenant %s) attempt=%s",
                        seller_id,
                        target.marketplace,
                        tenant_id,
                        attempt,
                    )
                    if attempt >= _EVENT_PUBLISH_ATTEMPTS:
                        return
                    attempt += 1
                    await asyncio.sleep(_EVENT_PUBLISH_RETRY_SECONDS)
                    continue
                errors = int(getattr(result, "errors", 0))
                binding_errors = int(getattr(result, "binding_errors", 0))
                retryable_errors = int(getattr(result, "retryable_errors", 0))
                if retryable_errors:
                    retry_after_seconds = max(
                        0.0,
                        float(getattr(result, "retry_after_seconds", 0.0)),
                    )
                    if retry_after_seconds > 0:
                        _MARKETPLACE_BACKOFF.record_rate_limit(
                            target.marketplace,
                            retry_after_seconds=retry_after_seconds,
                        )
                    logger.warning(
                        "fbs stock publish temporarily incomplete: seller=%s marketplace=%s "
                        "attempt=%s errors=%s binding_errors=%s retryable_errors=%s",
                        seller_id,
                        target.marketplace,
                        attempt,
                        errors,
                        binding_errors,
                        retryable_errors,
                    )
                    if attempt >= _EVENT_PUBLISH_ATTEMPTS:
                        return
                    attempt += 1
                    await asyncio.sleep(
                        max(_EVENT_PUBLISH_RETRY_SECONDS, retry_after_seconds)
                    )
                    continue
                if errors or binding_errors:
                    logger.warning(
                        "fbs stock publish permanent failure: seller=%s marketplace=%s "
                        "errors=%s binding_errors=%s",
                        seller_id,
                        target.marketplace,
                        errors,
                        binding_errors,
                    )
                    return
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
                return

    async with httpx.AsyncClient() as http_client:
        await asyncio.gather(
            *(publish_target_once(target, http_client) for target in targets)
        )


async def publish_seller_stocks_now(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str | None = None,
) -> None:
    """Coalesce each burst, then keep publishing while a later event requests a pass."""
    key = (tenant_id, seller_id, marketplace)
    existing = _COALESCED_REQUESTS.get(key)
    if existing is not None and existing.task is not None and not existing.task.done():
        existing.rerun_requested = True
        await asyncio.shield(existing.task)
        return

    state = _CoalescedPublish()

    async def run() -> None:
        while True:
            state.rerun_requested = False
            await _publish_seller_stocks_pass(tenant_id, seller_id, marketplace)
            if not state.rerun_requested:
                return

    state.task = asyncio.create_task(run())
    _COALESCED_REQUESTS[key] = state
    try:
        await asyncio.shield(state.task)
    finally:
        if _COALESCED_REQUESTS.get(key) is state:
            _COALESCED_REQUESTS.pop(key, None)


def _dispatch(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    marketplace: str | None = None,
) -> None:
    """Hand the publish off to Celery, or to the running loop when there is no broker."""
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_fbs_stock_publish_seller_task

        if marketplace is None:
            run_fbs_stock_publish_seller_task.delay(str(tenant_id), str(seller_id))
        else:
            run_fbs_stock_publish_seller_task.delay(str(tenant_id), str(seller_id), marketplace)
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
    task = loop.create_task(
        publish_seller_stocks_now(tenant_id, seller_id, marketplace)
        if marketplace is not None
        else publish_seller_stocks_now(tenant_id, seller_id)
    )
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
    marketplace: str | None = None,
) -> None:
    """Queue an FBS stock publish for this seller, to run once the transaction commits.

    Safe to call many times inside one operation: duplicates collapse, so a 40-line
    intake produces one publish per seller, not forty.
    """
    if seller_id is None:
        return
    pending: set[tuple[uuid.UUID, uuid.UUID, str | None]] = session.info.setdefault(
        _PENDING_KEY, set()
    )
    pending.add((tenant_id, seller_id, marketplace))
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
        for queued_tenant_id, queued_seller_id, queued_marketplace in queued:
            if queued_marketplace is None:
                _dispatch(queued_tenant_id, queued_seller_id)
            else:
                _dispatch(queued_tenant_id, queued_seller_id, queued_marketplace)

    @event.listens_for(sync_session, "after_rollback")
    def _after_rollback(_session: object) -> None:
        session.info[_PENDING_KEY] = set()
