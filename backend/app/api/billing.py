from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.billing import (
    BillingInvoice,
    BillingLedgerEntry,
    BillingProfile,
    BillingRunIssue,
    BillingTariffVersion,
)
from app.models.seller import Seller
from app.models.user import User
from app.services.billing_configuration_service import (
    BillingConfigurationError,
    assert_seller_in_tenant,
    create_tariff,
    save_profile,
)
from app.services.billing_invoice_service import (
    _month_bounds,
    _source_numbers,
    cancel_invoice,
    current_blocking_reasons,
    form_invoice,
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


def _month_period(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=422, detail="Период должен быть в формате YYYY-MM"
            ) from exc
        return parsed.replace(day=1)


def _seller_filter(value: str | None) -> uuid.UUID | None:
    if value in (None, "", "all"):
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Некорректный селлер") from exc


def _query_period(period: str | None, date_value: str | None) -> date:
    if period is None and date_value is None:
        raise HTTPException(status_code=422, detail="Укажите месяц")
    if period is not None and date_value is not None:
        first = _month_period(period)
        second = _month_period(date_value)
        if first != second:
            raise HTTPException(status_code=422, detail="Переданы разные месяцы")
        return first
    return _month_period(period or date_value or "")


def _invoice_out(
    invoice: BillingInvoice,
    seller_name: str,
    issues: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": invoice.id, "number": invoice.number, "period": invoice.period,
        "status": invoice.status, "issued_at": invoice.issued_at,
        "total_amount": invoice.total_amount, "seller_id": invoice.seller_id,
        "seller_name": seller_name, "ff_profile": invoice.ff_profile_snapshot,
        "seller_profile": invoice.seller_profile_snapshot, "lines": invoice.lines,
        "issues": issues or [],
    }


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
    try:
        await assert_seller_in_tenant(session, tenant_id=user.tenant_id, seller_id=seller_id)
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
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
    except IntegrityError as exc:
        await session.rollback()
        raise _error(BillingConfigurationError("Дата пересекает будущую версию ставки")) from exc


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
    period: str | None = None,
    date: str | None = None,
    seller_id: str | None = None,
    service_code: str | None = None,
    mode: str | None = None,
    document_number: str | None = None,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, list[dict[str, Any]]]:
    del mode  # grouping is intentionally a presentation concern.
    month = _query_period(period, date)
    start, end = _month_bounds(month)
    requested_seller = _seller_filter(seller_id)
    query = select(BillingLedgerEntry, Seller.name, User.email).outerjoin(
        Seller, BillingLedgerEntry.seller_id == Seller.id
    ).outerjoin(User, BillingLedgerEntry.performer_id == User.id).where(
        BillingLedgerEntry.tenant_id == user.tenant_id,
        BillingLedgerEntry.occurred_at >= start,
        BillingLedgerEntry.occurred_at < end,
    )
    if requested_seller is not None:
        query = query.where(BillingLedgerEntry.seller_id == requested_seller)
    if service_code not in (None, "", "all"):
        query = query.where(BillingLedgerEntry.service_code == service_code)
    rows = (await session.execute(query.order_by(BillingLedgerEntry.occurred_at))).all()
    ledger_rows = [row for row, _seller_name, _performer_name in rows]
    source_numbers = await _source_numbers(session, ledger_rows, month)
    source_refs = {
        row.id: (row.source_type, row.source_id)
        for row in ledger_rows
    }
    reversal_ids = {
        row.reversal_of_id for row in ledger_rows if row.reversal_of_id is not None
    }
    if reversal_ids:
        originals = await session.execute(
            select(
                BillingLedgerEntry.id,
                BillingLedgerEntry.source_type,
                BillingLedgerEntry.source_id,
            ).where(
                BillingLedgerEntry.tenant_id == user.tenant_id,
                BillingLedgerEntry.id.in_(reversal_ids),
            )
        )
        original_source_refs = {
            entry_id: (source_type, source_id)
            for entry_id, source_type, source_id in originals
        }
        source_refs.update(
            {
                row.id: original_source_refs[row.reversal_of_id]
                for row in ledger_rows
                if row.reversal_of_id in original_source_refs
            }
        )
    entries = [{
        "id": row.id, "seller_id": row.seller_id, "seller_name": seller_name or "Не указан",
        "entry_type": row.entry_type, "service_code": row.service_code,
        "source_type": source_refs[row.id][0], "source_id": source_refs[row.id][1],
        "quantity": row.quantity, "unit": row.unit, "rate": row.rate,
        "amount": row.amount, "occurred_at": row.occurred_at,
        "performer_id": row.performer_id, "performer_name": performer_name,
        "document_number": source_numbers[row.id],
        "problem": "unpriced" if row.amount is None else None,
    } for row, seller_name, performer_name in rows]
    if document_number:
        entries = [
            entry
            for entry in entries
            if document_number.lower() in entry["document_number"].lower()
        ]
    return {"entries": entries}


@router.get("/invoices", response_model=None)
async def get_billing_invoices(
    *,
    period: str | None = None,
    seller_id: str | None = None,
    status: str | None = None,
    number: str | None = None,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, list[dict[str, Any]]]:
    query = select(BillingInvoice, Seller.name).join(
        Seller, BillingInvoice.seller_id == Seller.id
    ).where(BillingInvoice.tenant_id == user.tenant_id)
    if period is not None:
        query = query.where(BillingInvoice.period == _month_period(period))
    requested_seller = _seller_filter(seller_id)
    if requested_seller is not None:
        query = query.where(BillingInvoice.seller_id == requested_seller)
    if status not in (None, "", "all"):
        query = query.where(BillingInvoice.status == status)
    if number:
        query = query.where(BillingInvoice.number.ilike(f"%{number}%"))
    invoice_rows = (await session.execute(query.order_by(BillingInvoice.period.desc()))).all()
    invoices = [_invoice_out(invoice, seller_name) for invoice, seller_name in invoice_rows]
    issues_query = select(BillingRunIssue, Seller.name).join(
        Seller, BillingRunIssue.seller_id == Seller.id
    ).where(BillingRunIssue.tenant_id == user.tenant_id)
    if period is not None:
        issues_query = issues_query.where(BillingRunIssue.period == _month_period(period))
    if requested_seller is not None:
        issues_query = issues_query.where(BillingRunIssue.seller_id == requested_seller)
    issue_rows = (await session.execute(issues_query)).all()
    issues = []
    for issue, seller_name in issue_rows:
        live_reasons = await current_blocking_reasons(
            session,
            tenant_id=user.tenant_id,
            seller_id=issue.seller_id,
            period=issue.period,
        )
        if issue.reason not in live_reasons:
            continue
        issues.append(
            {
                "id": issue.id,
                "seller_id": issue.seller_id,
                "seller_name": seller_name,
                "period": issue.period,
                "reason": issue.reason,
                "message": issue.message,
            }
        )
    return {"invoices": invoices, "issues": issues}


@router.get("/invoices/{invoice_id}", response_model=None)
async def get_billing_invoice(
    invoice_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    row = (await session.execute(select(BillingInvoice, Seller.name).join(Seller).where(
        BillingInvoice.id == invoice_id, BillingInvoice.tenant_id == user.tenant_id,
    ))).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Счёт не найден")
    return _invoice_out(*row)


@router.post("/invoices/{seller_id}/{period}/form")
async def form_billing_invoice(
    seller_id: uuid.UUID,
    period: str,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        result = await form_invoice(
            session, tenant_id=user.tenant_id, seller_id=seller_id, period=_month_period(period)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    if result is None:
        return {"status": "empty"}
    if isinstance(result, BillingInvoice):
        return {
            "status": result.status,
            "id": result.id,
            "number": result.number,
            "total_amount": result.total_amount,
        }
    issues = result if isinstance(result, list) else [result]
    primary = issues[0]
    return {
        "status": "blocked",
        "reason": primary.reason,
        "message": primary.message,
        "reasons": [
            {"reason": issue.reason, "message": issue.message}
            for issue in issues
        ],
    }


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
