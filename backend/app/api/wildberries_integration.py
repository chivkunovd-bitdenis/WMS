from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.core.settings import settings
from app.db.session import get_db
from app.models.user import User
from app.services.wildberries_credentials_service import (
    SKIP,
    TokenPatchValue,
    WildberriesCredentialsError,
    get_public_token_status,
    patch_seller_tokens,
)

router = APIRouter(prefix="/integrations/wildberries", tags=["integrations"])


class WildberriesStatusOut(BaseModel):
    content_api_base: str
    supplies_api_base: str
    import_only: bool = True


class WildberriesSellerTokensOut(BaseModel):
    seller_id: str
    has_content_token: bool
    has_supplies_token: bool
    updated_at: datetime | None


def _parse_token_merge_patch(raw: object) -> tuple[TokenPatchValue, TokenPatchValue]:
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_object",
        )
    allowed = {"content_api_token", "supplies_api_token"}
    if set(raw) - allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown_fields",
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="empty_patch",
        )
    content: TokenPatchValue = SKIP
    supplies: TokenPatchValue = SKIP
    if "content_api_token" in raw:
        val = raw["content_api_token"]
        if val is not None and not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_type:content_api_token",
            )
        content = val
    if "supplies_api_token" in raw:
        val = raw["supplies_api_token"]
        if val is not None and not isinstance(val, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_type:supplies_api_token",
            )
        supplies = val
    if content is SKIP and supplies is SKIP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="empty_patch",
        )
    return content, supplies


@router.get("/status", response_model=WildberriesStatusOut)
async def wildberries_status(
    _: Annotated[User, Depends(require_fulfillment_admin)],
) -> WildberriesStatusOut:
    """Публичная конфигурация (без токенов): базы URL для импорта WB."""
    return WildberriesStatusOut(
        content_api_base=settings.wildberries_content_api_base,
        supplies_api_base=settings.wildberries_supplies_api_base,
    )


@router.get("/sellers/{seller_id}/tokens", response_model=WildberriesSellerTokensOut)
async def get_seller_wildberries_tokens(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSellerTokensOut:
    """Маска наличия токенов (значения не отдаются)."""
    st = await get_public_token_status(session, user.tenant_id, seller_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    has_c, has_s, upd = st
    return WildberriesSellerTokensOut(
        seller_id=str(seller_id),
        has_content_token=has_c,
        has_supplies_token=has_s,
        updated_at=upd,
    )


@router.patch("/sellers/{seller_id}/tokens", response_model=WildberriesSellerTokensOut)
async def patch_seller_wildberries_tokens(
    seller_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WildberriesSellerTokensOut:
    """Частичное обновление: только переданные ключи JSON (null = удалить токен)."""
    try:
        raw = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_json",
        ) from exc
    content, supplies = _parse_token_merge_patch(raw)
    try:
        row = await patch_seller_tokens(
            session,
            user.tenant_id,
            seller_id,
            content_api_token=content,
            supplies_api_token=supplies,
        )
    except WildberriesCredentialsError as exc:
        if exc.code in ("empty_patch", "token_empty", "invalid_token_type"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=exc.code,
            ) from exc
        raise
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    st = await get_public_token_status(session, user.tenant_id, seller_id)
    assert st is not None
    has_c, has_s, upd = st
    return WildberriesSellerTokensOut(
        seller_id=str(seller_id),
        has_content_token=has_c,
        has_supplies_token=has_s,
        updated_at=upd,
    )
