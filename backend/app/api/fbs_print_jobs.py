"""Очередь печати готовых этикеток FBS на складской принтер (WMS-402).

Узкий контур: эти ручки умеют только ставить в очередь один уже готовый
``FbsPrintAsset``, выдавать его локальному агенту склада и принимать квитанцию
очереди ОС. Ни маркетплейс, ни складские остатки, ни статусы поставки отсюда не
меняются, повторная подготовка этикетки не запускается.

Оператор на ТСД: ``POST ""`` и ``GET /{job_id}``.
Локальный агент на складском компьютере: ``POST /next``,
``GET /{job_id}/content``, ``POST /{job_id}/result``.

Агент ходит наружу сам, поэтому входящий доступ в сеть склада не нужен.
Внутренний ``storage_path`` наружу не отдаётся ни в одном ответе.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc
from app.db.session import get_db
from app.models.background_job import BackgroundJob
from app.models.user import User
from app.services.fbs_print_asset_service import FbsPrintAssetError
from app.services.fbs_print_job_service import (
    claim_next_print_job,
    create_print_job,
    finish_print_job,
    get_print_job,
    load_print_job_content,
    print_job_status_text,
)

router = APIRouter(prefix="/operations/fbs-print-jobs", tags=["operations"])

_NOT_FOUND_CODES = frozenset({"asset_not_found", "print_job_not_found", "warehouse_not_found"})
_CONFLICT_CODES = frozenset(
    {
        "asset_not_ready",
        "order_cancelled",
        "print_asset_changed",
        "print_asset_warehouse_mismatch",
        "print_job_conflict",
        "print_job_not_running",
        "print_job_result_conflict",
    }
)


def _raise_print_job_http(exc: FbsPrintAssetError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code in _NOT_FOUND_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code in _CONFLICT_CODES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code == "invalid_kind":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


class FbsPrintJobCreateBody(BaseModel):
    # Идентификатор задаёт ТСД один раз на явное нажатие печати. Повтор HTTP с тем
    # же значением возвращает то же задание, а не печатает второй лист.
    job_id: uuid.UUID
    asset_id: uuid.UUID
    warehouse_id: uuid.UUID


class FbsPrintJobResultBody(BaseModel):
    warehouse_id: uuid.UUID
    # Квитанция очереди ОС. Она есть только когда очередь действительно приняла
    # файл, поэтому при отказе поле пустое, а причина едет в error_message.
    queue_receipt: str | None = Field(default=None, max_length=256)
    handed_to_queue: bool = True
    error_message: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _receipt_required_when_handed(self) -> FbsPrintJobResultBody:
        if self.handed_to_queue and not (self.queue_receipt or "").strip():
            raise ValueError("queue_receipt обязателен при handed_to_queue=true")
        return self


class FbsPrintJobOut(BaseModel):
    id: str
    status: str
    status_text: str
    warehouse_id: str | None
    asset_id: str | None
    asset_kind: str | None
    content_type: str | None
    checksum: str | None
    width_mm: int | None
    height_mm: int | None
    content_url: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    queue_receipt: str | None
    error_message: str | None


class FbsPrintJobNextOut(BaseModel):
    job: FbsPrintJobOut | None


def _job_out(job: BackgroundJob) -> FbsPrintJobOut:
    payload = job.payload_json or {}
    result = job.result_json or {}
    width = payload.get("width_mm")
    height = payload.get("height_mm")
    return FbsPrintJobOut(
        id=str(job.id),
        status=job.status,
        status_text=print_job_status_text(job.status),
        warehouse_id=payload.get("warehouse_id"),
        asset_id=payload.get("asset_id"),
        asset_kind=payload.get("asset_kind"),
        content_type=payload.get("content_type"),
        checksum=payload.get("checksum"),
        width_mm=width if isinstance(width, int) else None,
        height_mm=height if isinstance(height, int) else None,
        content_url=f"/operations/fbs-print-jobs/{job.id}/content",
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        queue_receipt=result.get("queue_receipt"),
        error_message=job.error_message,
    )


@router.post("", response_model=FbsPrintJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_fbs_print_job(
    body: FbsPrintJobCreateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintJobOut:
    try:
        job = await create_print_job(
            session,
            user.tenant_id,
            job_id=body.job_id,
            asset_id=body.asset_id,
            warehouse_id=body.warehouse_id,
            user_id=user.id,
        )
    except FbsPrintAssetError as exc:
        _raise_print_job_http(exc)
    await session.commit()
    return _job_out(job)


@router.post("/next", response_model=FbsPrintJobNextOut)
async def claim_next_fbs_print_job(
    warehouse_id: Annotated[uuid.UUID, Query()],
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintJobNextOut:
    job = await claim_next_print_job(session, user.tenant_id, warehouse_id=warehouse_id)
    await session.commit()
    return FbsPrintJobNextOut(job=_job_out(job) if job is not None else None)


@router.get("/{job_id}/content")
async def get_fbs_print_job_content(
    job_id: uuid.UUID,
    warehouse_id: Annotated[uuid.UUID, Query()],
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        payload, content_type = await load_print_job_content(
            session,
            user.tenant_id,
            job_id,
            warehouse_id=warehouse_id,
        )
    except FbsPrintAssetError as exc:
        _raise_print_job_http(exc)
    return Response(content=payload, media_type=content_type)


@router.post("/{job_id}/result", response_model=FbsPrintJobOut)
async def report_fbs_print_job_result(
    job_id: uuid.UUID,
    body: FbsPrintJobResultBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintJobOut:
    try:
        job = await finish_print_job(
            session,
            user.tenant_id,
            job_id,
            warehouse_id=body.warehouse_id,
            queue_receipt=body.queue_receipt,
            handed_to_queue=body.handed_to_queue,
            error_message=body.error_message,
        )
    except FbsPrintAssetError as exc:
        _raise_print_job_http(exc)
    await session.commit()
    return _job_out(job)


@router.get("/{job_id}", response_model=FbsPrintJobOut)
async def get_fbs_print_job(
    job_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintJobOut:
    try:
        job = await get_print_job(session, user.tenant_id, job_id)
    except FbsPrintAssetError as exc:
        _raise_print_job_http(exc)
    return _job_out(job)
