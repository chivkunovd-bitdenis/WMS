from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc
from app.db.session import get_db
from app.models.fbs_order import FbsOrderMarking
from app.models.user import User
from app.services import fbs_marking_service as marking_svc

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)


class FbsOrderMarkingOut(BaseModel):
    id: str
    order_id: str
    kind: str
    value: str
    check_status: str
    marking_code_id: str | None
    meta_status: str
    reason: str | None = None


class FbsOrderMetadataOut(BaseModel):
    required: list[str]
    optional: list[str]
    states: list[dict[str, Any]]
    delivery_allowed: bool
    last_checked_at: str | None


def _marking_out(row: FbsOrderMarking) -> FbsOrderMarkingOut:
    return FbsOrderMarkingOut(
        id=str(row.id),
        order_id=str(row.order_id),
        kind=row.kind,
        value=row.value,
        check_status=row.check_status,
        marking_code_id=str(row.marking_code_id) if row.marking_code_id else None,
        meta_status=row.meta_status,
        reason=row.reason,
    )


def _metadata_out(payload: dict[str, Any]) -> FbsOrderMetadataOut:
    return FbsOrderMetadataOut(**payload)


def _raise_from_service(exc: marking_svc.FbsMarkingError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code in {"order_not_found", "seller_not_found"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if exc.code in {
        "invalid_kind",
        "empty_value",
        "kind_not_required",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if exc.code in {
        "order_marking_frozen",
        "duplicate_kiz",
        "cross_seller_code",
        "code_product_mismatch",
        "kind_already_assigned",
        "marking_code_already_assigned",
        "meta_validation_fail",
        "sgtin_missing_gs",
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


@router.get("/{order_id}/metadata", response_model=FbsOrderMetadataOut)
async def get_fbs_order_metadata(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderMetadataOut:
    async with httpx.AsyncClient() as http_client:
        try:
            payload = await marking_svc.get_order_metadata(
                session,
                user.tenant_id,
                order_id,
                http_client,
            )
        except marking_svc.FbsMarkingError as exc:
            _raise_from_service(exc)
    await session.commit()
    return _metadata_out(payload)


@router.get("/{order_id}/markings", response_model=list[FbsOrderMarkingOut])
async def get_fbs_order_markings(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsOrderMarkingOut]:
    try:
        rows = await marking_svc.list_order_markings(session, user.tenant_id, order_id)
    except marking_svc.FbsMarkingError as exc:
        _raise_from_service(exc)
    return [_marking_out(row) for row in rows]


@router.post("/{order_id}/markings/sync", response_model=list[FbsOrderMarkingOut])
async def sync_fbs_order_markings(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsOrderMarkingOut]:
    async with httpx.AsyncClient() as http_client:
        try:
            rows = await marking_svc.sync_order_marking_statuses(
                session,
                user.tenant_id,
                order_id,
                http_client,
            )
        except marking_svc.FbsMarkingError as exc:
            _raise_from_service(exc)
    await session.commit()
    return [_marking_out(row) for row in rows]
