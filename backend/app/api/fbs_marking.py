from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.fbs_order import FbsOrderMarking
from app.models.user import User
from app.services import fbs_marking_service as marking_svc

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)


class FbsMarkingValueBody(BaseModel):
    value: str = Field(min_length=1, max_length=512)


class FbsOrderMarkingOut(BaseModel):
    id: str
    order_id: str
    kind: str
    value: str
    check_status: str
    marking_code_id: str | None


def _marking_out(row: FbsOrderMarking) -> FbsOrderMarkingOut:
    return FbsOrderMarkingOut(
        id=str(row.id),
        order_id=str(row.order_id),
        kind=row.kind,
        value=row.value,
        check_status=row.check_status,
        marking_code_id=str(row.marking_code_id) if row.marking_code_id else None,
    )


def _raise_from_service(exc: marking_svc.FbsMarkingError) -> None:
    if exc.code in {"order_not_found", "seller_not_found"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.code)
    if exc.code in {"invalid_kind", "empty_value"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    if exc.code == "order_marking_frozen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.get("/{order_id}/markings", response_model=list[FbsOrderMarkingOut])
async def get_fbs_order_markings(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsOrderMarkingOut]:
    try:
        rows = await marking_svc.list_order_markings(session, user.tenant_id, order_id)
    except marking_svc.FbsMarkingError as exc:
        _raise_from_service(exc)
    return [_marking_out(row) for row in rows]


@router.put("/{order_id}/markings/{kind}", response_model=FbsOrderMarkingOut)
async def put_fbs_order_marking(
    order_id: uuid.UUID,
    kind: str,
    body: FbsMarkingValueBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderMarkingOut:
    async with httpx.AsyncClient() as http_client:
        try:
            row = await marking_svc.upsert_order_marking(
                session,
                user.tenant_id,
                order_id,
                kind,
                body.value,
                http_client,
            )
        except marking_svc.FbsMarkingError as exc:
            _raise_from_service(exc)
    await session.commit()
    await session.refresh(row)
    return _marking_out(row)


@router.post("/{order_id}/markings/sync", response_model=list[FbsOrderMarkingOut])
async def sync_fbs_order_markings(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
