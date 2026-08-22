from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.models.tenant import Tenant

MOSCOW = ZoneInfo("Europe/Moscow")


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
) -> BillingLedgerEntry | None:
    """Record the first final operational fact, without blocking on a missing tariff."""
    fact_date = occurred_at.astimezone(MOSCOW).date()
    billing_enabled_from = await session.scalar(
        select(Tenant.billing_enabled_from).where(Tenant.id == tenant_id)
    )
    if billing_enabled_from is None or fact_date < billing_enabled_from:
        return None

    existing = await session.scalar(
        select(BillingLedgerEntry).where(
            BillingLedgerEntry.tenant_id == tenant_id,
            BillingLedgerEntry.source_type == source_type,
            BillingLedgerEntry.source_id == source_id,
            BillingLedgerEntry.entry_type == "charge",
        )
    )
    if existing is not None:
        return existing

    tariff = await session.scalar(
        select(BillingTariffVersion)
        .where(
            BillingTariffVersion.tenant_id == tenant_id,
            BillingTariffVersion.service_code == service_code,
            BillingTariffVersion.valid_from <= fact_date,
            (
                BillingTariffVersion.valid_to.is_(None)
                | (BillingTariffVersion.valid_to >= fact_date)
            ),
            (BillingTariffVersion.seller_id == seller_id)
            | BillingTariffVersion.seller_id.is_(None),
        )
        .order_by(BillingTariffVersion.seller_id.is_(None), BillingTariffVersion.valid_from.desc())
    )
    rate = tariff.amount if tariff is not None else None
    billed_quantity = Decimal("1") if tariff is not None and tariff.unit == "document" else quantity
    amount = None if rate is None else (rate * billed_quantity).quantize(Decimal("0.01"))
    entry = BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        tariff_version_id=tariff.id if tariff is not None else None,
        performer_id=performer_id,
        service_code=service_code,
        source=source,
        source_type=source_type,
        source_id=source_id,
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
        concurrent = await session.scalar(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.tenant_id == tenant_id,
                BillingLedgerEntry.source_type == source_type,
                BillingLedgerEntry.source_id == source_id,
                BillingLedgerEntry.entry_type == "charge",
            )
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await nested.commit()
        return entry
