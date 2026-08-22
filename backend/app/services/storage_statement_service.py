from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement


class StorageStatementError(ValueError):
    pass


def _billing_models() -> tuple[type, type]:
    """Load the shared billing models without inventing a storage ledger."""
    try:
        from app.models.billing import BillingLedgerEntry, BillingTariffVersion
    except ImportError as exc:
        raise StorageStatementError("billing_models_unavailable") from exc
    return BillingTariffVersion, BillingLedgerEntry


async def fix_storage_statement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statement_id: uuid.UUID,
) -> StorageStatement:
    """Fix one clean draft and publish its ledger rows in the same transaction."""
    statement = await session.scalar(
        select(StorageStatement)
        .where(StorageStatement.id == statement_id, StorageStatement.tenant_id == tenant_id)
        .with_for_update()
    )
    if statement is None:
        raise StorageStatementError("not_found")
    if statement.status == "fixed":
        return statement
    if statement.status != "draft":
        raise StorageStatementError("not_editable")

    measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement)
                .where(StorageMeasurement.tenant_id == tenant_id)
                .where(StorageMeasurement.seller_id == statement.seller_id)
                .where(StorageMeasurement.warehouse_id == statement.warehouse_id)
                .where(StorageMeasurement.period_start == statement.period_start)
                .where(StorageMeasurement.period_end == statement.period_end)
                .order_by(StorageMeasurement.id)
            )
        ).all()
    )
    if any(row.status != "calculated" for row in measurements):
        raise StorageStatementError("missing_dimensions")

    BillingTariffVersion, BillingLedgerEntry = _billing_models()
    tariff = await session.scalar(
        select(BillingTariffVersion)
        .where(BillingTariffVersion.tenant_id == tenant_id)
        .where(BillingTariffVersion.warehouse_id == statement.warehouse_id)
        .where(BillingTariffVersion.service_code == "storage_liter_day")
        .where(BillingTariffVersion.unit == "liter_day")
        .where(BillingTariffVersion.effective_from <= statement.period_end)
        .where(
            or_(
                BillingTariffVersion.seller_id.is_(None),
                BillingTariffVersion.seller_id == statement.seller_id,
            )
        )
        .order_by(BillingTariffVersion.effective_from.desc())
    )
    if tariff is None:
        raise StorageStatementError("tariff_not_found")

    for measurement in measurements:
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=statement.seller_id,
                service_code="storage_liter_day",
                unit="liter_day",
                source_type="storage_measurement",
                source_id=measurement.id,
                quantity=measurement.liter_days,
                rate_snapshot=tariff.rate,
                amount=Decimal(measurement.liter_days) * Decimal(tariff.rate),
                occurred_at=datetime.now(UTC),
            )
        )
    statement.status = "fixed"
    statement.fixed_at = datetime.now(UTC)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await session.scalar(
            select(StorageStatement).where(StorageStatement.id == statement_id)
        )
        if existing is not None and existing.status == "fixed":
            return existing
        raise StorageStatementError("already_fixed") from exc
    await session.refresh(statement)
    return statement


async def get_fixed_storage_statement(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> tuple[StorageStatement, list[StorageMeasurement]]:
    statement = await session.scalar(
        select(StorageStatement).where(
            StorageStatement.id == statement_id,
            StorageStatement.tenant_id == tenant_id,
            StorageStatement.status == "fixed",
        )
    )
    if statement is None:
        raise StorageStatementError("not_found")
    # Measurements are immutable input, but a fixed document is reconstructed
    # from its ledger rows so a later rebuild can never change the printout.
    _, BillingLedgerEntry = _billing_models()
    ledger_rows = list((await session.scalars(select(BillingLedgerEntry).where(
        BillingLedgerEntry.tenant_id == tenant_id,
        BillingLedgerEntry.seller_id == statement.seller_id,
        BillingLedgerEntry.source_type == "storage_measurement",
        BillingLedgerEntry.service_code == "storage_liter_day",
        BillingLedgerEntry.source_id.is_not(None),
    ).order_by(BillingLedgerEntry.id))).all())
    ids = [row.source_id for row in ledger_rows]
    rows = list((await session.scalars(select(StorageMeasurement).where(
        StorageMeasurement.tenant_id == tenant_id,
        StorageMeasurement.id.in_(ids) if ids else False,
    ).order_by(StorageMeasurement.id))).all())
    return statement, rows
