from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_effective_seller_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.developer_request import DeveloperRequestCreate, DeveloperRequestOut
from app.services import developer_request_service as service

router = APIRouter(prefix="/developer-requests", tags=["developer-requests"])


@router.post("", response_model=DeveloperRequestOut)
async def create_developer_request(
    body: DeveloperRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeveloperRequestOut:
    try:
        row = await service.create_request(session, user, seller_id, body)
    except service.IdempotencyConflict:
        raise HTTPException(status_code=409, detail="idempotency_key_conflict") from None
    await session.commit()
    return DeveloperRequestOut.model_validate(row)


@router.get("", response_model=list[DeveloperRequestOut])
async def list_developer_requests(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeveloperRequestOut]:
    return [
        DeveloperRequestOut.model_validate(row)
        for row in await service.list_requests(session, user)
    ]


@router.get("/{request_id}", response_model=DeveloperRequestOut)
async def get_developer_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeveloperRequestOut:
    row = await service.get_request(session, user, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="developer_request_not_found")
    return DeveloperRequestOut.model_validate(row)
