from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.inventory_movement import InventoryMovement

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"

JOB_TYPE_MOVEMENTS_DIGEST = "movements_digest"


async def create_pending_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_type: str,
) -> BackgroundJob:
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type=job_type,
        status=JOB_STATUS_PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
) -> BackgroundJob | None:
    job = await session.get(BackgroundJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        return None
    return job


async def run_movements_digest_job(job_id: uuid.UUID) -> None:
    """Выполняется в фоне после ответа API (отдельная сессия БД)."""
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("background job missing: %s", job_id)
            return
        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            await asyncio.sleep(0.35)
            stmt = (
                select(InventoryMovement.movement_type, func.count(InventoryMovement.id))
                .where(InventoryMovement.tenant_id == job.tenant_id)
                .group_by(InventoryMovement.movement_type)
            )
            res = await session.execute(stmt)
            rows = list(res.all())
            by_type: dict[str, int] = {str(mt): int(c) for mt, c in rows}
            total = sum(by_type.values())
            result: dict[str, Any] = {
                "movement_counts_by_type": by_type,
                "total_movements": total,
            }
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except Exception as exc:
            logger.exception("background job failed: %s", exc)
            job.status = JOB_STATUS_FAILED
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()
