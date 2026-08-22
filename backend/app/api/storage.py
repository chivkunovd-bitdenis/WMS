from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_ff_or_seller_with_permission
from app.core.settings import settings
from app.db.session import get_db
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_STORAGE_MEASUREMENT_REBUILD
from app.services.staff_permissions_service import PERM_INVENTORY
from app.services.storage_measurement_service import (
    MOSCOW,
    StorageMeasurementError,
    month_bounds,
    previous_month,
)
from app.services.storage_statement_service import (
    StorageStatementError,
    fix_storage_statement,
    get_fixed_storage_statement,
    get_storage_ledger_rows,
)

router = APIRouter(prefix="/operations/storage", tags=["storage"])
require_storage_access = require_ff_or_seller_with_permission(PERM_INVENTORY)


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
    seller_id: uuid.UUID
    warehouse_id: uuid.UUID
    measurements: list[dict[str, object]]
    total_liter_days: str
    total_amount: str


def _statement_out(statement, rows) -> StorageStatementOut:
    total_liter_days = sum((Decimal(str(row.liter_days)) for row in rows), Decimal(0))
    return StorageStatementOut(
        id=statement.id,
        status=statement.status,
        fixed_at=statement.fixed_at.isoformat() if statement.fixed_at else None,
        period_start=statement.period_start.isoformat(),
        period_end=statement.period_end.isoformat(),
        seller_id=statement.seller_id,
        warehouse_id=statement.warehouse_id,
        measurements=[
            {
                "product_id": row.product_id,
                "liter_days": str(row.liter_days),
                "source_type": "storage_measurement",
            }
            for row in rows
        ],
        total_liter_days=str(total_liter_days),
        total_amount="0",
    )


@router.post(
    "/measurements/rebuild", response_model=StorageRebuildOut, status_code=status.HTTP_202_ACCEPTED
)
async def rebuild_storage(
    body: StorageRebuildBody,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageRebuildOut:
    if (body.year is None) != (body.month is None):
        raise HTTPException(status_code=422, detail="year_and_month_required_together")
    try:
        period_start, _ = (
            month_bounds(body.year, body.month)
            if body.year is not None and body.month is not None
            else previous_month()
        )
    except StorageMeasurementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if period_start > datetime.now(MOSCOW).date().replace(day=1):
        raise HTTPException(status_code=422, detail="future_month")
    payload = {
        k: v
        for k, v in {
            "year": body.year,
            "month": body.month,
            "warehouse_id": str(body.warehouse_id) if body.warehouse_id else None,
        }.items()
        if v is not None
    }
    if user.role == "fulfillment_seller":
        payload["seller_id"] = str(user.seller_id)
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
    user: Annotated[User, Depends(require_storage_access)],
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
    out = _statement_out(statement, rows)
    ledger = await get_storage_ledger_rows(session, user.tenant_id, statement.id)
    out.measurements = [
        {
            "product_id": measurement.product_id,
            "liter_days": str(measurement.liter_days),
            "source_type": ledger_row.source_type,
            "service_code": ledger_row.service_code,
            "unit": ledger_row.unit,
            "rate_snapshot": str(ledger_row.rate_snapshot),
            "amount": str(ledger_row.amount),
        }
        for measurement, ledger_row in zip(rows, ledger, strict=True)
    ]
    out.total_amount = str(sum((Decimal(str(row.amount)) for row in ledger), Decimal(0)))
    return out


@router.get("/statements/{statement_id}/print", response_model=StorageStatementOut)
async def print_statement(
    statement_id: uuid.UUID,
    user: Annotated[User, Depends(require_storage_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorageStatementOut:
    try:
        statement, rows = await get_fixed_storage_statement(session, user.tenant_id, statement_id)
        if user.role == "fulfillment_seller" and user.seller_id != statement.seller_id:
            raise StorageStatementError("not_found")
    except StorageStatementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out = _statement_out(statement, rows)
    ledger = await get_storage_ledger_rows(session, user.tenant_id, statement.id)
    out.measurements = [
        {
            "product_id": measurement.product_id,
            "liter_days": str(measurement.liter_days),
            "source_type": ledger_row.source_type,
            "service_code": ledger_row.service_code,
            "unit": ledger_row.unit,
            "rate_snapshot": str(ledger_row.rate_snapshot),
            "amount": str(ledger_row.amount),
        }
        for measurement, ledger_row in zip(rows, ledger, strict=True)
    ]
    out.total_amount = str(sum((Decimal(str(row.amount)) for row in ledger), Decimal(0)))
    return out
