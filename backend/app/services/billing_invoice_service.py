from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile, BillingRunIssue

REASONS = {
    "unpriced": "Нет тарифа",
    "missing_profile": "Нет реквизитов",
    "storage_period_not_closed": "Хранение не закрыто",
}


async def form_invoice(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, period: date
) -> BillingInvoice | BillingRunIssue:
    existing = await session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.tenant_id == tenant_id,
            BillingInvoice.seller_id == seller_id,
            BillingInvoice.period == period,
        )
    )
    if existing:
        return existing
    start = datetime(period.year, period.month, 1, tzinfo=UTC)
    end = datetime(period.year + (period.month == 12), (period.month % 12) + 1, 1, tzinfo=UTC)
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
    if any(e.source_type == "storage_period_open" for e in entries):
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
        return issue
    assert ff is not None and seller is not None
    grouped: dict[tuple[str, str, Decimal], dict[str, Decimal]] = {}
    for entry in entries:
        if entry.amount is None:
            continue
        key = (entry.service_code, entry.unit, entry.rate or Decimal("0"))
        row = grouped.setdefault(key, {"quantity": Decimal("0"), "amount": Decimal("0")})
        row["quantity"] += entry.quantity
        row["amount"] += entry.amount
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
            }
            for k, v in grouped.items()
        ],
    )
    session.add(invoice)
    return invoice


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
