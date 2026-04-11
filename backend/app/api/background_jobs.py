from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin
from app.core.settings import settings
from app.db.session import get_db
from app.models.background_job import BackgroundJob
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_MOVEMENTS_DIGEST

router = APIRouter(
    prefix="/operations/background-jobs",
    tags=["operations"],
)


class BackgroundJobStartBody(BaseModel):
    job_type: str = Field(min_length=1, max_length=64)


class BackgroundJobStartOut(BaseModel):
    id: str
    status: str


class BackgroundJobOut(BaseModel):
    id: str
    job_type: str
    status: str
    result_json: dict[str, Any] | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


def _job_out(job: BackgroundJob) -> BackgroundJobOut:
    return BackgroundJobOut(
        id=str(job.id),
        job_type=job.job_type,
        status=job.status,
        result_json=job.result_json,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.post(
    "",
    response_model=BackgroundJobStartOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_background_job(
    body: BackgroundJobStartBody,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BackgroundJobStartOut:
    if body.job_type != JOB_TYPE_MOVEMENTS_DIGEST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown_job_type",
        )
    job = await job_svc.create_pending_job(
        session,
        user.tenant_id,
        job_type=body.job_type,
    )
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_movements_digest_task

        run_movements_digest_task.delay(str(job.id))
    else:
        background_tasks.add_task(job_svc.run_movements_digest_job, job.id)
    return BackgroundJobStartOut(id=str(job.id), status=job.status)


@router.get("/{job_id}", response_model=BackgroundJobOut)
async def get_background_job(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BackgroundJobOut:
    job = await job_svc.get_job(session, user.tenant_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job_not_found",
        )
    return _job_out(job)
