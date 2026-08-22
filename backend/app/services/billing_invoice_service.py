from __future__ import annotations

import importlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.billing import (
    BillingInvoice,
    BillingLedgerEntry,
    BillingProfile,
    BillingRunIssue,
    BillingTariffVersion,
)
from app.models.inbound_intake import InboundIntakeRequest
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.seller import Seller

REASONS = {
    "unpriced": "Нет тарифа",
    "missing_profile": "Нет реквизитов",
    "storage_period_not_closed": "Хранение не закрыто",
    "no_entries": "Нет начислений для формирования",
}
BLOCKING_REASONS = frozenset({"unpriced", "missing_profile", "storage_period_not_closed"})
MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class _InvoiceInputs:
    entries: list[BillingLedgerEntry]
    ff_profile: BillingProfile | None
    seller_profile: BillingProfile | None
    reason: str | None


def _month_bounds(period: date) -> tuple[datetime, datetime]:
    if period.day != 1:
        raise ValueError("Период счёта должен быть первым числом месяца")
    next_month = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    return (
        datetime.combine(period, datetime.min.time(), tzinfo=MSK).astimezone(UTC),
        datetime.combine(next_month, datetime.min.time(), tzinfo=MSK).astimezone(UTC),
    )


async def _storage_source_ids(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    period: date,
) -> tuple[bool, set[uuid.UUID]]:
    """Return readiness and the ledger source ids published by every storage statement.

    Storage is owned by card 08 and can be merged after this card.  Until its
    models are present, an active storage tariff fails closed instead of allowing
    an incomplete immutable invoice.
    """
    next_month = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
    period_end = next_month - timedelta(days=1)
    tariff = await session.scalar(
        select(BillingTariffVersion.id).where(
            BillingTariffVersion.tenant_id == tenant_id,
            BillingTariffVersion.service_code == "storage_liter_day",
            BillingTariffVersion.valid_from <= period_end,
            or_(BillingTariffVersion.valid_to.is_(None), BillingTariffVersion.valid_to >= period),
            or_(
                BillingTariffVersion.seller_id == seller_id,
                BillingTariffVersion.seller_id.is_(None),
            ),
        )
    )
    if tariff is None:
        return True, set()

    try:
        statement_model = importlib.import_module(
            "app.models.storage_statement"
        ).StorageStatement
        measurement_model = importlib.import_module(
            "app.models.storage_measurement"
        ).StorageMeasurement
        warehouse_model = importlib.import_module("app.models.warehouse").Warehouse
        operational_column = warehouse_model.is_operational
    except (AttributeError, ModuleNotFoundError):
        return False, set()

    warehouse_ids = set(
        (
            await session.scalars(
                select(warehouse_model.id).where(
                    warehouse_model.tenant_id == tenant_id,
                    operational_column.is_(True),
                )
            )
        ).all()
    )
    if not warehouse_ids:
        return True, set()

    statements = list(
        (
            await session.scalars(
                select(statement_model).where(
                    statement_model.tenant_id == tenant_id,
                    statement_model.seller_id == seller_id,
                    statement_model.warehouse_id.in_(warehouse_ids),
                    statement_model.period_start == period,
                    statement_model.period_end == period_end,
                    statement_model.status == "fixed",
                )
            )
        ).all()
    )
    if {statement.warehouse_id for statement in statements} != warehouse_ids:
        return False, set()

    source_ids: set[uuid.UUID] = set()
    for statement in statements:
        measurement_ids = set(
            (
                await session.scalars(
                    select(measurement_model.id).where(
                        measurement_model.tenant_id == tenant_id,
                        measurement_model.seller_id == seller_id,
                        measurement_model.warehouse_id == statement.warehouse_id,
                        measurement_model.period_start == period,
                        measurement_model.period_end == period_end,
                    )
                )
            ).all()
        )
        source_ids.update(measurement_ids or {statement.id})

    published_ids = set(
        (
            await session.scalars(
                select(BillingLedgerEntry.source_id).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == seller_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code == "storage_liter_day",
                    BillingLedgerEntry.source_id.in_(source_ids),
                )
            )
        ).all()
    )
    return published_ids == source_ids, source_ids


async def _invoice_inputs(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    period: date,
) -> _InvoiceInputs:
    start, end = _month_bounds(period)
    storage_ready, storage_source_ids = await _storage_source_ids(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=period,
    )
    period_clause: ColumnElement[bool] = (
        (BillingLedgerEntry.occurred_at >= start) & (BillingLedgerEntry.occurred_at < end)
    )
    if storage_source_ids:
        period_clause = or_(
            period_clause,
            (
                (BillingLedgerEntry.source_type == "storage_measurement")
                & BillingLedgerEntry.source_id.in_(storage_source_ids)
            ),
        )
    entries = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == seller_id,
                    period_clause,
                )
            )
        ).all()
    )
    if not entries:
        return _InvoiceInputs([], None, None, "no_entries")

    ff_profile = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id,
            BillingProfile.seller_id.is_(None),
        )
    )
    seller_profile = await session.scalar(
        select(BillingProfile).where(
            BillingProfile.tenant_id == tenant_id,
            BillingProfile.seller_id == seller_id,
        )
    )
    reason: str | None = None
    if ff_profile is None or seller_profile is None:
        reason = "missing_profile"
    elif any(entry.amount is None for entry in entries):
        reason = "unpriced"
    elif not storage_ready:
        reason = "storage_period_not_closed"
    return _InvoiceInputs(entries, ff_profile, seller_profile, reason)


async def current_blocking_reason(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    period: date,
) -> str | None:
    """Re-evaluate an old issue so the read model never exposes a stale blocker."""
    reason = (await _invoice_inputs(
        session, tenant_id=tenant_id, seller_id=seller_id, period=period
    )).reason
    return reason if reason in BLOCKING_REASONS else None


async def _replace_issue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    period: date,
    reason: str | None,
) -> BillingRunIssue | None:
    issue_scope = (
        BillingRunIssue.tenant_id == tenant_id,
        BillingRunIssue.seller_id == seller_id,
        BillingRunIssue.period == period,
    )
    if reason not in BLOCKING_REASONS:
        await session.execute(delete(BillingRunIssue).where(*issue_scope))
        return None
    await session.execute(
        delete(BillingRunIssue).where(
            *issue_scope,
            BillingRunIssue.reason != reason,
        )
    )
    existing = await session.scalar(
        select(BillingRunIssue).where(
            BillingRunIssue.tenant_id == tenant_id,
            BillingRunIssue.seller_id == seller_id,
            BillingRunIssue.period == period,
            BillingRunIssue.reason == reason,
        )
    )
    if existing is not None:
        return existing
    issue = BillingRunIssue(
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=period,
        reason=reason,
        message=REASONS[reason],
    )
    savepoint = await session.begin_nested()
    try:
        session.add(issue)
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        concurrent = await session.scalar(
            select(BillingRunIssue).where(
                *issue_scope,
                BillingRunIssue.reason == reason,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await savepoint.commit()
        return issue


async def _source_numbers(
    session: AsyncSession,
    entries: list[BillingLedgerEntry],
    period: date,
) -> dict[uuid.UUID, str]:
    resolved = {entry.id: entry for entry in entries}
    reversal_ids = {entry.reversal_of_id for entry in entries if entry.reversal_of_id is not None}
    if reversal_ids:
        originals = (
            await session.scalars(
                select(BillingLedgerEntry).where(BillingLedgerEntry.id.in_(reversal_ids))
            )
        ).all()
        resolved.update({entry.id: entry for entry in originals})

    source_by_entry: dict[uuid.UUID, BillingLedgerEntry] = {}
    for entry in entries:
        source_by_entry[entry.id] = (
            resolved[entry.reversal_of_id] if entry.reversal_of_id is not None else entry
        )

    inbound_ids = {
        entry.source_id
        for entry in source_by_entry.values()
        if entry.source_type == "inbound_intake"
    }
    unload_ids = {
        entry.source_id
        for entry in source_by_entry.values()
        if entry.source_type == "marketplace_unload"
    }
    numbers: dict[tuple[str, uuid.UUID], str] = {}
    if inbound_ids:
        inbound_rows = (
            await session.scalars(
                select(InboundIntakeRequest).where(InboundIntakeRequest.id.in_(inbound_ids))
            )
        ).all()
        numbers.update(
            {
                ("inbound_intake", row.id): row.document_number or row.display_number or str(row.id)
                for row in inbound_rows
            }
        )
    if unload_ids:
        unload_rows = (
            await session.scalars(
                select(MarketplaceUnloadRequest).where(MarketplaceUnloadRequest.id.in_(unload_ids))
            )
        ).all()
        numbers.update(
            {
                ("marketplace_unload", row.id): row.document_number
                or row.display_number
                or str(row.id)
                for row in unload_rows
            }
        )

    result: dict[uuid.UUID, str] = {}
    for entry in entries:
        source = source_by_entry[entry.id]
        if source.source_type == "storage_measurement":
            number = f"Расчёт хранения за {period:%Y-%m}"
        else:
            number = numbers.get((source.source_type, source.source_id), str(source.source_id))
        result[entry.id] = number
    return result


async def form_invoice(
    session: AsyncSession, *, tenant_id: uuid.UUID, seller_id: uuid.UUID, period: date
) -> BillingInvoice | BillingRunIssue:
    _month_bounds(period)
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
    if existing is not None:
        await _replace_issue(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            period=period,
            reason=None,
        )
        return existing

    inputs = await _invoice_inputs(
        session, tenant_id=tenant_id, seller_id=seller_id, period=period
    )
    issue = await _replace_issue(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=period,
        reason=inputs.reason,
    )
    if inputs.reason is not None:
        return issue or BillingRunIssue(
            tenant_id=tenant_id,
            seller_id=seller_id,
            period=period,
            reason=inputs.reason,
            message=REASONS[inputs.reason],
        )

    assert inputs.ff_profile is not None and inputs.seller_profile is not None
    source_numbers = await _source_numbers(session, inputs.entries, period)
    grouped: dict[tuple[str, str, Decimal], dict[str, Any]] = {}
    for entry in inputs.entries:
        assert entry.amount is not None
        key = (entry.service_code, entry.unit, entry.rate or Decimal("0"))
        row = grouped.setdefault(
            key, {"quantity": Decimal("0"), "amount": Decimal("0"), "documents": []}
        )
        row["quantity"] += entry.quantity
        row["amount"] += entry.amount
        row["documents"].append(
            {
                "id": str(entry.id),
                "source_type": entry.source_type,
                "source_id": str(entry.source_id),
                "quantity": str(entry.quantity),
                "amount": str(entry.amount),
                "occurred_at": entry.occurred_at.isoformat(),
                "number": source_numbers[entry.id],
                "date": entry.occurred_at.date().isoformat(),
                "performer_id": str(entry.performer_id) if entry.performer_id else None,
            }
        )

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
        total_amount=sum((value["amount"] for value in grouped.values()), Decimal("0")),
        ff_profile_snapshot=snapshot(inputs.ff_profile),
        seller_profile_snapshot=snapshot(inputs.seller_profile),
        lines=[
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{seller_id}:{period}:{key}")),
                "service_code": key[0],
                "unit": key[1],
                "rate": str(key[2]),
                "quantity": str(value["quantity"]),
                "amount": str(value["amount"]),
                "documents": value["documents"],
            }
            for key, value in grouped.items()
        ],
    )
    savepoint = await session.begin_nested()
    try:
        session.add(invoice)
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        winner = await session.scalar(
            select(BillingInvoice).where(
                BillingInvoice.tenant_id == tenant_id,
                BillingInvoice.seller_id == seller_id,
                BillingInvoice.period == period,
            )
        )
        if winner is None:
            raise
        return winner
    else:
        await savepoint.commit()
        return invoice


async def cancel_invoice(
    session: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> BillingInvoice:
    invoice = await session.scalar(
        select(BillingInvoice).where(
            BillingInvoice.id == invoice_id,
            BillingInvoice.tenant_id == tenant_id,
        )
    )
    if invoice is None:
        raise ValueError("Счёт не найден")
    if invoice.status == "issued":
        invoice.status = "cancelled"
    return invoice
