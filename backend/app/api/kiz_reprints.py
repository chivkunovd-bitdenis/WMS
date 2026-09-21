from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_reception_access
from app.db.session import get_db
from app.models.kiz_reprint import KizReprint
from app.models.seller import Seller
from app.models.user import User
from app.services import kiz_reprint_service as reprint_svc

router = APIRouter(prefix="/operations/kiz-reprints", tags=["operations"])


class KizReprintCreateIn(BaseModel):
    seller_id: uuid.UUID
    kiz: str = Field(max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)


class KizReprintOut(BaseModel):
    id: str
    seller_id: str
    kiz: str
    created_at: str
    print_started_at: str | None
    replayed: bool = False


class KizReprintListOut(BaseModel):
    rows: list[KizReprintOut]


class KizReprintPrintClaimIn(BaseModel):
    attempt_key: str = Field(min_length=1, max_length=128)


class KizReprintPrintClaimOut(BaseModel):
    row: KizReprintOut
    claimed: bool


def _out(row: KizReprint, *, replayed: bool = False) -> KizReprintOut:
    return KizReprintOut(
        id=str(row.id),
        seller_id=str(row.seller_id),
        kiz=row.kiz,
        created_at=row.created_at.isoformat(),
        print_started_at=(row.print_started_at.isoformat() if row.print_started_at else None),
        replayed=replayed,
    )


async def _require_seller_in_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> None:
    seller = await session.scalar(
        select(Seller.id).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
    )
    if seller is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")


def _raise_service_error(exc: reprint_svc.KizReprintServiceError) -> None:
    if exc.code in {"idempotency_key_reused"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    invalid_request_codes = {
        "idempotency_key_required",
        "idempotency_key_too_long",
        "not_a_kiz",
        "gs_separator_lost",
        "print_claim_key_required",
        "print_claim_key_too_long",
    }
    if exc.code in invalid_request_codes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.code)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="kiz_reprint_save_failed",
    )


async def _require_reprint_in_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reprint_id: uuid.UUID,
) -> None:
    row = await session.scalar(
        select(KizReprint.id).where(
            KizReprint.id == reprint_id,
            KizReprint.tenant_id == tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reprint_not_found")


@router.get("", response_model=KizReprintListOut)
async def list_kiz_reprint_history(
    seller_id: Annotated[uuid.UUID, Query()],
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KizReprintListOut:
    await _require_seller_in_tenant(session, user.tenant_id, seller_id)
    rows = await reprint_svc.list_kiz_reprints(session, user.tenant_id, seller_id)
    return KizReprintListOut(rows=[_out(row) for row in rows])


@router.post("", response_model=KizReprintOut, status_code=status.HTTP_201_CREATED)
async def create_kiz_reprint(
    body: KizReprintCreateIn,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KizReprintOut:
    await _require_seller_in_tenant(session, user.tenant_id, body.seller_id)
    try:
        result = await reprint_svc.save_kiz_reprint(
            session,
            user.tenant_id,
            body.seller_id,
            raw_kiz=body.kiz,
            idempotency_key=body.idempotency_key,
            actor_user_id=user.id,
        )
    except reprint_svc.KizReprintServiceError as exc:
        _raise_service_error(exc)
    return _out(result.row, replayed=result.replayed)


@router.post("/{reprint_id}/print-claim", response_model=KizReprintPrintClaimOut)
async def claim_kiz_reprint_print(
    reprint_id: uuid.UUID,
    body: KizReprintPrintClaimIn,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KizReprintPrintClaimOut:
    await _require_reprint_in_tenant(session, user.tenant_id, reprint_id)
    try:
        result = await reprint_svc.claim_kiz_reprint_print(
            session, user.tenant_id, reprint_id, attempt_key=body.attempt_key
        )
    except reprint_svc.KizReprintServiceError as exc:
        _raise_service_error(exc)
    return KizReprintPrintClaimOut(row=_out(result.row), claimed=result.claimed)


@router.post("/{reprint_id}/print-started", response_model=KizReprintOut)
async def mark_kiz_reprint_print_started(
    reprint_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KizReprintOut:
    try:
        row = await reprint_svc.mark_kiz_reprint_print_started(
            session, user.tenant_id, reprint_id
        )
    except reprint_svc.KizReprintServiceError as exc:
        _raise_service_error(exc)
    return _out(row)


@router.post("/{reprint_id}/print-failed", response_model=KizReprintOut)
async def release_kiz_reprint_print_claim(
    reprint_id: uuid.UUID,
    body: KizReprintPrintClaimIn,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KizReprintOut:
    try:
        row = await reprint_svc.release_kiz_reprint_print_claim(
            session, user.tenant_id, reprint_id, attempt_key=body.attempt_key
        )
    except reprint_svc.KizReprintServiceError as exc:
        _raise_service_error(exc)
    return _out(row)
