from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_reception_access
from app.core.settings import settings
from app.db.session import get_db
from app.models.user import User
from app.services import inbound_marking_service as svc
from app.services.inbound_intake_service import InboundIntakeError

router = APIRouter(prefix="/operations/inbound-intake-requests", tags=["operations"])
logger = logging.getLogger(__name__)


class ScanBody(BaseModel):
    line_id: uuid.UUID
    cis_code: str = Field(min_length=1, max_length=512)


def _error(exc: InboundIntakeError) -> HTTPException:
    code = (
        404
        if exc.code
        in {"request_not_found", "line_not_found", "product_not_found", "marking_code_not_found"}
        else 409
    )
    if exc.code == "marking_invalid_code":
        code = 422
    return HTTPException(status_code=code, detail=exc.code)


async def schedule_after_posting(
    session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID, tasks: BackgroundTasks
) -> None:
    # The stock transaction has committed. A check failure cannot undo or block posting.
    try:
        await _schedule(session, tenant_id, request_id, tasks)
    except Exception:
        await session.rollback()
        logger.exception("Cannot schedule receiving marking check for %s", request_id)


async def _schedule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    tasks: BackgroundTasks,
    *,
    force: bool = False,
) -> None:
    job_id = await svc.schedule_check(session, tenant_id, request_id, force=force)
    if job_id is None:
        return
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_inbound_marking_check_task

        try:
            run_inbound_marking_check_task.delay(str(job_id))
        except Exception:
            # The same durable job remains idempotent if the broker accepted before failure.
            tasks.add_task(svc.run_check_job, job_id)
    else:
        tasks.add_task(svc.run_check_job, job_id)


@router.get("/{request_id}/marking-codes")
async def list_codes(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return await svc.list_codes(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        raise _error(exc) from None


@router.post("/{request_id}/marking-codes/scan")
async def scan_code(
    request_id: uuid.UUID,
    body: ScanBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return await svc.attach_code(
            session,
            user.tenant_id,
            request_id,
            line_id=body.line_id,
            cis_code=body.cis_code,
            actor_user_id=user.id,
        )
    except InboundIntakeError as exc:
        raise _error(exc) from None


@router.post("/{request_id}/marking-codes/check", status_code=202)
async def check_codes(
    request_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        await _schedule(session, user.tenant_id, request_id, background_tasks, force=True)
        result = await svc.list_codes(session, user.tenant_id, request_id)
        return {"checking": result["checking"]}
    except InboundIntakeError as exc:
        raise _error(exc) from None


@router.get("/{request_id}/marking-codes/problems.xlsx")
async def export_codes(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        result = await svc.list_codes(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        raise _error(exc) from None
    return Response(
        content=svc.export_problems(result["items"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="marking-problems-{request_id}.xlsx"'
        },
    )


@router.delete("/{request_id}/marking-codes/{code_id}", status_code=204)
async def delete_code(
    request_id: uuid.UUID,
    code_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await svc.delete_code(session, user.tenant_id, request_id, code_id)
    except InboundIntakeError as exc:
        raise _error(exc) from None
    return Response(status_code=204)
