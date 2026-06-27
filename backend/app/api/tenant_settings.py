from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.user import User
from app.services.tenant_settings_service import (
    get_tenant_settings,
    update_tenant_settings,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])


class TenantSettingsOut(BaseModel):
    address_storage_enabled: bool


class TenantSettingsPatch(BaseModel):
    address_storage_enabled: bool | None = None


@router.get("/settings", response_model=TenantSettingsOut)
async def read_tenant_settings(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TenantSettingsOut:
    try:
        data = await get_tenant_settings(session, user.tenant_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        ) from None
    return TenantSettingsOut(**data)


@router.patch("/settings", response_model=TenantSettingsOut)
async def patch_tenant_settings(
    body: TenantSettingsPatch,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TenantSettingsOut:
    if body.address_storage_enabled is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="no_fields_to_update",
        )
    try:
        data = await update_tenant_settings(
            session,
            user.tenant_id,
            address_storage_enabled=body.address_storage_enabled,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        ) from None
    return TenantSettingsOut(**data)
