from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.models.tenant import Tenant

MOSCOW = ZoneInfo("Europe/Moscow")
POSTGRES_INTEGER_MIN = -(2**31)
POSTGRES_INTEGER_MAX = 2**31 - 1


class BillingLedgerError(ValueError):
    """A billing fact cannot be represented without corrupting its source transaction."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def postgres_numeric(
    value: Decimal, *, precision: int, scale: int, field: str
) -> Decimal:
    """Validate and normalize a Decimal before a PostgreSQL NUMERIC write."""
    if precision <= 0 or scale < 0 or scale > precision or not value.is_finite():
        raise BillingLedgerError(f"{field}_overflow")
    quantum = Decimal(1).scaleb(-scale)
    maximum = (Decimal(10) ** (precision - scale)) - quantum
    try:
        normalized = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise BillingLedgerError(f"{field}_overflow") from exc
    if abs(normalized) > maximum:
        raise BillingLedgerError(f"{field}_overflow")
    return normalized


def postgres_integer(value: Decimal, *, field: str) -> int:
    if not value.is_finite():
        raise BillingLedgerError(f"{field}_overflow")
    try:
        rounded = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise BillingLedgerError(f"{field}_overflow") from exc
    if not POSTGRES_INTEGER_MIN <= rounded <= POSTGRES_INTEGER_MAX:
        raise BillingLedgerError(f"{field}_overflow")
    return rounded


async def resolve_active_tariff(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None,
    service_code: str,
    fact_date: date,
) -> BillingTariffVersion | None:
    """Resolve the most specific tariff while preserving explicit scope priority."""
    seller_scope = (
        BillingTariffVersion.seller_id.is_(None)
        if seller_id is None
        else (
            (BillingTariffVersion.seller_id == seller_id)
            | BillingTariffVersion.seller_id.is_(None)
        )
    )
    warehouse_scope = (
        BillingTariffVersion.warehouse_id.is_(None)
        if warehouse_id is None
        else (
            (BillingTariffVersion.warehouse_id == warehouse_id)
            | BillingTariffVersion.warehouse_id.is_(None)
        )
    )
    if warehouse_id is not None and seller_id is not None:
        specificity = case(
            (
                and_(
                    BillingTariffVersion.warehouse_id == warehouse_id,
                    BillingTariffVersion.seller_id == seller_id,
                ),
                0,
            ),
            (
                and_(
                    BillingTariffVersion.warehouse_id.is_(None),
                    BillingTariffVersion.seller_id == seller_id,
                ),
                1,
            ),
            (
                and_(
                    BillingTariffVersion.warehouse_id == warehouse_id,
                    BillingTariffVersion.seller_id.is_(None),
                ),
                2,
            ),
            else_=3,
        )
    elif warehouse_id is not None:
        specificity = case(
            (BillingTariffVersion.warehouse_id == warehouse_id, 0),
            else_=1,
        )
    elif seller_id is not None:
        specificity = case(
            (BillingTariffVersion.seller_id == seller_id, 0),
            else_=1,
        )
    else:
        specificity = case((BillingTariffVersion.id.is_not(None), 0), else_=1)

    return cast(
        BillingTariffVersion | None,
        await session.scalar(
            select(BillingTariffVersion)
            .where(
                BillingTariffVersion.tenant_id == tenant_id,
                BillingTariffVersion.service_code == service_code,
                BillingTariffVersion.valid_from <= fact_date,
                (
                    BillingTariffVersion.valid_to.is_(None)
                    | (BillingTariffVersion.valid_to >= fact_date)
                ),
                seller_scope,
                warehouse_scope,
            )
            .order_by(specificity, BillingTariffVersion.valid_from.desc())
        ),
    )


async def _active_charge_for_source(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> BillingLedgerEntry | None:
    """Return the only charge for a source that has not been reversed."""
    charge = aliased(BillingLedgerEntry)
    reversal = aliased(BillingLedgerEntry)
    return cast(
        BillingLedgerEntry | None,
        await session.scalar(
            select(charge)
            .outerjoin(reversal, reversal.reversal_of_id == charge.id)
            .where(
                charge.tenant_id == tenant_id,
                charge.source_type == source_type,
                charge.source_id == source_id,
                charge.entry_type == "charge",
                reversal.id.is_(None),
            )
            .order_by(charge.occurred_at.desc(), charge.id.desc())
        ),
    )


async def _latest_reversal_for_source(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> BillingLedgerEntry | None:
    """Return the latest immutable reversal in a source's charge history."""
    charge = aliased(BillingLedgerEntry)
    reversal = aliased(BillingLedgerEntry)
    return cast(
        BillingLedgerEntry | None,
        await session.scalar(
            select(reversal)
            .join(charge, reversal.reversal_of_id == charge.id)
            .where(
                charge.tenant_id == tenant_id,
                charge.source_type == source_type,
                charge.source_id == source_id,
                charge.entry_type == "charge",
            )
            .order_by(reversal.occurred_at.desc(), reversal.id.desc())
        ),
    )


async def record_operational_charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    source_type: str,
    source_id: uuid.UUID,
    source: str,
    service_code: str,
    quantity: Decimal,
    occurred_at: datetime,
    performer_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
) -> BillingLedgerEntry | None:
    """Record the first final operational fact, without blocking on a missing tariff."""
    fact_date = occurred_at.astimezone(MOSCOW).date()
    billing_enabled_from = await session.scalar(
        select(Tenant.billing_enabled_from).where(Tenant.id == tenant_id)
    )
    if billing_enabled_from is None or fact_date < billing_enabled_from:
        return None

    existing = await _active_charge_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
    )
    if existing is not None:
        return existing

    previous_reversal = await _latest_reversal_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
    )
    event_kind = (
        "completed"
        if previous_reversal is None
        else f"completed_after_reversal:{previous_reversal.id}"
    )

    tariff = await resolve_active_tariff(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        service_code=service_code,
        fact_date=fact_date,
    )
    rate = tariff.amount if tariff is not None else None
    billed_quantity = Decimal("1") if tariff is not None and tariff.unit == "document" else quantity
    amount = (
        None
        if rate is None
        else int(
            (Decimal(rate) * billed_quantity).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    )
    entry = BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        tariff_version_id=tariff.id if tariff is not None else None,
        performer_id=performer_id,
        entry_type="charge",
        service_code=service_code,
        source=source,
        source_type=source_type,
        source_id=source_id,
        event_kind=event_kind,
        unit=tariff.unit if tariff is not None else "item",
        quantity=billed_quantity,
        rate=rate,
        amount=amount,
        occurred_at=occurred_at,
    )
    # The unique source-event constraint is the concurrency guard.  Flush in a
    # savepoint so a concurrent finalisation can safely turn its constraint
    # error into the already committed ledger row without aborting the caller's
    # warehouse transaction.
    nested = await session.begin_nested()
    try:
        session.add(entry)
        await session.flush()
    except IntegrityError:
        await nested.rollback()
        concurrent = await _active_charge_for_source(
            session,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await nested.commit()
        return entry


async def record_operational_reversal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    occurred_at: datetime,
    performer_id: uuid.UUID | None,
) -> BillingLedgerEntry | None:
    """Reverse a recorded final fact once, preserving its immutable tariff snapshot."""
    original = await _active_charge_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
    )
    if original is None:
        # Billing may have been disabled when the warehouse fact was recorded.
        # A repeated cancellation returns the historical reversal, without
        # creating a second correction.
        return await _latest_reversal_for_source(
            session,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
        )

    existing = await session.scalar(
        select(BillingLedgerEntry).where(
            BillingLedgerEntry.reversal_of_id == original.id,
        )
    )
    if existing is not None:
        return existing

    reversal = BillingLedgerEntry(
        tenant_id=original.tenant_id,
        seller_id=original.seller_id,
        warehouse_id=original.warehouse_id,
        tariff_version_id=original.tariff_version_id,
        reversal_of_id=original.id,
        performer_id=performer_id,
        entry_type="reversal",
        service_code=original.service_code,
        source=original.source,
        source_type="billing_reversal",
        source_id=original.id,
        event_kind=f"reversal:{original.id}",
        unit=original.unit,
        quantity=-original.quantity,
        rate=original.rate,
        amount=-original.amount if original.amount is not None else None,
        occurred_at=occurred_at,
    )
    nested = await session.begin_nested()
    try:
        session.add(reversal)
        await session.flush()
    except IntegrityError:
        await nested.rollback()
        concurrent = await session.scalar(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.reversal_of_id == original.id,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await nested.commit()
        return reversal
