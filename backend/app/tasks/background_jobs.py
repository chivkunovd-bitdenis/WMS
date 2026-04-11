"""Celery tasks for background jobs (async service code via asyncio.run)."""

from __future__ import annotations

import asyncio
import uuid

from app.celery_app import celery_app
from app.services.background_job_service import (
    run_movements_digest_job,
    run_wildberries_cards_sync_job,
    run_wildberries_supplies_sync_job,
)


@celery_app.task(name="wms.movements_digest")
def run_movements_digest_task(job_id: str) -> None:
    asyncio.run(run_movements_digest_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wildberries_cards_sync")
def run_wildberries_cards_sync_task(job_id: str) -> None:
    asyncio.run(run_wildberries_cards_sync_job(uuid.UUID(job_id)))


@celery_app.task(name="wms.wildberries_supplies_sync")
def run_wildberries_supplies_sync_task(job_id: str) -> None:
    asyncio.run(run_wildberries_supplies_sync_job(uuid.UUID(job_id)))
