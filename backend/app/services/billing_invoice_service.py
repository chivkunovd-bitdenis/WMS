from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingInvoice, BillingLedgerEntry, BillingProfile, BillingRunIssue
from app.models.seller import Seller

REASONS = {
    "unpriced": "Нет тарифа",
    "missing_profile": "Нет реквизитов",
    "storage_period_not_closed": "Хранение не закрыто",
    "no_entries": "Нет начислений для формирования",
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
    seller_in_tenant = await session.scalar(
        select(Seller.id).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
    )
    if seller_in_tenant is None:
        raise ValueError("Селлер не найден в текущем tenant")
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
    if not entries:
        reason = "no_entries"
    elif any(e.amount is None for e in entries):
        reason = "unpriced"
    storage_entries = [e for e in entries if e.service_code == "storage_liter_day"]
    if not storage_entries and reason is None:
        from app.models.billing import BillingTariffVersion

        storage_tariff = await session.scalar(select(BillingTariffVersion).where(
            BillingTariffVersion.tenant_id == tenant_id,
            BillingTariffVersion.service_code == "storage_liter_day",
            BillingTariffVersion.valid_from < end.date(),
            or_(BillingTariffVersion.valid_to.is_(None), BillingTariffVersion.valid_to >= period),
            (BillingTariffVersion.seller_id == seller_id)
            | BillingTariffVersion.seller_id.is_(None),
        ))
        if storage_tariff is not None:
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
            # The source id remains available for audits; a displayable number is
            # intentionally immutable even where old source tables have no number.
            "number": str(entry.source_id), "date": entry.occurred_at.date().isoformat(),
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
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{seller_id}:{period}:{k}")),
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
