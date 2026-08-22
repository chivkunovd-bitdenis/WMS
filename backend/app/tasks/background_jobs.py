"""Celery tasks for background jobs (async service code via asyncio.run)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from typing import Protocol

from app.celery_app import celery_app
from app.services.background_job_service import (
    purge_expired_label_tape_assets,
    run_fbs_stock_sync_job,
    run_marking_label_tape_job,
    run_movements_digest_job,
    run_wildberries_cards_sync_job,
    run_wildberries_marketplace_orders_sync_job,
    run_wildberries_supplies_sync_job,
)


class _SellerSyncTask(Protocol):
    def apply_async(
        self,
        args: tuple[str, str],
        *,
        countdown: float,
    ) -> object: ...


class _SellerSyncTarget(Protocol):
    @property
    def tenant_id(self) -> uuid.UUID: ...

    @property
    def seller_id(self) -> uuid.UUID: ...


def _dispatch_seller_syncs_evenly(
    task: _SellerSyncTask,
    targets: Sequence[_SellerSyncTarget],
    *,
    interval_seconds: float,
) -> None:
    """Spread one cycle across its interval instead of sending a WB request burst."""
    if not targets:
        return
    spacing = interval_seconds / len(targets)
    for index, target in enumerate(targets):
        task.apply_async(
            args=(str(target.tenant_id), str(target.seller_id)),
            countdown=index * spacing,
        )


@celery_app.task(name="wms.marking_label_tape", queue="print")
def run_marking_label_tape_task(job_id: str) -> None:
    asyncio.run(run_marking_label_tape_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.purge_expired_label_tape_assets")
def purge_expired_label_tape_assets_task() -> None:
    asyncio.run(purge_expired_label_tape_assets())


@celery_app.task(name="wms.movements_digest")
def run_movements_digest_task(job_id: str) -> None:
    asyncio.run(run_movements_digest_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wildberries_cards_sync")
def run_wildberries_cards_sync_task(job_id: str) -> None:
    asyncio.run(run_wildberries_cards_sync_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wildberries_supplies_sync")
def run_wildberries_supplies_sync_task(job_id: str) -> None:
    asyncio.run(run_wildberries_supplies_sync_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wildberries_marketplace_orders_sync")
def run_wildberries_marketplace_orders_sync_task(job_id: str) -> None:
    asyncio.run(run_wildberries_marketplace_orders_sync_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.fbs_stock_sync")
def run_fbs_stock_sync_task(job_id: str) -> None:
    asyncio.run(run_fbs_stock_sync_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wb_mp_warehouses_daily_sync")
def run_wb_mp_warehouses_daily_sync_task() -> None:
    from app.services.wb_mp_warehouse_service import run_daily_wb_mp_warehouses_sync_all_tenants

    asyncio.run(run_daily_wb_mp_warehouses_sync_all_tenants())


@celery_app.task(name="wms.marking_low_stock")
def run_marking_low_stock_task() -> None:
    from app.services.marking_low_stock_service import run_marking_low_stock_all_tenants

    asyncio.run(run_marking_low_stock_all_tenants())


@celery_app.task(name="wms.fbs_orders_autopoll")
def run_fbs_orders_autopoll_task() -> None:
    from app.services.fbs_autopoll_service import poll_fbs_orders_all_sellers

    asyncio.run(poll_fbs_orders_all_sellers())


@celery_app.task(name="wms.wb_orders_new")
def run_wb_orders_new_task(tenant_id: str, seller_id: str) -> None:
    from app.services.fbs_autopoll_service import sync_new_orders_for_seller_job

    asyncio.run(sync_new_orders_for_seller_job(uuid.UUID(tenant_id), uuid.UUID(seller_id)))


@celery_app.task(name="wms.wb_orders_reconcile")
def run_wb_orders_reconcile_task(tenant_id: str, seller_id: str) -> None:
    from app.services.fbs_autopoll_service import reconcile_orders_for_seller_job

    asyncio.run(reconcile_orders_for_seller_job(uuid.UUID(tenant_id), uuid.UUID(seller_id)))


@celery_app.task(name="wms.wb_orders_new_dispatch")
def dispatch_wb_orders_new_task() -> None:
    from app.db.session import SessionLocal
    from app.services.fbs_autopoll_service import list_sellers_with_marketplace_token

    async def dispatch() -> None:
        async with SessionLocal() as session:
            targets = await list_sellers_with_marketplace_token(session)
        _dispatch_seller_syncs_evenly(
            run_wb_orders_new_task,
            targets,
            interval_seconds=180.0,
        )

    asyncio.run(dispatch())


@celery_app.task(name="wms.wb_orders_reconcile_dispatch")
def dispatch_wb_orders_reconcile_task() -> None:
    from app.db.session import SessionLocal
    from app.services.fbs_autopoll_service import list_sellers_with_marketplace_token

    async def dispatch() -> None:
        async with SessionLocal() as session:
            targets = await list_sellers_with_marketplace_token(session)
        _dispatch_seller_syncs_evenly(
            run_wb_orders_reconcile_task,
            targets,
            interval_seconds=3600.0,
        )

    asyncio.run(dispatch())


@celery_app.task(name="wms.fbs_order_statuses_autopoll")
def run_fbs_order_statuses_autopoll_task() -> None:
    from app.services.fbs_autopoll_service import sync_fbs_order_statuses_all_sellers

    asyncio.run(sync_fbs_order_statuses_all_sellers())


@celery_app.task(name="wms.fbs_stock_reconcile")
def run_fbs_stock_reconcile_task() -> None:
    from app.services.fbs_autopoll_service import reconcile_fbs_stocks_all_sellers

    asyncio.run(reconcile_fbs_stocks_all_sellers())


@celery_app.task(name="wms.fbs_stock_publish_seller")
def run_fbs_stock_publish_seller_task(tenant_id: str, seller_id: str) -> None:
    """Event-driven publication: one seller, triggered by a stock movement."""
    from app.services.fbs_stock_publish_service import publish_seller_stocks_now

    asyncio.run(publish_seller_stocks_now(uuid.UUID(tenant_id), uuid.UUID(seller_id)))
