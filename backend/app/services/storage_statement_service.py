from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse
from app.services.storage_measurement_service import (
    MOSCOW,
    _seconds,
    _volume_segments,
    calculation_end_exclusive,
)


class StorageStatementError(ValueError):
    pass


StorageDraftPricing = dict[
    uuid.UUID,
    tuple[Decimal, Decimal, BillingTariffVersion],
]


@dataclass(frozen=True)
class RepricedStorageDraft:
    statement: StorageStatement
    measurements: list[StorageMeasurement]
    pricing: StorageDraftPricing


def _statement_source_ids(
    statement: StorageStatement, measurements: list[StorageMeasurement]
) -> set[uuid.UUID]:
    """Return the ledger source ids that unambiguously belong to a statement.

    A non-empty statement is published one measurement at a time.  A zero
    statement has no measurement id, so its own id is the single source event.
    This keeps the shared ledger's source-id uniqueness useful without a
    storage-specific charge table or a nullable, ambiguous source id.
    """
    return {row.id for row in measurements} or {statement.id}


def _tariff_for_day(
    tariffs: list[BillingTariffVersion],
    on_day: date,
) -> BillingTariffVersion | None:
    """Choose the seller override first, then the common rate effective that day."""
    applicable = [
        tariff
        for tariff in tariffs
        if tariff.valid_from <= on_day and (tariff.valid_to is None or tariff.valid_to >= on_day)
    ]
    return max(
        applicable,
        key=lambda tariff: (
            tariff.seller_id is not None,
            tariff.valid_from,
            str(tariff.id),
        ),
        default=None,
    )


def _pricing_boundaries(
    start: datetime,
    end: datetime,
    tariffs: list[BillingTariffVersion],
) -> list[datetime]:
    boundaries = {start, end}
    for tariff in tariffs:
        valid_from = datetime.combine(tariff.valid_from, time.min, MOSCOW)
        if start < valid_from < end:
            boundaries.add(valid_from)
        if tariff.valid_to is not None:
            valid_to = datetime.combine(tariff.valid_to + timedelta(days=1), time.min, MOSCOW)
            if start < valid_to < end:
                boundaries.add(valid_to)
    return sorted(boundaries)


def _price_volume_segments(
    segments: Sequence[
        tuple[datetime, datetime, int, Decimal | None, ProductDimensionEvent | None]
    ],
    tariffs: list[BillingTariffVersion],
) -> tuple[Decimal, Decimal, BillingTariffVersion | None]:
    """Price actual liter-day intervals while keeping one ledger row per measurement.

    The shared ledger permits one source row for a storage measurement.  If a rate
    changes inside the month, ``amount`` is the exact sum of the dated intervals and
    ``rate`` is their weighted snapshot for the single immutable ledger row.
    """
    charged_quantity = Decimal(0)
    amount = Decimal(0)
    last_tariff: BillingTariffVersion | None = None
    for segment_start, segment_end, held, volume, _ in segments:
        if held <= 0 or volume is None:
            continue
        boundaries = _pricing_boundaries(segment_start, segment_end, tariffs)
        for left, right in pairwise(boundaries):
            tariff = _tariff_for_day(tariffs, left.astimezone(MOSCOW).date())
            if tariff is None:
                continue
            quantity = Decimal(held) * _seconds(left, right) * Decimal(volume)
            charged_quantity += quantity
            amount += quantity * Decimal(tariff.amount)
            last_tariff = tariff
    return charged_quantity, amount.quantize(Decimal("0.01")), last_tariff


async def _measurement_pricing(
    session: AsyncSession,
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
    tariffs: list[BillingTariffVersion],
) -> StorageDraftPricing:
    product_ids = {measurement.product_id for measurement in measurements}
    period_start_at = datetime.combine(statement.period_start, time.min, MOSCOW)
    period_end_at = calculation_end_exclusive(statement.period_start, statement.period_end)
    products = {
        product.id: product
        for product in (
            await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    }
    movements_by_product: dict[uuid.UUID, list[InventoryMovement]] = {}
    movements = (
        await session.scalars(
            select(InventoryMovement)
            .where(
                InventoryMovement.tenant_id == statement.tenant_id,
                InventoryMovement.seller_id == statement.seller_id,
                InventoryMovement.warehouse_id == statement.warehouse_id,
                InventoryMovement.product_id.in_(product_ids or {uuid.UUID(int=0)}),
                InventoryMovement.created_at < period_end_at,
            )
            .order_by(InventoryMovement.created_at, InventoryMovement.id)
        )
    ).all()
    for movement in movements:
        movements_by_product.setdefault(movement.product_id, []).append(movement)
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]] = {}
    events = (
        await session.scalars(
            select(ProductDimensionEvent)
            .where(
                ProductDimensionEvent.tenant_id == statement.tenant_id,
                ProductDimensionEvent.product_id.in_(product_ids or {uuid.UUID(int=0)}),
                ProductDimensionEvent.observed_at < period_end_at,
            )
            .order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id)
        )
    ).all()
    for event in events:
        events_by_product.setdefault(event.product_id, []).append(event)

    result: StorageDraftPricing = {}
    for measurement in measurements:
        product = products[measurement.product_id]
        segments = _volume_segments(
            movements_by_product.get(measurement.product_id, []),
            events_by_product.get(measurement.product_id, []),
            period_start_at,
            period_end_at,
            legacy_volume_liters=product.volume_liters,
        )
        charged_quantity, amount, last_tariff = _price_volume_segments(segments, tariffs)
        if last_tariff is None:
            # The dated tariff can intersect the statement even when this SKU
            # had no positive balance after the rate became effective.  Such a
            # row is a valid zero preview, not a reason to reject the tariff.
            last_tariff = _tariff_for_day(tariffs, statement.period_end)
        if last_tariff is None:
            raise StorageStatementError("tariff_not_found")
        result[measurement.id] = (charged_quantity, amount, last_tariff)
    return result


async def get_storage_draft_pricing(
    session: AsyncSession,
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
) -> StorageDraftPricing:
    """Calculate the current preview for an editable statement from dated tariffs."""
    tariffs = list(
        (
            await session.scalars(
                select(BillingTariffVersion).where(
                    BillingTariffVersion.tenant_id == statement.tenant_id,
                    BillingTariffVersion.service_code == "storage_liter_day",
                    BillingTariffVersion.unit == "liter_day",
                    BillingTariffVersion.warehouse_id == statement.warehouse_id,
                    BillingTariffVersion.valid_from <= statement.period_end,
                    or_(
                        BillingTariffVersion.valid_to.is_(None),
                        BillingTariffVersion.valid_to >= statement.period_start,
                    ),
                    or_(
                        BillingTariffVersion.seller_id.is_(None),
                        BillingTariffVersion.seller_id == statement.seller_id,
                    ),
                )
            )
        ).all()
    )
    if not tariffs:
        raise StorageStatementError("tariff_not_found")
    return await _measurement_pricing(session, statement, measurements, tariffs)


async def reprice_open_storage_drafts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    valid_from: date,
    seller_exception: tuple[uuid.UUID, Decimal, date] | None = None,
) -> list[RepricedStorageDraft]:
    """Recalculate every open draft intersected by newly added tariff versions.

    Draft amounts are deliberately not persisted: they are previews derived from
    measurements and the current dated tariffs.  Returning the previews from the
    tariff transaction makes the new values immediately available while keeping
    fixed statements and their ledger snapshots immutable.
    """
    affected_period = StorageStatement.period_end >= valid_from
    if seller_exception is not None:
        seller_id, _, seller_valid_from = seller_exception
        affected_period = or_(
            affected_period,
            and_(
                StorageStatement.seller_id == seller_id,
                StorageStatement.period_end >= seller_valid_from,
            ),
        )
    statements = list(
        (
            await session.scalars(
                select(StorageStatement)
                .options(
                    joinedload(StorageStatement.seller),
                    joinedload(StorageStatement.warehouse),
                )
                .where(
                    StorageStatement.tenant_id == tenant_id,
                    StorageStatement.warehouse_id == warehouse_id,
                    StorageStatement.status == "draft",
                    affected_period,
                )
                .order_by(
                    StorageStatement.period_start,
                    StorageStatement.seller_id,
                    StorageStatement.id,
                )
            )
        ).unique().all()
    )

    repriced: list[RepricedStorageDraft] = []
    for statement in statements:
        measurements = list(
            (
                await session.scalars(
                    select(StorageMeasurement)
                    .options(
                        joinedload(StorageMeasurement.product),
                        joinedload(StorageMeasurement.dimension_event),
                    )
                    .where(
                        StorageMeasurement.tenant_id == tenant_id,
                        StorageMeasurement.seller_id == statement.seller_id,
                        StorageMeasurement.warehouse_id == warehouse_id,
                        StorageMeasurement.period_start == statement.period_start,
                        StorageMeasurement.period_end == statement.period_end,
                    )
                    .order_by(StorageMeasurement.product_id)
                )
            ).unique().all()
        )
        priceable_rows = [row for row in measurements if row.status == "calculated"]
        pricing = (
            await get_storage_draft_pricing(session, statement, priceable_rows)
            if priceable_rows
            else {}
        )
        repriced.append(
            RepricedStorageDraft(
                statement=statement,
                measurements=measurements,
                pricing=pricing,
            )
        )
    return repriced


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
    current_month = datetime.now(MOSCOW).date().replace(day=1)
    if statement.period_start >= current_month:
        raise StorageStatementError("period_not_closed")

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

    # Load every shared tariff intersecting the month.  Pricing below applies
    # each version only from its valid_from date and prefers seller overrides.
    tariffs = list(
        (
            await session.scalars(
                select(BillingTariffVersion)
                .where(BillingTariffVersion.tenant_id == tenant_id)
                .where(BillingTariffVersion.service_code == "storage_liter_day")
                .where(BillingTariffVersion.unit == "liter_day")
                .where(BillingTariffVersion.warehouse_id == statement.warehouse_id)
                .where(BillingTariffVersion.valid_from <= statement.period_end)
                .where(
                    or_(
                        BillingTariffVersion.valid_to.is_(None),
                        BillingTariffVersion.valid_to >= statement.period_start,
                    )
                )
                .where(
                    or_(
                        BillingTariffVersion.seller_id.is_(None),
                        BillingTariffVersion.seller_id == statement.seller_id,
                    )
                )
                .order_by(BillingTariffVersion.valid_from, BillingTariffVersion.id)
            )
        ).all()
    )
    if not tariffs:
        raise StorageStatementError("tariff_not_found")
    pricing = await _measurement_pricing(session, statement, measurements, tariffs)

    source_ids = _statement_source_ids(statement, measurements)
    existing_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code == "storage_liter_day",
                    BillingLedgerEntry.source_id.in_(source_ids),
                )
            )
        ).all()
    )
    existing_ids = {row.source_id for row in existing_rows}
    for measurement in measurements:
        if measurement.id in existing_ids:
            continue
        charged_quantity, amount, tariff = pricing[measurement.id]
        effective_rate = (
            (amount / charged_quantity).quantize(Decimal("0.000000000001"))
            if charged_quantity
            else Decimal(0)
        )
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=statement.seller_id,
                tariff_version_id=tariff.id,
                service_code="storage_liter_day",
                unit="liter_day",
                source="storage_statement",
                source_type="storage_measurement",
                source_id=measurement.id,
                quantity=charged_quantity,
                rate=effective_rate,
                amount=amount,
                occurred_at=datetime.now(UTC),
            )
        )
    if not measurements and statement.id not in existing_ids:
        # A zero statement still has one auditable ledger publication.
        zero_tariff = _tariff_for_day(tariffs, statement.period_end) or max(
            tariffs,
            key=lambda item: (item.seller_id is not None, item.valid_from, str(item.id)),
        )
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=statement.seller_id,
                tariff_version_id=zero_tariff.id,
                service_code="storage_liter_day",
                unit="liter_day",
                source="storage_statement",
                source_type="storage_measurement",
                source_id=statement.id,
                quantity=Decimal(0),
                rate=zero_tariff.amount,
                amount=Decimal(0),
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
        select(StorageStatement)
        .options(joinedload(StorageStatement.seller), joinedload(StorageStatement.warehouse))
        .where(
            StorageStatement.id == statement_id,
            StorageStatement.tenant_id == tenant_id,
            StorageStatement.status == "fixed",
        )
    )
    if statement is None:
        raise StorageStatementError("not_found")
    # Reconstruct only this document's source measurements.  A seller may have
    # several fixed months, so a broad seller ledger query is incorrect.
    measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement)
                .where(StorageMeasurement.tenant_id == tenant_id)
                .where(StorageMeasurement.seller_id == statement.seller_id)
                .where(StorageMeasurement.warehouse_id == statement.warehouse_id)
                .where(StorageMeasurement.period_start == statement.period_start)
                .where(StorageMeasurement.period_end == statement.period_end)
                .options(
                    joinedload(StorageMeasurement.product),
                    joinedload(StorageMeasurement.dimension_event),
                )
                .order_by(StorageMeasurement.id)
            )
        ).all()
    )
    source_ids = _statement_source_ids(statement, measurements)
    ledger_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == statement.seller_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code == "storage_liter_day",
                    BillingLedgerEntry.source_id.in_(source_ids),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )
    by_id = {row.id: row for row in measurements}
    return statement, [by_id[row.source_id] for row in ledger_rows if row.source_id in by_id]


async def create_storage_tariff(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    amount: Decimal,
    valid_from: date,
    seller_exception: tuple[uuid.UUID, Decimal, date] | None = None,
) -> tuple[
    BillingTariffVersion,
    BillingTariffVersion | None,
    list[RepricedStorageDraft],
]:
    """Create a warehouse storage tariff and an optional seller override atomically.

    Both tariff rows and the affected draft previews share one SQLAlchemy
    unit-of-work.  A failed INSERT rolls back before repricing; a repricing error
    also rolls back the new tariff versions.
    """
    amounts = [amount]
    if seller_exception is not None:
        amounts.append(seller_exception[1])
    if any(candidate <= 0 for candidate in amounts):
        raise StorageStatementError("tariff_amount_must_be_positive")

    today_moscow = datetime.now(MOSCOW).date()
    effective_dates = [valid_from]
    if seller_exception is not None:
        effective_dates.append(seller_exception[2])
    if any(effective_date < today_moscow for effective_date in effective_dates):
        raise StorageStatementError("tariff_valid_from_in_past")

    warehouse = await session.scalar(
        select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
    )
    if warehouse is None:
        raise StorageStatementError("warehouse_not_found")
    if not warehouse.is_operational:
        raise StorageStatementError("warehouse_not_operational")

    if seller_exception is not None:
        seller_id = seller_exception[0]
        seller = await session.scalar(
            select(Seller).where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
        )
        if seller is None:
            raise StorageStatementError("seller_not_found")

    warehouse_tariff = BillingTariffVersion(
        tenant_id=tenant_id,
        seller_id=None,
        warehouse_id=warehouse_id,
        service_code="storage_liter_day",
        unit="liter_day",
        amount=amount,
        valid_from=valid_from,
    )
    session.add(warehouse_tariff)

    seller_tariff: BillingTariffVersion | None = None
    if seller_exception is not None:
        seller_id, seller_amount, seller_valid_from = seller_exception
        seller_tariff = BillingTariffVersion(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            service_code="storage_liter_day",
            unit="liter_day",
            amount=seller_amount,
            valid_from=seller_valid_from,
        )
        session.add(seller_tariff)

    repriced_drafts: list[RepricedStorageDraft]
    try:
        await session.flush()
        repriced_drafts = await reprice_open_storage_drafts(
            session,
            tenant_id,
            warehouse_id,
            valid_from,
            seller_exception,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise StorageStatementError("tariff_already_exists") from exc
    except Exception:
        await session.rollback()
        raise

    await session.refresh(warehouse_tariff)
    if seller_tariff is not None:
        await session.refresh(seller_tariff)

    return warehouse_tariff, seller_tariff, repriced_drafts


async def get_storage_ledger_rows(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> list[Any]:
    """Return the immutable ledger snapshot belonging to one fixed statement."""
    statement = await session.scalar(
        select(StorageStatement).where(
            StorageStatement.id == statement_id,
            StorageStatement.tenant_id == tenant_id,
            StorageStatement.status == "fixed",
        )
    )
    if statement is None:
        raise StorageStatementError("not_found")
    measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement.id).where(
                    StorageMeasurement.tenant_id == tenant_id,
                    StorageMeasurement.seller_id == statement.seller_id,
                    StorageMeasurement.warehouse_id == statement.warehouse_id,
                    StorageMeasurement.period_start == statement.period_start,
                    StorageMeasurement.period_end == statement.period_end,
                )
            )
        ).all()
    )
    return list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == statement.seller_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code == "storage_liter_day",
                    BillingLedgerEntry.source_id.in_(set(measurements) or {statement.id}),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )
