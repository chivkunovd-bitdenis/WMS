"""WMS-442: operator sorting context and narrowly scoped outbound PC pairing."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin, require_reception_access
from app.api.fbs_print_jobs import _job_out, _raise_print_job_http
from app.db.session import get_db
from app.models.background_job import BackgroundJob
from app.models.print_connection import PrintConnection
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.fbs_print_asset_service import FbsPrintAssetError
from app.services.fbs_print_job_service import (
    claim_next_print_job,
    finish_print_job,
    get_print_job,
    load_print_job_content,
)
from app.services.sorting_print_service import create_sorting_job, resolve_label

router = APIRouter(prefix="/operations/print", tags=["operations"])
DB = Annotated[AsyncSession, Depends(get_db)]
Operator = Annotated[User, Depends(require_reception_access)]
Admin = Annotated[User, Depends(require_fulfillment_admin)]
bearer = HTTPBearer(auto_error=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def connection_out(connection: PrintConnection) -> dict[str, Any]:
    return {
        "connection_id": str(connection.id),
        "queue_name": connection.queue_name,
        "platform": connection.platform,
        "warehouse_id": str(connection.warehouse_id) if connection.warehouse_id else None,
        "paired": connection.tenant_id is not None,
        "is_default": connection.is_default,
        "last_seen_at": connection.last_seen_at.isoformat() if connection.last_seen_at else None,
        "online": bool(
            connection.last_seen_at
            and utc(connection.last_seen_at) > datetime.now(UTC) - timedelta(seconds=60)
        ),
    }


def job_out(job: BackgroundJob, *, claim: bool = False) -> dict[str, Any]:
    output = _job_out(job).model_dump()
    data = job.payload_json or {}
    for name in (
        "connection_id",
        "queue_name",
        "copies",
        "barcode",
        "label_title",
        "label_subtitle",
        "content_bytes",
        "request_id",
    ):
        output[name] = data.get(name)
    output["content_url"] = f"/operations/print/agent/jobs/{job.id}/content"
    if claim:
        output["claim_id"] = (job.result_json or {}).get("claim_id")
    return output


async def pc_connection(
    session: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> PrintConnection:
    if credentials is None:
        raise HTTPException(401, "print_connection_required")
    connection = await session.scalar(
        select(PrintConnection).where(PrintConnection.token_hash == digest(credentials.credentials))
    )
    if connection is None:
        raise HTTPException(401, "invalid_print_connection")
    if connection.tenant_id is None and utc(connection.pairing_expires_at) <= datetime.now(UTC):
        raise HTTPException(401, "pairing_expired")
    return connection


PC = Annotated[PrintConnection, Depends(pc_connection)]


class PairBegin(BaseModel):
    connection_id: uuid.UUID
    # Generated and stored privately by the PC before its first HTTP request.
    device_token: str = Field(min_length=43, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    queue_name: str = Field(min_length=1, max_length=127, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    platform: Literal["darwin", "linux"]


@router.post("/pairing")
async def begin_pairing(body: PairBegin, session: DB) -> dict[str, Any]:
    connection = await session.get(PrintConnection, body.connection_id)
    # Deterministic private code allows recovery of the first lost HTTP response.
    code = digest(body.device_token + ":pair")[:16].upper()
    if connection is not None:
        if (
            connection.token_hash != digest(body.device_token)
            or connection.queue_name != body.queue_name
            or connection.platform != body.platform
        ):
            raise HTTPException(409, "pairing_conflict")
        if connection.tenant_id is not None:
            return {"pairing_code": None, **connection_out(connection)}
        if utc(connection.pairing_expires_at) <= datetime.now(UTC):
            raise HTTPException(410, "pairing_expired")
    else:
        await session.execute(
            delete(PrintConnection).where(
                PrintConnection.tenant_id.is_(None),
                PrintConnection.pairing_expires_at < datetime.now(UTC),
            )
        )
        connection = PrintConnection(
            id=body.connection_id,
            token_hash=digest(body.device_token),
            pairing_hash=digest(code),
            pairing_expires_at=datetime.now(UTC) + timedelta(minutes=15),
            queue_name=body.queue_name,
            platform=body.platform,
            is_default=False,
        )
        session.add(connection)
        await session.commit()
    return {
        "pairing_code": code,
        "expires_at": connection.pairing_expires_at.isoformat(),
        **connection_out(connection),
    }


class PairConfirm(BaseModel):
    pairing_code: str = Field(min_length=16, max_length=19)


@router.post("/warehouses/{warehouse_id}/pair")
async def confirm_pairing(
    warehouse_id: uuid.UUID, body: PairConfirm, user: Admin, session: DB
) -> dict[str, Any]:
    warehouse = await session.scalar(
        select(Warehouse)
        .where(Warehouse.id == warehouse_id, Warehouse.tenant_id == user.tenant_id)
        .with_for_update()
    )
    if warehouse is None:
        raise HTTPException(404, "warehouse_not_found")
    code = re.sub(r"[\s-]", "", body.pairing_code).upper()
    connection = await session.scalar(
        select(PrintConnection)
        .where(PrintConnection.pairing_hash == digest(code))
        .with_for_update()
    )
    if connection is None or utc(connection.pairing_expires_at) <= datetime.now(UTC):
        raise HTTPException(404, "pairing_not_found_or_expired")
    if connection.tenant_id is not None:
        raise HTTPException(409, "pairing_already_used")
    await session.execute(
        update(PrintConnection)
        .where(PrintConnection.warehouse_id == warehouse.id, PrintConnection.is_default.is_(True))
        .values(is_default=False)
    )
    connection.tenant_id = user.tenant_id
    connection.warehouse_id = warehouse.id
    connection.paired_by_user_id = user.id
    connection.is_default = True
    connection.pairing_hash = None
    await session.commit()
    return connection_out(connection)


@router.get("/warehouses/{warehouse_id}/destination")
async def destination(warehouse_id: uuid.UUID, user: Operator, session: DB) -> dict[str, Any]:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != user.tenant_id:
        raise HTTPException(404, "warehouse_not_found")
    connection = await session.scalar(
        select(PrintConnection).where(
            PrintConnection.warehouse_id == warehouse_id,
            PrintConnection.tenant_id == user.tenant_id,
            PrintConnection.is_default.is_(True),
        )
    )
    return {"destination": connection_out(connection) if connection else None}


class SortingJobBody(BaseModel):
    job_id: uuid.UUID
    kind: Literal["product", "location"]
    object_id: uuid.UUID
    marketplace: Literal["wb", "ozon"] | None = None
    copies: int = Field(default=1, ge=1, le=999)
    connection_id: uuid.UUID


@router.get("/sorting/{request_id}/label")
async def preview_label(
    request_id: uuid.UUID,
    kind: Literal["product", "location"],
    object_id: uuid.UUID,
    user: Operator,
    session: DB,
    marketplace: Literal["wb", "ozon"] | None = None,
) -> dict[str, Any]:
    try:
        request, barcode, title, subtitle = await resolve_label(
            session,
            user.tenant_id,
            request_id,
            kind=kind,
            object_id=object_id,
            marketplace=marketplace,
        )
    except FbsPrintAssetError as exc:
        print_error(exc)
    return {
        "barcode": barcode,
        "label_title": title,
        "label_subtitle": subtitle,
        "warehouse_id": str(request.warehouse_id),
        "printable": bool(barcode),
        "error_message": None if barcode else "У объекта нет штрихкода.",
    }


def print_error(exc: FbsPrintAssetError) -> None:
    if exc.code in {"barcode_missing", "marketplace_required"}:
        raise HTTPException(422, {"code": exc.code, "message": exc.message})
    _raise_print_job_http(exc)


@router.post("/sorting/{request_id}/jobs", status_code=202)
async def create_job(
    request_id: uuid.UUID, body: SortingJobBody, user: Operator, session: DB
) -> dict[str, Any]:
    try:
        job = await create_sorting_job(
            session, user.tenant_id, user.id, request_id, **body.model_dump()
        )
    except FbsPrintAssetError as exc:
        print_error(exc)
    await session.commit()
    return job_out(job)


@router.get("/jobs/{job_id}")
async def read_job(job_id: uuid.UUID, user: Operator, session: DB) -> dict[str, Any]:
    try:
        job = await get_print_job(session, user.tenant_id, job_id)
    except FbsPrintAssetError as exc:
        print_error(exc)
    if (job.payload_json or {}).get("requested_by_user_id") != str(user.id):
        raise HTTPException(404, "print_job_not_found")
    return job_out(job)


@router.post("/agent/heartbeat")
async def heartbeat(connection: PC, session: DB) -> dict[str, Any]:
    connection.last_seen_at = datetime.now(UTC)
    await session.commit()
    return connection_out(connection)


def paired(connection: PrintConnection) -> tuple[uuid.UUID, uuid.UUID]:
    if connection.tenant_id is None or connection.warehouse_id is None:
        raise HTTPException(403, "print_connection_not_paired")
    return connection.tenant_id, connection.warehouse_id


@router.post("/agent/next")
async def next_job(connection: PC, session: DB) -> dict[str, Any]:
    tenant_id, warehouse_id = paired(connection)
    job = await claim_next_print_job(
        session, tenant_id, warehouse_id=warehouse_id, connection_id=connection.id
    )
    connection.last_seen_at = datetime.now(UTC)
    await session.commit()
    return {"job": job_out(job, claim=True) if job else None}


@router.get("/agent/jobs/{job_id}/content")
async def job_content(
    job_id: uuid.UUID, claim_id: uuid.UUID, connection: PC, session: DB
) -> Response:
    tenant_id, warehouse_id = paired(connection)
    try:
        content, mime = await load_print_job_content(
            session,
            tenant_id,
            job_id,
            warehouse_id=warehouse_id,
            connection_id=connection.id,
            claim_id=str(claim_id),
        )
    except FbsPrintAssetError as exc:
        print_error(exc)
    return Response(content, media_type=mime)


class ResultBody(BaseModel):
    claim_id: uuid.UUID
    queue_receipt: str | None = Field(default=None, max_length=256)
    handed_to_queue: bool
    error_message: str | None = Field(default=None, max_length=512)


@router.post("/agent/jobs/{job_id}/result")
async def job_result(
    job_id: uuid.UUID, body: ResultBody, connection: PC, session: DB
) -> dict[str, Any]:
    tenant_id, warehouse_id = paired(connection)
    if body.handed_to_queue and not (body.queue_receipt or "").strip():
        raise HTTPException(422, "queue_receipt_required")
    if not body.handed_to_queue and body.queue_receipt:
        raise HTTPException(422, "receipt_conflicts_with_failure")
    try:
        job = await finish_print_job(
            session,
            tenant_id,
            job_id,
            warehouse_id=warehouse_id,
            connection_id=connection.id,
            **{**body.model_dump(), "claim_id": str(body.claim_id)},
        )
    except FbsPrintAssetError as exc:
        print_error(exc)
    await session.commit()
    return job_out(job)
