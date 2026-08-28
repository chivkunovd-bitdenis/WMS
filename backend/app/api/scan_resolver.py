from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.scan_resolver_service import (
    ScanMatch,
    ScanResolverError,
    resolve_any_scan,
)

router = APIRouter(prefix="/operations/scan", tags=["operations"])


class ScanResolveOut(BaseModel):
    type: Literal[
        "cell",
        "pallet",
        "box",
        "cargo_place",
        "product",
        "fbs_order",
        "warehouse",
    ]
    id: uuid.UUID
    name: str
    warehouse_id: uuid.UUID | None


def _scan_out(match: ScanMatch) -> ScanResolveOut:
    return ScanResolveOut(
        type=match.type,
        id=match.id,
        name=match.name,
        warehouse_id=match.warehouse_id,
    )


@router.get("/resolve", response_model=ScanResolveOut)
async def resolve_scan(
    code: Annotated[str, Query(min_length=1, max_length=512)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ScanResolveOut:
    try:
        match = await resolve_any_scan(
            session,
            user.tenant_id,
            code,
            warehouse_id=warehouse_id,
        )
    except ScanResolverError as exc:
        http_status = (
            status.HTTP_409_CONFLICT
            if exc.code == "scan_ambiguous"
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(
            status_code=http_status,
            detail={
                "code": exc.code,
                "message": exc.message,
                "matches": [_scan_out(match).model_dump(mode="json") for match in exc.matches],
            },
        ) from None
    return _scan_out(match)
