from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_seller_permission, get_current_user, get_effective_seller_id
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.marketplace_account_service import (
    MarketplaceAccountError,
    MarketplaceAccountService,
    SellerNotFound,
)
from app.services.ozon_client import OzonValidationResult, validate_ozon_credentials
from app.services.seller_staff_permissions_service import PERM_SETTINGS


class OzonAccountStatusOut(BaseModel):
    marketplace: Literal["ozon"]
    connected: bool
    validation_status: Literal["not_configured", "valid", "invalid", "unavailable"]
    last_validated_at: datetime | None
    last_validation_error: str | None
    credentials_updated_at: datetime | None
    last_synced_at: datetime | None
    last_sync_error: str | None


class OzonAccountPutIn(BaseModel):
    """The only accepted credential shape; public responses never reuse it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    client_id: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1, max_length=4096)

    @field_validator("client_id", "api_key", mode="before")
    @classmethod
    def strip_and_require_value(cls, value: object, info: Any) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise PydanticCustomError(f"{info.field_name}_required", "required")
        return value.strip() if isinstance(value, str) else value


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code})


def _put_validation_error(errors: Sequence[dict[str, Any]]) -> JSONResponse:
    """Keep frozen blank/missing codes while Pydantic owns the request schema."""
    by_field = {tuple(error.get("loc", ())): error for error in errors}
    for field, code in (("client_id", "client_id_required"), ("api_key", "api_key_required")):
        error = by_field.get(("body", field))
        if error is not None and error.get("type") in {"missing", code}:
            return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, code)
    return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_payload")


class _OzonIntegrationRoute(APIRoute):
    """Limit the frozen error envelope to this integration route family."""

    def get_route_handler(self) -> Any:
        route_handler = super().get_route_handler()

        async def handler(request: Any) -> Any:
            try:
                return await route_handler(request)
            except RequestValidationError as exc:
                return _put_validation_error(exc.errors())

        return handler


router = APIRouter(
    prefix="/integrations/ozon", tags=["integrations"], route_class=_OzonIntegrationRoute
)


async def _scope(
    user: User,
    session: AsyncSession,
    effective_seller_id: uuid.UUID | None,
) -> uuid.UUID:
    await assert_seller_permission(session, user, PERM_SETTINGS)
    if user.role != FULFILLMENT_SELLER or effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return effective_seller_id


def _validation_failure(result: OzonValidationResult) -> tuple[int, str, str, str | None]:
    if result.transport_failed:
        return 503, "ozon_validation_unavailable", "unavailable", "transport_error"
    if result.status_code in (401, 403):
        return 422, "ozon_credentials_invalid", "invalid", "credentials_invalid"
    if result.status_code == 429:
        return 503, "ozon_validation_unavailable", "unavailable", "rate_limited"
    if result.status_code is not None and 500 <= result.status_code < 600:
        return 503, "ozon_validation_unavailable", "unavailable", "provider_unavailable"
    return 502, "ozon_validation_failed", "unavailable", "unexpected_status"


@router.get("/self/account", response_model=OzonAccountStatusOut)
async def get_self_account(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> OzonAccountStatusOut:
    seller_id = await _scope(user, session, effective_seller_id)
    service = MarketplaceAccountService(session)
    try:
        return OzonAccountStatusOut.model_validate(
            await service.public_status(user.tenant_id, seller_id)
        )
    except SellerNotFound:
        raise HTTPException(status_code=404, detail="seller_not_found") from None


@router.put("/self/account", response_model=OzonAccountStatusOut)
async def put_self_account(
    candidate: OzonAccountPutIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> OzonAccountStatusOut | JSONResponse:
    seller_id = await _scope(user, session, effective_seller_id)
    result = await validate_ozon_credentials(candidate.client_id, candidate.api_key)
    if result.status_code is None or not 200 <= result.status_code < 300:
        _, code, _, _ = _validation_failure(result)
        return _error(_validation_failure(result)[0], code)
    service = MarketplaceAccountService(session)
    try:
        saved = await service.save_validated_candidate(
            user.tenant_id, seller_id, user.id, candidate.client_id, candidate.api_key
        )
    except SellerNotFound:
        raise HTTPException(status_code=404, detail="seller_not_found") from None
    return OzonAccountStatusOut.model_validate(saved.status)


@router.post("/self/account/test-connection", response_model=OzonAccountStatusOut)
async def test_self_account(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> OzonAccountStatusOut | JSONResponse:
    seller_id = await _scope(user, session, effective_seller_id)
    raw = await request.body()
    if raw:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return _error(422, "invalid_payload")
        if decoded is not None:
            return _error(422, "invalid_payload")
    service = MarketplaceAccountService(session)
    try:
        client_id, api_key = await service.stored_credentials(user.tenant_id, seller_id)
    except SellerNotFound:
        raise HTTPException(status_code=404, detail="seller_not_found") from None
    except MarketplaceAccountError as exc:
        return _error(409, exc.code)
    result = await validate_ozon_credentials(client_id, api_key)
    if result.status_code is not None and 200 <= result.status_code < 300:
        stored = await service.update_stored_validation(
            user.tenant_id, seller_id, user.id, validation_status="valid", error_code=None
        )
        return OzonAccountStatusOut.model_validate(stored)
    http_status, code, validation_status, error_code = _validation_failure(result)
    await service.update_stored_validation(
        user.tenant_id, seller_id, user.id,
        validation_status=validation_status, error_code=error_code,
    )
    return _error(http_status, code)


@router.delete("/self/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_self_account(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> Response:
    seller_id = await _scope(user, session, effective_seller_id)
    service = MarketplaceAccountService(session)
    try:
        await service.disconnect(user.tenant_id, seller_id, user.id)
    except SellerNotFound:
        raise HTTPException(status_code=404, detail="seller_not_found") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
