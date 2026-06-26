from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_effective_seller_id, require_fulfillment_admin
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.seller_marking_credentials_service import (
    SKIP,
    MarkingCredentialsPublic,
    SecretPatchValue,
    SellerMarkingCredentialsError,
    _SkipSentinel,
    get_public_credentials,
    patch_seller_credentials,
)

router = APIRouter(
    prefix="/operations/marking-codes",
    tags=["operations"],
)

_ALLOWED_PATCH_KEYS = frozenset(
    {
        "cz_token",
        "suz_oms_token",
        "mp_api_key",
        "marketplace",
        "mchd_id",
        "mchd_valid_until",
        "signing_method",
        "edo_route",
        "auto_introduce",
        "auto_emit_limit",
    }
)


class MarkingCredentialsOut(BaseModel):
    seller_id: str | None = None
    has_cz_token: bool
    has_suz_oms_token: bool
    has_mp_api_key: bool
    marketplace: str | None
    mchd_id: str | None
    mchd_valid_until: date | None
    signing_method: str
    edo_route: str
    auto_introduce: bool
    auto_emit_limit: int | None
    updated_at: datetime | None


def _to_out(public: MarkingCredentialsPublic) -> MarkingCredentialsOut:
    return MarkingCredentialsOut(
        seller_id=str(public.seller_id),
        has_cz_token=public.has_cz_token,
        has_suz_oms_token=public.has_suz_oms_token,
        has_mp_api_key=public.has_mp_api_key,
        marketplace=public.marketplace,
        mchd_id=public.mchd_id,
        mchd_valid_until=public.mchd_valid_until,
        signing_method=public.signing_method,
        edo_route=public.edo_route,
        auto_introduce=public.auto_introduce,
        auto_emit_limit=public.auto_emit_limit,
        updated_at=public.updated_at,
    )


def _parse_secret_field(raw: dict[str, Any], field: str) -> SecretPatchValue:
    if field not in raw:
        return SKIP
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_token_type",
        )
    return value


def _parse_optional_str(raw: dict[str, Any], field: str) -> str | None | _SkipSentinel:
    if field not in raw:
        return SKIP
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid_{field}",
        )
    return value


def _parse_optional_date(raw: dict[str, Any], field: str) -> date | None | _SkipSentinel:
    if field not in raw:
        return SKIP
    value = raw[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid_{field}",
        )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid_{field}",
        ) from exc


def _parse_credentials_patch(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="expected_object",
        )
    body: dict[str, Any] = raw
    if set(body) - _ALLOWED_PATCH_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="unknown_fields",
        )
    signing_method: str | _SkipSentinel = SKIP
    if "signing_method" in body:
        value = body["signing_method"]
        if not isinstance(value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_signing_method",
            )
        signing_method = value

    edo_route: str | _SkipSentinel = SKIP
    if "edo_route" in body:
        value = body["edo_route"]
        if not isinstance(value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_edo_route",
            )
        edo_route = value

    auto_introduce: bool | _SkipSentinel = SKIP
    if "auto_introduce" in body:
        value = body["auto_introduce"]
        if not isinstance(value, bool):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_auto_introduce",
            )
        auto_introduce = value

    auto_emit_limit: int | None | _SkipSentinel = SKIP
    if "auto_emit_limit" in body:
        value = body["auto_emit_limit"]
        if value is None:
            auto_emit_limit = None
        elif isinstance(value, int):
            auto_emit_limit = value
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_auto_emit_limit",
            )

    return {
        "cz_token": _parse_secret_field(body, "cz_token"),
        "suz_oms_token": _parse_secret_field(body, "suz_oms_token"),
        "mp_api_key": _parse_secret_field(body, "mp_api_key"),
        "marketplace": _parse_optional_str(body, "marketplace"),
        "mchd_id": _parse_optional_str(body, "mchd_id"),
        "mchd_valid_until": _parse_optional_date(body, "mchd_valid_until"),
        "signing_method": signing_method,
        "edo_route": edo_route,
        "auto_introduce": auto_introduce,
        "auto_emit_limit": auto_emit_limit,
    }


async def _patch_and_respond(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    patch: dict[str, Any],
) -> MarkingCredentialsOut:
    try:
        row = await patch_seller_credentials(session, tenant_id, seller_id, **patch)
    except SellerMarkingCredentialsError as exc:
        if exc.code in (
            "empty_patch",
            "token_empty",
            "invalid_token_type",
            "invalid_marketplace",
            "invalid_signing_method",
            "invalid_edo_route",
            "invalid_auto_emit_limit",
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from exc
        raise
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    public = await get_public_credentials(session, tenant_id, seller_id)
    assert public is not None
    return _to_out(public)


@router.get("/sellers/{seller_id}/credentials", response_model=MarkingCredentialsOut)
async def get_seller_marking_credentials(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingCredentialsOut:
    """Маска наличия токенов и настроек (секреты не отдаются)."""
    public = await get_public_credentials(session, user.tenant_id, seller_id)
    if public is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    return _to_out(public)


@router.get("/self/credentials", response_model=MarkingCredentialsOut)
async def get_self_marking_credentials(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MarkingCredentialsOut:
    if user.role != FULFILLMENT_SELLER or effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    public = await get_public_credentials(session, user.tenant_id, effective_seller_id)
    if public is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    out = _to_out(public)
    return MarkingCredentialsOut(
        seller_id=None,
        has_cz_token=out.has_cz_token,
        has_suz_oms_token=out.has_suz_oms_token,
        has_mp_api_key=out.has_mp_api_key,
        marketplace=out.marketplace,
        mchd_id=out.mchd_id,
        mchd_valid_until=out.mchd_valid_until,
        signing_method=out.signing_method,
        edo_route=out.edo_route,
        auto_introduce=out.auto_introduce,
        auto_emit_limit=out.auto_emit_limit,
        updated_at=out.updated_at,
    )


@router.patch("/sellers/{seller_id}/credentials", response_model=MarkingCredentialsOut)
async def patch_seller_marking_credentials(
    seller_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingCredentialsOut:
    try:
        raw = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_json",
        ) from exc
    patch = _parse_credentials_patch(raw)
    return await _patch_and_respond(session, user.tenant_id, seller_id, patch)


@router.patch("/self/credentials", response_model=MarkingCredentialsOut)
async def patch_self_marking_credentials(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MarkingCredentialsOut:
    if user.role != FULFILLMENT_SELLER or effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        raw = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_json",
        ) from exc
    patch = _parse_credentials_patch(raw)
    out = await _patch_and_respond(session, user.tenant_id, effective_seller_id, patch)
    return MarkingCredentialsOut(
        seller_id=None,
        has_cz_token=out.has_cz_token,
        has_suz_oms_token=out.has_suz_oms_token,
        has_mp_api_key=out.has_mp_api_key,
        marketplace=out.marketplace,
        mchd_id=out.mchd_id,
        mchd_valid_until=out.mchd_valid_until,
        signing_method=out.signing_method,
        edo_route=out.edo_route,
        auto_introduce=out.auto_introduce,
        auto_emit_limit=out.auto_emit_limit,
        updated_at=out.updated_at,
    )
