from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.billing import BillingProfile, BillingTariffVersion
from app.models.user import User
from app.services.billing_configuration_service import (
    BillingConfigurationError,
    create_tariff,
    save_profile,
)

router = APIRouter(prefix="/billing", tags=["billing"])


class ProfileBody(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    inn: str
    kpp: str | None = None
    bank_name: str | None = None
    bik: str | None = None
    settlement_account: str | None = None
    correspondent_account: str | None = None


class ProfileOut(ProfileBody):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    seller_id: uuid.UUID | None

    @classmethod
    def from_model(cls, value: BillingProfile) -> ProfileOut:
        return cls.model_validate(value, from_attributes=True)


class TariffBody(BaseModel):
    seller_id: uuid.UUID | None = None
    service_code: str = Field(min_length=1, max_length=64)
    unit: str
    amount: Decimal = Field(ge=0, decimal_places=2, max_digits=14)
    valid_from: date


class TariffOut(TariffBody):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    valid_to: date | None

    @classmethod
    def from_model(cls, value: BillingTariffVersion) -> TariffOut:
        return cls.model_validate(value, from_attributes=True)


def _error(exc: BillingConfigurationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/profiles/ff", response_model=ProfileOut)
async def put_ff_profile(
    body: ProfileBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileOut:
    try:
        profile = await save_profile(
            session, tenant_id=user.tenant_id, seller_id=None, **body.model_dump()
        )
        await session.commit()
        return ProfileOut.from_model(profile)
    except BillingConfigurationError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.put("/profiles/sellers/{seller_id}", response_model=ProfileOut)
async def put_seller_profile(
    seller_id: uuid.UUID,
    body: ProfileBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProfileOut:
    try:
        profile = await save_profile(
            session, tenant_id=user.tenant_id, seller_id=seller_id, **body.model_dump()
        )
        await session.commit()
        return ProfileOut.from_model(profile)
    except BillingConfigurationError as exc:
        await session.rollback()
        raise _error(exc) from exc


@router.post("/tariffs", response_model=TariffOut, status_code=status.HTTP_201_CREATED)
async def post_tariff(
    body: TariffBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TariffOut:
    try:
        tariff = await create_tariff(session, tenant_id=user.tenant_id, **body.model_dump())
        await session.commit()
        return TariffOut.from_model(tariff)
    except BillingConfigurationError as exc:
        await session.rollback()
        raise _error(exc) from exc
