from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_UP,
    Decimal,
    DecimalException,
    InvalidOperation,
)
from itertools import pairwise
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.billing import BillingLedgerEntry, BillingTariffVersionV2
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.services.billing_ledger_service import (
    BillingLedgerError,
    postgres_integer,
    postgres_numeric,
)
from app.services.billing_seller_report_service import storage_tariff_for_day
from app.services.billing_tariff_matrix_service import (
    BillingTariffMatrixError,
    TariffVersionDraft,
    get_tariff_matrix,
    save_tariff_matrix,
)
from app.services.operation_fact_service import record_storage_fixed
from app.services.staff_packaging_billing_service import rub_to_kopecks
from app.services.storage_measurement_service import (
    MOSCOW,
    _seconds,
    _volume_segments,
    calculation_end_exclusive,
)


class StorageStatementError(ValueError):
    pass


STORAGE_TARIFF_MONEY_QUANTUM = Decimal("0.01")


def _as_moscow_timestamp(value: datetime) -> datetime:
    """SQLite drops tzinfo from V2 timestamps; persisted values are UTC instants."""
    return (
        value.replace(tzinfo=UTC).astimezone(MOSCOW)
        if value.tzinfo is None
        else value.astimezone(MOSCOW)
    )


def normalize_storage_tariff_amount(amount: Decimal) -> Decimal:
    """Round a storage rate to persisted money precision and reject zero."""
    try:
        normalized = amount.quantize(
            STORAGE_TARIFF_MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        postgres_integer(normalized * Decimal(100), field="tariff_amount")
    except (InvalidOperation, BillingLedgerError) as exc:
        raise StorageStatementError("tariff_amount_out_of_range") from exc
    if normalized <= 0:
        raise StorageStatementError("tariff_amount_must_be_positive")
    return normalized


def normalize_storage_ledger_quantity(quantity: Decimal) -> Decimal:
    """Fit one storage charge quantity into billing ledger NUMERIC(14, 4)."""
    try:
        normalized = postgres_numeric(
            quantity,
            precision=14,
            scale=4,
            field="ledger_quantity",
        )
    except BillingLedgerError as exc:
        raise StorageStatementError("ledger_quantity_out_of_range") from exc
    if normalized < 0:
        raise StorageStatementError("ledger_quantity_out_of_range")
    return normalized


def _storage_ledger_integer(value: Decimal, field: str) -> int:
    try:
        return postgres_integer(value, field=field)
    except BillingLedgerError as exc:
        raise StorageStatementError(f"{field}_out_of_range") from exc


StorageDraftPricing = dict[
    uuid.UUID,
    tuple[Decimal, Decimal, BillingTariffVersionV2],
]
RawStorageDraftPricing = dict[
    uuid.UUID,
    tuple[Decimal, dict[date, Decimal], BillingTariffVersionV2],
]
StoragePricingScope = tuple[StorageStatement, list[StorageMeasurement]]


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
    tariffs: list[BillingTariffVersionV2],
    on_day: date,
) -> BillingTariffVersionV2 | None:
    """Use the exact V2 seller/common precedence used by the invoice report."""
    return storage_tariff_for_day(tariffs, on_day)


def _pricing_boundaries(
    start: datetime,
    end: datetime,
    tariffs: list[BillingTariffVersionV2],
) -> list[datetime]:
    boundaries = {start, end}
    for tariff in tariffs:
        valid_from = _as_moscow_timestamp(tariff.valid_from_at)
        if start < valid_from < end:
            boundaries.add(valid_from)
        if tariff.valid_to_at is not None:
            valid_to = _as_moscow_timestamp(tariff.valid_to_at)
            if start < valid_to < end:
                boundaries.add(valid_to)
    return sorted(boundaries)


def _price_volume_segments(
    segments: Sequence[
        tuple[datetime, datetime, int, Decimal | None, ProductDimensionEvent | None]
    ],
    tariffs: list[BillingTariffVersionV2],
) -> tuple[Decimal, Decimal, BillingTariffVersionV2 | None]:
    """Price actual liter-day intervals while keeping one ledger row per measurement.

    The shared ledger permits one source row for a storage measurement.  If a rate
    changes inside the month, ``amount`` is the exact sum of the dated intervals and
    ``rate`` is their weighted snapshot for the single immutable ledger row.
    """
    charged_quantity, amount_by_day, last_tariff = _price_volume_segments_by_day(
        segments,
        tariffs,
    )
    amount = sum(amount_by_day.values(), start=Decimal(0)) / Decimal(100)
    return (
        charged_quantity,
        amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        last_tariff,
    )


def _price_volume_segments_by_day(
    segments: Sequence[
        tuple[datetime, datetime, int, Decimal | None, ProductDimensionEvent | None]
    ],
    tariffs: list[BillingTariffVersionV2],
) -> tuple[Decimal, dict[date, Decimal], BillingTariffVersionV2 | None]:
    """Return exact kopeck contributions split at Moscow day boundaries."""
    charged_quantity = Decimal(0)
    amount_by_day: dict[date, Decimal] = {}
    last_tariff: BillingTariffVersionV2 | None = None
    for segment_start, segment_end, held, volume, _ in segments:
        if held <= 0 or volume is None:
            continue
        boundaries = set(_pricing_boundaries(segment_start, segment_end, tariffs))
        next_day = datetime.combine(
            segment_start.astimezone(MOSCOW).date() + timedelta(days=1),
            time.min,
            MOSCOW,
        )
        while next_day < segment_end:
            boundaries.add(next_day)
            next_day += timedelta(days=1)
        for left, right in pairwise(sorted(boundaries)):
            day = left.astimezone(MOSCOW).date()
            tariff = _tariff_for_day(tariffs, day)
            if tariff is None:
                continue
            quantity = Decimal(held) * _seconds(left, right) * Decimal(volume)
            charged_quantity += quantity
            amount_by_day[day] = amount_by_day.get(day, Decimal(0)) + (
                quantity * Decimal(tariff.rate)
            )
            last_tariff = tariff
    return charged_quantity, amount_by_day, last_tariff


async def _measurement_pricing_raw(
    session: AsyncSession,
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
    tariffs: list[BillingTariffVersionV2],
) -> RawStorageDraftPricing:
    product_ids = {measurement.product_id for measurement in measurements}
    period_end_at = calculation_end_exclusive(statement.period_start, statement.period_end)
    products = {
        product.id: product
        for product in (
            await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    }
    movements_by_scope: dict[
        tuple[uuid.UUID | None, uuid.UUID, uuid.UUID],
        list[InventoryMovement],
    ] = {}
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
        movements_by_scope.setdefault(
            (movement.seller_id, movement.warehouse_id, movement.product_id),
            [],
        ).append(movement)
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

    return _measurement_pricing_raw_from_loaded(
        statement,
        measurements,
        tariffs,
        products,
        movements_by_scope,
        events_by_product,
    )


def _measurement_pricing_raw_from_loaded(
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
    tariffs: list[BillingTariffVersionV2],
    products: dict[uuid.UUID, Product],
    movements_by_scope: dict[
        tuple[uuid.UUID | None, uuid.UUID, uuid.UUID],
        list[InventoryMovement],
    ],
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]],
) -> RawStorageDraftPricing:
    """Рассчитать строки ведомости по уже пакетно загруженным исходным данным."""
    period_start_at = datetime.combine(statement.period_start, time.min, MOSCOW)
    period_end_at = calculation_end_exclusive(statement.period_start, statement.period_end)

    raw_pricing: RawStorageDraftPricing = {}
    for measurement in measurements:
        product = products[measurement.product_id]
        segments = _volume_segments(
            movements_by_scope.get(
                (
                    statement.seller_id,
                    statement.warehouse_id,
                    measurement.product_id,
                ),
                [],
            ),
            events_by_product.get(measurement.product_id, []),
            period_start_at,
            period_end_at,
            legacy_volume_liters=product.volume_liters,
        )
        charged_quantity, amount_by_day, last_tariff = _price_volume_segments_by_day(
            segments,
            tariffs,
        )
        if last_tariff is None:
            # The dated tariff can intersect the statement even when this SKU
            # had no positive balance after the rate became effective.  Such a
            # row is a valid zero preview, not a reason to reject the tariff.
            last_tariff = _tariff_for_day(tariffs, statement.period_end)
        if last_tariff is None:
            raise StorageStatementError("tariff_not_found")
        raw_pricing[measurement.id] = (charged_quantity, amount_by_day, last_tariff)
    return raw_pricing


async def get_storage_draft_pricing_batch(
    session: AsyncSession,
    rounding_scopes: Sequence[StoragePricingScope],
) -> dict[uuid.UUID, StorageDraftPricing]:
    """Рассчитать список ведомостей фиксированным числом запросов к БД."""
    scopes = [(statement, rows) for statement, rows in rounding_scopes if rows]
    if not scopes:
        return {}

    tenant_id = scopes[0][0].tenant_id
    seller_ids = {statement.seller_id for statement, _rows in scopes}
    product_ids = {row.product_id for _statement, rows in scopes for row in rows}
    warehouse_ids = {statement.warehouse_id for statement, _rows in scopes}
    period_start_at = min(
        datetime.combine(statement.period_start, time.min, MOSCOW)
        for statement, _rows in scopes
    )
    period_end_at = max(
        calculation_end_exclusive(statement.period_start, statement.period_end)
        for statement, _rows in scopes
    )

    tariffs = list(
        (
            await session.scalars(
                select(BillingTariffVersionV2).where(
                    BillingTariffVersionV2.tenant_id == tenant_id,
                    BillingTariffVersionV2.service_code == "storage",
                    BillingTariffVersionV2.unit == "liter_day",
                    BillingTariffVersionV2.enabled.is_(True),
                    BillingTariffVersionV2.employee_user_id.is_(None),
                    BillingTariffVersionV2.product_id.is_(None),
                    BillingTariffVersionV2.valid_from_at < period_end_at,
                    or_(
                        BillingTariffVersionV2.valid_to_at.is_(None),
                        BillingTariffVersionV2.valid_to_at > period_start_at,
                    ),
                    or_(
                        BillingTariffVersionV2.seller_id.is_(None),
                        BillingTariffVersionV2.seller_id.in_(seller_ids),
                    ),
                )
            )
        ).all()
    )
    products = {
        product.id: product
        for product in (
            await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    }
    movements = list(
        (
            await session.scalars(
                select(InventoryMovement)
                .where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.seller_id.in_(seller_ids),
                    InventoryMovement.warehouse_id.in_(warehouse_ids),
                    InventoryMovement.product_id.in_(product_ids),
                    InventoryMovement.created_at < period_end_at,
                )
                .order_by(InventoryMovement.created_at, InventoryMovement.id)
            )
        ).all()
    )
    movements_by_scope: dict[
        tuple[uuid.UUID | None, uuid.UUID, uuid.UUID],
        list[InventoryMovement],
    ] = {}
    for movement in movements:
        movements_by_scope.setdefault(
            (movement.seller_id, movement.warehouse_id, movement.product_id),
            [],
        ).append(movement)
    events = list(
        (
            await session.scalars(
                select(ProductDimensionEvent)
                .where(
                    ProductDimensionEvent.tenant_id == tenant_id,
                    ProductDimensionEvent.product_id.in_(product_ids),
                    ProductDimensionEvent.observed_at < period_end_at,
                )
                .order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id)
            )
        ).all()
    )
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]] = {}
    for event in events:
        events_by_product.setdefault(event.product_id, []).append(event)

    scopes_by_seller_period: dict[
        tuple[uuid.UUID, date, date],
        list[StoragePricingScope],
    ] = {}
    for statement, rows in scopes:
        key = (
            statement.seller_id,
            statement.period_start,
            statement.period_end,
        )
        scopes_by_seller_period.setdefault(key, []).append((statement, rows))

    result: dict[uuid.UUID, StorageDraftPricing] = {}
    for (seller_id, _period_start, _period_end), seller_scopes in (
        scopes_by_seller_period.items()
    ):
        seller_tariffs = [
            tariff
            for tariff in tariffs
            if tariff.seller_id is None or tariff.seller_id == seller_id
        ]
        if not seller_tariffs:
            continue
        combined_raw: RawStorageDraftPricing = {}
        try:
            for statement, rows in seller_scopes:
                combined_raw.update(
                    _measurement_pricing_raw_from_loaded(
                        statement,
                        rows,
                        seller_tariffs,
                        products,
                        movements_by_scope,
                        events_by_product,
                    )
                )
        except StorageStatementError as exc:
            if str(exc) == "tariff_not_found":
                continue
            raise
        combined_pricing = _allocate_storage_pricing(combined_raw)
        for statement, rows in seller_scopes:
            result[statement.id] = {
                row.id: combined_pricing[row.id]
                for row in rows
            }
    return result


def _allocate_storage_pricing(
    raw_pricing: RawStorageDraftPricing,
) -> StorageDraftPricing:
    """Allocate seller/day rounded kopecks across all supplied statement rows."""

    # The invoice rounds the seller's total once per Moscow day. Allocate that
    # same integer number of kopecks back to visible statement rows using the
    # largest remainders, with the measurement UUID as a stable tie-breaker.
    # This keeps both the document total and the sum of its rows exactly equal
    # to the invoice without inventing sub-kopeck public amounts.
    allocated_kopecks = {measurement_id: 0 for measurement_id in raw_pricing}
    days = sorted(
        {
            day
            for _, amount_by_day, _ in raw_pricing.values()
            for day in amount_by_day
        }
    )
    for day in days:
        exact = {
            measurement_id: amount_by_day.get(day, Decimal(0))
            for measurement_id, (_, amount_by_day, _) in raw_pricing.items()
        }
        floors = {
            measurement_id: int(value.to_integral_value(rounding=ROUND_FLOOR))
            for measurement_id, value in exact.items()
        }
        target = int(
            sum(exact.values(), start=Decimal(0)).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
        remainder_count = target - sum(floors.values())
        ranked = sorted(
            exact,
            key=lambda measurement_id: (
                -(exact[measurement_id] - Decimal(floors[measurement_id])),
                str(measurement_id),
            ),
        )
        for measurement_id, floor in floors.items():
            allocated_kopecks[measurement_id] += floor
        for measurement_id in ranked[:remainder_count]:
            allocated_kopecks[measurement_id] += 1

    result: StorageDraftPricing = {}
    for measurement_id, (charged_quantity, _, last_tariff) in raw_pricing.items():
        result[measurement_id] = (
            charged_quantity,
            (Decimal(allocated_kopecks[measurement_id]) / Decimal(100)).quantize(
                STORAGE_TARIFF_MONEY_QUANTUM
            ),
            last_tariff,
        )
    return result


async def _measurement_pricing(
    session: AsyncSession,
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
    tariffs: list[BillingTariffVersionV2],
) -> StorageDraftPricing:
    raw_pricing = await _measurement_pricing_raw(
        session,
        statement,
        measurements,
        tariffs,
    )
    return _allocate_storage_pricing(raw_pricing)


async def get_storage_draft_pricing(
    session: AsyncSession,
    statement: StorageStatement,
    measurements: list[StorageMeasurement],
    newly_created_tariffs: Sequence[BillingTariffVersionV2] = (),
    *,
    rounding_scopes: Sequence[
        tuple[StorageStatement, list[StorageMeasurement]]
    ] = (),
) -> StorageDraftPricing:
    """Calculate the current preview for an editable statement from dated tariffs."""
    period_start_at = datetime.combine(statement.period_start, time.min, MOSCOW)
    period_end_at = calculation_end_exclusive(statement.period_start, statement.period_end)
    tariffs = list(
        (
            await session.scalars(
                select(BillingTariffVersionV2).where(
                    BillingTariffVersionV2.tenant_id == statement.tenant_id,
                    BillingTariffVersionV2.service_code == "storage",
                    BillingTariffVersionV2.unit == "liter_day",
                    BillingTariffVersionV2.enabled.is_(True),
                    BillingTariffVersionV2.employee_user_id.is_(None),
                    BillingTariffVersionV2.product_id.is_(None),
                    BillingTariffVersionV2.valid_from_at < period_end_at,
                    or_(
                        BillingTariffVersionV2.valid_to_at.is_(None),
                        BillingTariffVersionV2.valid_to_at > period_start_at,
                    ),
                    or_(
                        BillingTariffVersionV2.seller_id.is_(None),
                        BillingTariffVersionV2.seller_id == statement.seller_id,
                    ),
                )
            )
        ).all()
    )
    known_tariff_ids = {tariff.id for tariff in tariffs}
    tariffs.extend(
        tariff
        for tariff in newly_created_tariffs
        if tariff.id not in known_tariff_ids
        and tariff.tenant_id == statement.tenant_id
        and tariff.service_code == "storage"
        and tariff.unit == "liter_day"
        and tariff.enabled
        and _as_moscow_timestamp(tariff.valid_from_at) < period_end_at
        and (
            tariff.valid_to_at is None
            or _as_moscow_timestamp(tariff.valid_to_at) > period_start_at
        )
        and (tariff.seller_id is None or tariff.seller_id == statement.seller_id)
    )
    if not tariffs:
        raise StorageStatementError("tariff_not_found")
    if rounding_scopes:
        combined_raw: RawStorageDraftPricing = {}
        for peer_statement, peer_measurements in rounding_scopes:
            if (
                peer_statement.seller_id != statement.seller_id
                or peer_statement.period_start != statement.period_start
                or peer_statement.period_end != statement.period_end
            ):
                continue
            combined_raw.update(
                await _measurement_pricing_raw(
                    session,
                    peer_statement,
                    peer_measurements,
                    tariffs,
                )
            )
        combined_pricing = _allocate_storage_pricing(combined_raw)
        return {
            measurement.id: combined_pricing[measurement.id]
            for measurement in measurements
        }
    return await _measurement_pricing(session, statement, measurements, tariffs)


async def reprice_open_storage_drafts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    valid_from: date,
    seller_exception: tuple[uuid.UUID, Decimal, date] | None = None,
    newly_created_tariffs: Sequence[BillingTariffVersionV2] = (),
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
                    StorageStatement.status == "draft",
                    affected_period,
                )
                .order_by(
                    StorageStatement.period_start,
                    StorageStatement.seller_id,
                    StorageStatement.id,
                )
            )
        )
        .unique()
        .all()
    )

    statement_rows: dict[uuid.UUID, list[StorageMeasurement]] = {}
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
                        StorageMeasurement.warehouse_id == statement.warehouse_id,
                        StorageMeasurement.period_start == statement.period_start,
                        StorageMeasurement.period_end == statement.period_end,
                    )
                    .order_by(StorageMeasurement.product_id)
                )
            )
            .unique()
            .all()
        )
        statement_rows[statement.id] = measurements

    rounding_scopes_by_seller_period: dict[
        tuple[uuid.UUID, date, date],
        list[tuple[StorageStatement, list[StorageMeasurement]]],
    ] = {}
    for statement in statements:
        priceable_rows = [
            row
            for row in statement_rows[statement.id]
            if row.status == "calculated"
        ]
        if priceable_rows:
            key = (
                statement.seller_id,
                statement.period_start,
                statement.period_end,
            )
            rounding_scopes_by_seller_period.setdefault(key, []).append(
                (statement, priceable_rows)
            )

    repriced: list[RepricedStorageDraft] = []
    for statement in statements:
        measurements = statement_rows[statement.id]
        priceable_rows = [row for row in measurements if row.status == "calculated"]
        key = (
            statement.seller_id,
            statement.period_start,
            statement.period_end,
        )
        pricing = (
            await get_storage_draft_pricing(
                session,
                statement,
                priceable_rows,
                newly_created_tariffs,
                rounding_scopes=rounding_scopes_by_seller_period.get(key, []),
            )
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
        .options(joinedload(StorageStatement.seller))
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

    peer_measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement)
                .where(StorageMeasurement.tenant_id == tenant_id)
                .where(StorageMeasurement.seller_id == statement.seller_id)
                .where(StorageMeasurement.period_start == statement.period_start)
                .where(StorageMeasurement.period_end == statement.period_end)
                .order_by(StorageMeasurement.warehouse_id, StorageMeasurement.id)
            )
        ).all()
    )
    measurements = [
        row
        for row in peer_measurements
        if row.warehouse_id == statement.warehouse_id
    ]
    # Копейки округляются на уровне продавца и дня, а потом распределяются между
    # всеми его складами. Поэтому фиксировать один склад можно только после того,
    # как рассчитаны габариты на остальных складах того же периода: иначе позднее
    # исправление соседа перераспределит копейку, уже опубликованную проводкой.
    if any(row.status != "calculated" for row in peer_measurements):
        raise StorageStatementError("missing_dimensions")

    # Load every shared tariff intersecting the month.  Pricing below applies
    # each version only from its valid_from date and prefers seller overrides.
    period_start_at = datetime.combine(statement.period_start, time.min, MOSCOW)
    period_end_at = calculation_end_exclusive(statement.period_start, statement.period_end)
    tariffs = list(
        (
            await session.scalars(
                select(BillingTariffVersionV2)
                .where(BillingTariffVersionV2.tenant_id == tenant_id)
                .where(BillingTariffVersionV2.service_code == "storage")
                .where(BillingTariffVersionV2.unit == "liter_day")
                .where(BillingTariffVersionV2.enabled.is_(True))
                .where(BillingTariffVersionV2.employee_user_id.is_(None))
                .where(BillingTariffVersionV2.product_id.is_(None))
                .where(BillingTariffVersionV2.valid_from_at < period_end_at)
                .where(
                    or_(
                        BillingTariffVersionV2.valid_to_at.is_(None),
                        BillingTariffVersionV2.valid_to_at > period_start_at,
                    )
                )
                .where(
                    or_(
                        BillingTariffVersionV2.seller_id.is_(None),
                        BillingTariffVersionV2.seller_id == statement.seller_id,
                    )
                )
                .order_by(BillingTariffVersionV2.valid_from_at, BillingTariffVersionV2.id)
            )
        ).all()
    )
    if not tariffs:
        raise StorageStatementError("tariff_not_found")
    peer_statements = list(
        (
            await session.scalars(
                select(StorageStatement).where(
                    StorageStatement.tenant_id == tenant_id,
                    StorageStatement.seller_id == statement.seller_id,
                    StorageStatement.period_start == statement.period_start,
                    StorageStatement.period_end == statement.period_end,
                )
            )
        ).all()
    )
    peer_rows_by_warehouse: dict[uuid.UUID, list[StorageMeasurement]] = {}
    for peer_measurement in peer_measurements:
        peer_rows_by_warehouse.setdefault(
            peer_measurement.warehouse_id, []
        ).append(peer_measurement)
    priced_peer_scopes: list[
        tuple[StorageStatement, list[StorageMeasurement]]
    ] = []
    for peer_statement in peer_statements:
        peer_rows = peer_rows_by_warehouse.get(peer_statement.warehouse_id, [])
        if peer_rows:
            priced_peer_scopes.append((peer_statement, peer_rows))

    if len(priced_peer_scopes) == 1:
        pricing = await _measurement_pricing(
            session,
            statement,
            measurements,
            tariffs,
        )
    else:
        combined_raw: RawStorageDraftPricing = {}
        for peer_statement, peer_rows in priced_peer_scopes:
            combined_raw.update(
                await _measurement_pricing_raw(
                    session,
                    peer_statement,
                    peer_rows,
                    tariffs,
                )
            )
        combined_pricing = _allocate_storage_pricing(combined_raw)
        pricing = {
            measurement.id: combined_pricing[measurement.id]
            for measurement in measurements
        }

    source_ids = _statement_source_ids(statement, measurements)
    existing_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code == "storage",
                    BillingLedgerEntry.source_id.in_(source_ids),
                )
            )
        ).all()
    )
    existing_ids = {row.source_id for row in existing_rows}
    pending_entries: list[BillingLedgerEntry] = []
    for measurement in measurements:
        if measurement.id in existing_ids:
            continue
        charged_quantity, amount, tariff = pricing[measurement.id]
        quantity_value = normalize_storage_ledger_quantity(charged_quantity)
        amount_value = _storage_ledger_integer(
            amount * Decimal(100),
            "ledger_amount",
        )
        try:
            effective_rate = (
                (amount / charged_quantity).quantize(Decimal("0.000000000001"))
                if charged_quantity
                else Decimal(0)
            )
        except DecimalException as exc:
            raise StorageStatementError("ledger_rate_out_of_range") from exc
        rate_value = _storage_ledger_integer(
            effective_rate * Decimal(100),
            "ledger_rate",
        )
        pending_entries.append(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=statement.seller_id,
                warehouse_id=statement.warehouse_id,
                tariff_version_v2_id=tariff.id,
                service_code="storage",
                unit="liter_day",
                source="storage_statement",
                source_type="storage_measurement",
                source_id=measurement.id,
                event_kind="storage_fixed",
                quantity=quantity_value,
                rate=rate_value,
                amount=amount_value,
                occurred_at=datetime.now(UTC),
            )
        )
    if not measurements and statement.id not in existing_ids:
        # A zero statement still has one auditable ledger publication.
        zero_tariff = _tariff_for_day(tariffs, statement.period_end) or max(
            tariffs,
            key=lambda item: (item.seller_id is not None, item.valid_from_at, str(item.id)),
        )
        pending_entries.append(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=statement.seller_id,
                warehouse_id=statement.warehouse_id,
                tariff_version_v2_id=zero_tariff.id,
                service_code="storage",
                unit="liter_day",
                source="storage_statement",
                source_type="storage_measurement",
                source_id=statement.id,
                event_kind="storage_fixed",
                quantity=normalize_storage_ledger_quantity(Decimal(0)),
                rate=_storage_ledger_integer(
                    Decimal(zero_tariff.rate),
                    "ledger_rate",
                ),
                amount=_storage_ledger_integer(Decimal(0), "ledger_amount"),
                occurred_at=datetime.now(UTC),
            )
        )
    # Validate the complete publication before attaching a row or mutating the
    # statement. An overflow in a later SKU therefore leaves no partial state.
    occurred_at = datetime.now(UTC)
    for measurement in measurements:
        await record_storage_fixed(
            session,
            statement=statement,
            source_event_id=measurement.id,
            occurred_at=occurred_at,
        )
    if not measurements:
        await record_storage_fixed(
            session,
            statement=statement,
            source_event_id=statement.id,
            occurred_at=occurred_at,
        )
    session.add_all(pending_entries)
    statement.status = "fixed"
    statement.fixed_at = occurred_at
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
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
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
    amount: Decimal,
    valid_from: date,
    revision: int,
    seller_exception: tuple[uuid.UUID, Decimal, date] | None = None,
) -> tuple[
    BillingTariffVersionV2,
    BillingTariffVersionV2 | None,
    list[RepricedStorageDraft],
    int,
]:
    """Save common/seller V2 rates and refresh every affected draft atomically."""
    amount = normalize_storage_tariff_amount(amount)
    if seller_exception is not None:
        seller_exception = (
            seller_exception[0],
            normalize_storage_tariff_amount(seller_exception[1]),
            seller_exception[2],
        )

    today_moscow = datetime.now(MOSCOW).date()
    effective_dates = [valid_from]
    if seller_exception is not None:
        effective_dates.append(seller_exception[2])
    if any(effective_date < today_moscow for effective_date in effective_dates):
        raise StorageStatementError("tariff_valid_from_in_past")

    config = await get_tariff_matrix(session, tenant_id=tenant_id)
    versions: list[TariffVersionDraft] = [
        {
            "seller_id": None,
            "product_id": None,
            "employee_user_id": None,
            "service_code": "storage",
            "unit": "liter_day",
            "enabled": True,
            "rate": rub_to_kopecks(amount),
            "valid_from_at": datetime.combine(valid_from, time.min, MOSCOW),
            "valid_to_at": None,
        }
    ]
    if seller_exception is not None:
        seller_id, seller_amount, seller_valid_from = seller_exception
        versions.append(
            {
                "seller_id": seller_id,
                "product_id": None,
                "employee_user_id": None,
                "service_code": "storage",
                "unit": "liter_day",
                "enabled": True,
                "rate": rub_to_kopecks(seller_amount),
                "valid_from_at": datetime.combine(seller_valid_from, time.min, MOSCOW),
                "valid_to_at": None,
            }
        )
    try:
        services = {
            state.service_code: state.enabled or state.service_code == "storage"
            for state in config.service_states
        }
        config = await save_tariff_matrix(
            session,
            tenant_id=tenant_id,
            revision=revision,
            services=services,
            versions=versions,
        )
        await session.flush()

        async def saved_version(draft: TariffVersionDraft) -> BillingTariffVersionV2:
            query = select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.service_code == draft["service_code"],
                BillingTariffVersionV2.unit == draft["unit"],
                BillingTariffVersionV2.enabled == draft["enabled"],
                BillingTariffVersionV2.rate == draft["rate"],
                BillingTariffVersionV2.product_id.is_(None),
                BillingTariffVersionV2.employee_user_id.is_(None),
                BillingTariffVersionV2.valid_from_at
                == draft["valid_from_at"].astimezone(UTC),
            )
            if draft["seller_id"] is None:
                query = query.where(BillingTariffVersionV2.seller_id.is_(None))
            else:
                query = query.where(
                    BillingTariffVersionV2.seller_id == draft["seller_id"]
                )
            row = await session.scalar(query)
            if row is None:
                raise StorageStatementError("saved_tariff_not_found")
            return row

        common_tariff = await saved_version(versions[0])
        seller_tariff = (
            await saved_version(versions[1]) if seller_exception is not None else None
        )
        repriced_drafts = await reprice_open_storage_drafts(
            session,
            tenant_id,
            valid_from,
            seller_exception,
            (common_tariff, *( (seller_tariff,) if seller_tariff is not None else () )),
        )
        await session.commit()
    except (IntegrityError, BillingTariffMatrixError) as exc:
        await session.rollback()
        raise StorageStatementError(str(exc)) from exc
    except Exception:
        await session.rollback()
        raise

    await session.refresh(common_tariff)
    if seller_tariff is not None:
        await session.refresh(seller_tariff)

    return common_tariff, seller_tariff, repriced_drafts, config.revision


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
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
                    BillingLedgerEntry.source_id.in_(set(measurements) or {statement.id}),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )


async def get_storage_ledger_rows_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statements: Sequence[StorageStatement],
    rows_by_statement: dict[uuid.UUID, list[StorageMeasurement]],
) -> dict[uuid.UUID, list[BillingLedgerEntry]]:
    """Загрузить проводки списка ведомостей одним запросом."""
    source_to_statement: dict[uuid.UUID, uuid.UUID] = {}
    for statement in statements:
        rows = rows_by_statement.get(statement.id, [])
        for source_id in _statement_source_ids(statement, rows):
            source_to_statement[source_id] = statement.id
    if not source_to_statement:
        return {}

    ledger_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
                    BillingLedgerEntry.source_id.in_(source_to_statement),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )
    result: dict[uuid.UUID, list[BillingLedgerEntry]] = {
        statement.id: [] for statement in statements
    }
    for ledger_row in ledger_rows:
        statement_id = source_to_statement.get(ledger_row.source_id)
        if statement_id is not None:
            result[statement_id].append(ledger_row)
    return result
