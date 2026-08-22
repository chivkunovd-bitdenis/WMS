from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ff_or_seller
from app.core.settings import settings
from app.db.session import get_db
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_STORAGE_MEASUREMENT_REBUILD
from app.services.storage_statement_service import (
    StorageStatementError,
    fix_storage_statement,
    get_fixed_storage_statement,
)

router = APIRouter(prefix="/operations/storage", tags=["storage"])


class StorageRebuildBody(BaseModel):
    year: int | None = None
    month: int | None = None
    warehouse_id: uuid.UUID | None = None


class StorageRebuildOut(BaseModel):
    id: str
    status: str


class StorageStatementOut(BaseModel):
    id: uuid.UUID
    status: str
    fixed_at: str | None
    period_start: str
    period_end: str
    measurements: list[dict[str, object]]


@router.post(
    "/measurements/rebuild", response_model=StorageRebuildOut, status_code=status.HTTP_202_ACCEPTED
)
async def rebuild_storage(
    body: StorageRebuildBody,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageRebuildOut:
    payload = {
        k: v
        for k, v in {
            "year": body.year,
            "month": body.month,
            "warehouse_id": str(body.warehouse_id) if body.warehouse_id else None,
        }.items()
        if v is not None
    }
    job = await job_svc.create_pending_job(
        session, user.tenant_id, job_type=JOB_TYPE_STORAGE_MEASUREMENT_REBUILD, payload_json=payload
    )
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_storage_measurement_rebuild_task

        run_storage_measurement_rebuild_task.delay(str(job.id))
    else:
        background_tasks.add_task(job_svc.run_storage_measurement_rebuild_job, job.id)
    return StorageRebuildOut(id=str(job.id), status=job.status)


@router.post("/statements/{statement_id}/fix", response_model=StorageStatementOut)
async def fix_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    if user.role != "fulfillment_admin":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        statement = await fix_storage_statement(session, user.tenant_id, statement_id)
        statement, rows = await get_fixed_storage_statement(session, user.tenant_id, statement.id)
    except StorageStatementError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=409 if code in {"missing_dimensions", "not_editable"} else 404,
            detail=code,
        ) from exc
    return StorageStatementOut(
        id=statement.id,
        status=statement.status,
        fixed_at=statement.fixed_at.isoformat() if statement.fixed_at else None,
        period_start=statement.period_start.isoformat(),
        period_end=statement.period_end.isoformat(),
        measurements=[
            {"product_id": row.product_id, "liter_days": str(row.liter_days)} for row in rows
        ],
    )


@router.get("/statements/{statement_id}/print", response_model=StorageStatementOut)
async def print_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_ff_or_seller)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    try:
        statement, rows = await get_fixed_storage_statement(session, user.tenant_id, statement_id)
    except StorageStatementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StorageStatementOut(
        id=statement.id, status=statement.status,
        fixed_at=statement.fixed_at.isoformat() if statement.fixed_at else None,
        period_start=statement.period_start.isoformat(),
        period_end=statement.period_end.isoformat(),
        measurements=[
            {"product_id": row.product_id, "liter_days": str(row.liter_days)} for row in rows
        ],
    )
