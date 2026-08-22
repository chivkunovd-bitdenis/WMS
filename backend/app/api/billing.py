from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.billing import (
    BillingInvoice,
    BillingLedgerEntry,
    BillingProfile,
    BillingTariffVersion,
)
from app.models.user import User
from app.services.billing_configuration_service import (
    BillingConfigurationError,
    create_tariff,
    save_profile,
)
from app.services.billing_invoice_service import cancel_invoice, form_invoice

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


@router.get("/profiles/ff", response_model=ProfileOut | None)
async def get_ff_profile(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BillingProfile | None:
    return cast(BillingProfile | None, await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == user.tenant_id,
            BillingProfile.seller_id.is_(None),
        )
    ))


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


@router.get("/profiles/sellers/{seller_id}", response_model=ProfileOut | None)
async def get_seller_profile(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BillingProfile | None:
    return cast(BillingProfile | None, await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == user.tenant_id,
            BillingProfile.seller_id == seller_id,
        )
    ))


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


@router.get("/tariffs", response_model=list[TariffOut])
async def get_tariffs(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[TariffOut]:
    result = await session.scalars(
        select(BillingTariffVersion)
        .where(BillingTariffVersion.tenant_id == user.tenant_id)
        .order_by(BillingTariffVersion.valid_from.desc())
    )
    return [TariffOut.from_model(value) for value in result]


@router.get("/ledger")
async def get_billing_ledger(
    *,
    period: date,
    seller_id: uuid.UUID | None = None,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    start = period
    next_period = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    query = select(BillingLedgerEntry).where(
        BillingLedgerEntry.tenant_id == user.tenant_id,
        BillingLedgerEntry.occurred_at >= start,
        BillingLedgerEntry.occurred_at < next_period,
    )
    if seller_id is not None:
        query = query.where(BillingLedgerEntry.seller_id == seller_id)
    rows = (await session.scalars(query.order_by(BillingLedgerEntry.occurred_at))).all()
    return [{
        "id": row.id, "seller_id": row.seller_id, "service_code": row.service_code,
        "source_type": row.source_type, "source_id": row.source_id,
        "quantity": row.quantity, "unit": row.unit, "rate": row.rate,
        "amount": row.amount, "occurred_at": row.occurred_at,
        "performer_id": row.performer_id,
    } for row in rows]


@router.get("/invoices", response_model=None)
async def get_billing_invoices(
    *,
    period: date | None = None,
    seller_id: uuid.UUID | None = None,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[BillingInvoice]:
    query = select(BillingInvoice).where(BillingInvoice.tenant_id == user.tenant_id)
    if period is not None:
        query = query.where(BillingInvoice.period == period)
    if seller_id is not None:
        query = query.where(BillingInvoice.seller_id == seller_id)
    return list((await session.scalars(query.order_by(BillingInvoice.period.desc()))).all())


@router.get("/invoices/{invoice_id}", response_model=None)
async def get_billing_invoice(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BillingInvoice:
    invoice = await session.scalar(select(BillingInvoice).where(
        BillingInvoice.id == invoice_id, BillingInvoice.tenant_id == user.tenant_id,
    ))
    if invoice is None:
        raise HTTPException(status_code=404, detail="Счёт не найден")
    return invoice


@router.post("/invoices/{seller_id}/{period}/form")
async def form_billing_invoice(
    seller_id: uuid.UUID,
    period: date,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        result = await form_invoice(
            session, tenant_id=user.tenant_id, seller_id=seller_id, period=period
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    if isinstance(result, BillingInvoice):
        return {
            "status": result.status,
            "id": result.id,
            "number": result.number,
            "total_amount": result.total_amount,
        }
    return {"status": "blocked", "reason": result.reason, "message": result.message}


@router.post("/invoices/{invoice_id}/cancel")
async def cancel_billing_invoice(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        invoice = await cancel_invoice(session, tenant_id=user.tenant_id, invoice_id=invoice_id)
        await session.commit()
        return {"id": invoice.id, "status": invoice.status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
