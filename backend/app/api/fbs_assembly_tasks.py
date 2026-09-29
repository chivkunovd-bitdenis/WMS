from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_effective_seller_id, require_fbs_operator_access
from app.db.session import get_db
from app.models.user import User
from app.services import fbs_assembly_task_service as assembly_task_svc

router = APIRouter(prefix="/operations/fbs-assembly-tasks", tags=["operations"])


class FbsAssemblyTaskCreateBody(BaseModel):
    supply_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsAssemblyTaskAuthorOut(BaseModel):
    id: uuid.UUID | None
    name: str


class FbsAssemblyTaskSellerOut(BaseModel):
    id: uuid.UUID
    name: str


class FbsAssemblyTaskSupplyOut(BaseModel):
    id: uuid.UUID
    marketplace: Literal["wb", "ozon"]
    name: str
    seller: FbsAssemblyTaskSellerOut
    status: str
    orders_count: int
    picked_count: int
    units_count: int
    picked_units_count: int
    packed_count: int


class FbsAssemblyTaskOut(BaseModel):
    id: uuid.UUID
    number: str
    created_at: datetime
    created_by: FbsAssemblyTaskAuthorOut
    supplies: list[FbsAssemblyTaskSupplyOut]


class FbsAssemblyTaskListOut(BaseModel):
    items: list[FbsAssemblyTaskOut]


def _raise_from_service(exc: assembly_task_svc.FbsAssemblyTaskError) -> None:
    detail: dict[str, object] = {
        "code": exc.code,
        "message": exc.message,
    }
    if exc.context:
        detail["context"] = exc.context
    raise HTTPException(status_code=exc.http_status, detail=detail)


@router.post("", response_model=FbsAssemblyTaskOut, status_code=status.HTTP_201_CREATED)
async def create_fbs_assembly_task(
    body: FbsAssemblyTaskCreateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> FbsAssemblyTaskOut:
    try:
        task_id = await assembly_task_svc.create_assembly_task(
            session,
            user.tenant_id,
            created_by_user_id=user.id,
            supply_ids=body.supply_ids,
            idempotency_key=body.idempotency_key,
            seller_id=effective_seller_id,
        )
        await session.commit()
        payload = await assembly_task_svc.get_assembly_task(
            session,
            user.tenant_id,
            task_id,
            seller_id=effective_seller_id,
        )
    except assembly_task_svc.FbsAssemblyTaskError as exc:
        _raise_from_service(exc)
    return FbsAssemblyTaskOut.model_validate(payload)


@router.get("", response_model=FbsAssemblyTaskListOut)
async def get_fbs_assembly_tasks(
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    marketplace: Annotated[str | None, Query(pattern="^(wb|ozon)$")] = None,
) -> FbsAssemblyTaskListOut:
    items = await assembly_task_svc.list_assembly_tasks(
        session,
        user.tenant_id,
        seller_id=effective_seller_id,
        marketplace=marketplace,
    )
    return FbsAssemblyTaskListOut.model_validate({"items": items})


@router.get("/{task_id}", response_model=FbsAssemblyTaskOut)
async def get_fbs_assembly_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> FbsAssemblyTaskOut:
    try:
        payload = await assembly_task_svc.get_assembly_task(
            session,
            user.tenant_id,
            task_id,
            seller_id=effective_seller_id,
        )
    except assembly_task_svc.FbsAssemblyTaskError as exc:
        _raise_from_service(exc)
    return FbsAssemblyTaskOut.model_validate(payload)
