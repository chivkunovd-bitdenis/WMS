from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile, BillingRunIssue

REASONS = {
    "unpriced": "Нет тарифа",
    "missing_profile": "Нет реквизитов",
    "storage_period_not_closed": "Хранение не закрыто",
}
MSK = ZoneInfo("Europe/Moscow")


def _month_bounds(period: date) -> tuple[datetime, datetime]:
    if period.day != 1:
        raise ValueError("Период счёта должен быть первым числом месяца")
    next_month = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    return (
        datetime.combine(period, datetime.min.time(), tzinfo=MSK).astimezone(UTC),
        datetime.combine(next_month, datetime.min.time(), tzinfo=MSK).astimezone(UTC),
    )


async def form_invoice(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, period: date
) -> BillingInvoice | BillingRunIssue:
    start, end = _month_bounds(period)
    today_msk = datetime.now(MSK).date()
    if period >= date(today_msk.year, today_msk.month, 1):
        raise ValueError("Счёт можно формировать только за закрытый месяц")
    existing = await session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.tenant_id == tenant_id,
            BillingInvoice.seller_id == seller_id,
            BillingInvoice.period == period,
        )
    )
    if existing:
        return existing
    entries = (
        await session.scalars(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                BillingLedgerEntry.seller_id == seller_id,
                BillingLedgerEntry.occurred_at >= start,
                BillingLedgerEntry.occurred_at < end,
            )
        )
    ).all()
    reason = None
    if any(e.amount is None for e in entries):
        reason = "unpriced"
    storage_entries = [e for e in entries if e.service_code == "storage_liter_day"]
    has_storage_statement = any(
        e.source_type in {"storage_statement", "storage_statement_closed"} for e in entries
    )
    if storage_entries and not has_storage_statement:
        reason = "storage_period_not_closed"
    ff = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id.is_(None)
        )
    )
    seller = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id == seller_id
        )
    )
    if ff is None or seller is None:
        reason = "missing_profile"
    if reason:
        issue = await session.scalar(
            select(BillingRunIssue).where(
                BillingRunIssue.tenant_id == tenant_id,
                BillingRunIssue.seller_id == seller_id,
                BillingRunIssue.period == period,
                BillingRunIssue.reason == reason,
            )
        )
        if issue:
            return issue
        issue = BillingRunIssue(
            tenant_id=tenant_id,
            seller_id=seller_id,
            period=period,
            reason=reason,
            message=REASONS[reason],
        )
        session.add(issue)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            recovered = await session.scalar(select(BillingRunIssue).where(
                BillingRunIssue.tenant_id == tenant_id,
                BillingRunIssue.seller_id == seller_id,
                BillingRunIssue.period == period,
                BillingRunIssue.reason == reason,
            ))
            assert recovered is not None
            return recovered
        return issue
    assert ff is not None and seller is not None
    grouped: dict[tuple[str, str, Decimal], dict[str, Any]] = {}
    for entry in entries:
        if entry.amount is None:
            continue
        key = (entry.service_code, entry.unit, entry.rate or Decimal("0"))
        row = grouped.setdefault(
            key, {"quantity": Decimal("0"), "amount": Decimal("0"), "documents": []}
        )
        row["quantity"] += entry.quantity
        row["amount"] += entry.amount
        row["documents"].append({
            "id": str(entry.id), "source_type": entry.source_type,
            "source_id": str(entry.source_id), "quantity": str(entry.quantity),
            "amount": str(entry.amount), "occurred_at": entry.occurred_at.isoformat(),
            "performer_id": str(entry.performer_id) if entry.performer_id else None,
        })
    fields = (
        "legal_name",
        "inn",
        "kpp",
        "bank_name",
        "bik",
        "settlement_account",
        "correspondent_account",
    )
    def snapshot(profile: BillingProfile) -> dict[str, Any]:
        return {key: getattr(profile, key) for key in fields}
    invoice = BillingInvoice(
        tenant_id=tenant_id,
        seller_id=seller_id,
        number=f"INV-{period:%Y%m}-{seller_id.hex[:8]}",
        period=period,
        status="issued",
        total_amount=sum((v["amount"] for v in grouped.values()), Decimal("0")),
        ff_profile_snapshot=snapshot(ff),
        seller_profile_snapshot=snapshot(seller),
        lines=[
            {
                "service_code": k[0],
                "unit": k[1],
                "rate": str(k[2]),
                "quantity": str(v["quantity"]),
                "amount": str(v["amount"]),
                "documents": v["documents"],
            }
            for k, v in grouped.items()
        ],
    )
    session.add(invoice)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        winner = await session.scalar(select(BillingInvoice).where(
            BillingInvoice.tenant_id == tenant_id,
            BillingInvoice.seller_id == seller_id,
            BillingInvoice.period == period,
        ))
        if winner is None:
            raise
        return winner
    return invoice


async def record_reversal(
    session: AsyncSession, *, original: BillingLedgerEntry, source_id: uuid.UUID,
    occurred_at: datetime, performer_id: uuid.UUID | None = None,
) -> BillingLedgerEntry:
    existing = await session.scalar(select(BillingLedgerEntry).where(
        BillingLedgerEntry.tenant_id == original.tenant_id,
        BillingLedgerEntry.source_type == "reversal",
        BillingLedgerEntry.source_id == source_id,
    ))
    if existing:
        return existing
    reversal = BillingLedgerEntry(
        tenant_id=original.tenant_id, seller_id=original.seller_id,
        tariff_version_id=original.tariff_version_id, reversal_of_id=original.id,
        performer_id=performer_id, entry_type="reversal", service_code=original.service_code,
        source=original.source, source_type="reversal", source_id=source_id,
        unit=original.unit, quantity=-original.quantity,
        rate=original.rate, amount=-original.amount if original.amount is not None else None,
        occurred_at=occurred_at,
    )
    session.add(reversal)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        recovered = await session.scalar(select(BillingLedgerEntry).where(
            BillingLedgerEntry.tenant_id == original.tenant_id,
            BillingLedgerEntry.source_type == "reversal", BillingLedgerEntry.source_id == source_id,
        ))
        assert recovered is not None
        return recovered
    return reversal


async def cancel_invoice(
    session: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> BillingInvoice:
    invoice = await session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.id == invoice_id, BillingInvoice.tenant_id == tenant_id
        )
    )
    if invoice is None:
        raise ValueError("Счёт не найден")
    if invoice.status == "issued":
        invoice.status = "cancelled"
    return invoice
