from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse


class StorageMeasurementError(ValueError):
    pass


MOSCOW = ZoneInfo("Europe/Moscow")


def previous_month(today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(MOSCOW).date()
    first = today.replace(day=1)
    end_month = first - timedelta(days=1)
    return end_month.replace(day=1), end_month


def month_bounds(year: int, month: int) -> tuple[date, date]:
    if month not in range(1, 13):
        raise StorageMeasurementError("invalid_month")
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def calculation_end_exclusive(
    period_start: date,
    period_end: date,
    *,
    now: datetime | None = None,
) -> datetime:
    """Return the real upper boundary for an open monthly measurement.

    Completed months end at the next calendar-month boundary.  The current
    month ends at the current Moscow instant, so a draft never includes storage
    time that has not happened yet.
    """
    now_moscow = _as_moscow(now or datetime.now(MOSCOW))
    calendar_end = datetime.combine(period_end + timedelta(days=1), time.min, MOSCOW)
    if period_start == now_moscow.date().replace(day=1):
        return min(calendar_end, now_moscow)
    return calendar_end


def _seconds(a: datetime, b: datetime) -> Decimal:
    return Decimal(str(max(0, (b - a).total_seconds()))) / Decimal(86400)


def _stock_segments(
    movements: list[InventoryMovement], start: datetime, end: datetime
) -> list[tuple[datetime, datetime, int]]:
    """Return held-stock intervals, preserving the movement history boundaries."""
    quantity = 0
    cursor = start
    segments: list[tuple[datetime, datetime, int]] = []
    for movement in movements:
        at = (
            movement.created_at.replace(tzinfo=MOSCOW)
            if movement.created_at.tzinfo is None
            else movement.created_at.astimezone(MOSCOW)
        )
        if at <= start:
            quantity += movement.quantity_delta
            continue
        bounded = min(at, end)
        if quantity < 0:
            raise StorageMeasurementError("negative_reconstructed_stock")
        if bounded > cursor:
            segments.append((cursor, bounded, quantity))
        cursor = bounded
        quantity += movement.quantity_delta
        if at >= end:
            break
    if quantity < 0:
        raise StorageMeasurementError("negative_reconstructed_stock")
    if cursor < end:
        segments.append((cursor, end, quantity))
    return segments


def _as_moscow(value: datetime) -> datetime:
    return value.replace(tzinfo=MOSCOW) if value.tzinfo is None else value.astimezone(MOSCOW)


def _effective_dimension_events(
    events: list[ProductDimensionEvent],
) -> list[ProductDimensionEvent]:
    """Return only observations that changed the effective storage volume.

    ``applied`` identifies the version active now, not whether an older event was
    active when it was recorded.  Manual and container events always represent an
    intentional change.  A regular WB event recorded while either is effective is
    observation-only; an explicit WB restore is stored with a suffixed fingerprint
    and starts a new effective period.
    """
    effective: list[ProductDimensionEvent] = []
    active_source: str | None = None
    for event in events:
        protected_manual = active_source in {"manual", "container_override", "container"}
        is_wb_restore = event.source == "wb" and ":" in event.fingerprint
        if event.source == "wb" and protected_manual and not event.applied and not is_wb_restore:
            continue
        effective.append(event)
        active_source = event.source
    return effective


def _volume_segments(
    movements: list[InventoryMovement],
    events: list[ProductDimensionEvent],
    start: datetime,
    end: datetime,
    *,
    legacy_volume_liters: Decimal | float | None,
) -> list[tuple[datetime, datetime, int, Decimal | None, ProductDimensionEvent | None]]:
    """Split held stock at both movement and dimension-version boundaries.

    A legacy value can describe a product only until it has version history.  Once
    events exist, time before the first event deliberately has no volume instead
    of applying a later measurement retroactively.
    """
    events = _effective_dimension_events(events)
    boundaries = {start, end}
    boundaries.update(
        _as_moscow(movement.created_at)
        for movement in movements
        if start < _as_moscow(movement.created_at) < end
    )
    boundaries.update(
        _as_moscow(event.observed_at)
        for event in events
        if start < _as_moscow(event.observed_at) < end
    )
    points = sorted(boundaries)
    stock_segments = _stock_segments(movements, start, end)
    result: list[tuple[datetime, datetime, int, Decimal | None, ProductDimensionEvent | None]] = []
    for segment_start, segment_end in pairwise(points):
        held = next(
            (quantity for left, right, quantity in stock_segments
             if left <= segment_start and segment_end <= right),
            0,
        )
        applicable = [event for event in events if _as_moscow(event.observed_at) <= segment_start]
        event = applicable[-1] if applicable else None
        volume = event.volume_liters if event is not None else None
        if volume is None and not events and legacy_volume_liters is not None:
            volume = Decimal(str(legacy_volume_liters))
        result.append((segment_start, segment_end, held, volume, event))
    return result


async def rebuild_storage_measurements(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    period_start: date | None = None,
    warehouse_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None,
) -> dict[str, object]:
    """Rebuild open monthly drafts; no money is produced here."""
    if period_start is None:
        period_start, period_end = previous_month()
    else:
        period_start, period_end = month_bounds(period_start.year, period_start.month)
    today = datetime.now(MOSCOW).date()
    if period_start > today.replace(day=1):
        raise StorageMeasurementError("future_month")
    period_start_at = datetime.combine(period_start, time.min, MOSCOW)
    period_end_exclusive = calculation_end_exclusive(period_start, period_end)

    warehouses = select(Warehouse.id).where(
        Warehouse.tenant_id == tenant_id, Warehouse.is_operational.is_(True)
    )
    if warehouse_id is not None:
        warehouses = warehouses.where(Warehouse.id == warehouse_id)
    operational_warehouse_ids = set((await session.scalars(warehouses)).all())
    movements = list(
        (
            await session.scalars(
                select(InventoryMovement)
                .where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.warehouse_id.in_(
                        operational_warehouse_ids or {uuid.UUID(int=0)}
                    ),
                    InventoryMovement.created_at < period_end_exclusive,
                )
                .order_by(InventoryMovement.created_at, InventoryMovement.id)
            )
        ).all()
    )
    if seller_id is not None:
        movements = [movement for movement in movements if movement.seller_id == seller_id]
    product_ids = {m.product_id for m in movements}
    products = {
        p.id: p
        for p in (await session.scalars(select(Product).where(Product.id.in_(product_ids)))).all()
    }
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]] = {}
    for event in (await session.scalars(select(ProductDimensionEvent).where(
        ProductDimensionEvent.tenant_id == tenant_id,
        ProductDimensionEvent.product_id.in_(product_ids or {uuid.UUID(int=0)}),
    ).order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id))).all():
        events_by_product.setdefault(event.product_id, []).append(event)

    rows: list[StorageMeasurement] = []
    problems = 0
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[InventoryMovement]] = {}
    for movement in movements:
        product = products.get(movement.product_id)
        if product is None or movement.seller_id is None:
            continue
        warehouse = movement.warehouse_id
        if warehouse is not None:
            grouped.setdefault((movement.seller_id, warehouse), []).append(movement)
    for (scope_seller_id, wh_id), group in grouped.items():
        by_product: dict[uuid.UUID, list[InventoryMovement]] = {}
        for movement in group:
            by_product.setdefault(movement.product_id, []).append(movement)
        for product_id, product_moves in by_product.items():
            quantity = 0
            cursor = period_start_at
            quantity_days = Decimal(0)
            first_movement: InventoryMovement | None = None
            last_movement: InventoryMovement | None = None
            for movement in product_moves:
                at = movement.created_at
                at = at.replace(tzinfo=MOSCOW) if at.tzinfo is None else at.astimezone(MOSCOW)
                if at <= cursor:
                    quantity += movement.quantity_delta
                    continue
                bounded = min(at, period_end_exclusive)
                if quantity < 0:
                    raise StorageMeasurementError("negative_reconstructed_stock")
                quantity_days += Decimal(quantity) * _seconds(cursor, bounded)
                first_movement = first_movement or movement
                last_movement = movement
                cursor = at
                quantity += movement.quantity_delta
                if at >= period_end_exclusive:
                    break
            if cursor < period_end_exclusive:
                if quantity < 0:
                    raise StorageMeasurementError("negative_reconstructed_stock")
                quantity_days += Decimal(quantity) * _seconds(cursor, period_end_exclusive)
            product = products[product_id]
            effective_events = events_by_product.get(product_id, [])
            volume_days = Decimal(0)
            has_missing_dimensions = False
            applicable_dimension_event: ProductDimensionEvent | None = None
            for start, end, held, volume, dimension_event in _volume_segments(
                product_moves,
                effective_events,
                period_start_at,
                period_end_exclusive,
                legacy_volume_liters=product.volume_liters,
            ):
                if held <= 0:
                    continue
                if volume is not None:
                    volume_days += Decimal(held) * _seconds(start, end) * volume
                    applicable_dimension_event = dimension_event
                else:
                    has_missing_dimensions = True
            missing_dimensions = quantity_days > 0 and has_missing_dimensions
            if missing_dimensions:
                problems += 1
            rows.append(
                StorageMeasurement(
                    tenant_id=tenant_id,
                    seller_id=scope_seller_id,
                    warehouse_id=wh_id,
                    product_id=product_id,
                    dimension_event_id=(
                        applicable_dimension_event.id if applicable_dimension_event else None
                    ),
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=quantity_days,
                    movement_start_id=first_movement.id if first_movement else None,
                    movement_end_id=last_movement.id if last_movement else None,
                    liter_days=volume_days,
                    status="missing_dimensions" if missing_dimensions else "calculated",
                )
            )
    seller_ids = {seller_id} if seller_id is not None else set(
        (await session.scalars(select(Seller.id).where(Seller.tenant_id == tenant_id))).all()
    )
    warehouse_ids = operational_warehouse_ids
    scopes = {(r.seller_id, r.warehouse_id) for r in rows}
    scopes |= {(seller_id, wh_id) for seller_id in seller_ids for wh_id in warehouse_ids}
    for seller_id, wh_id in scopes:
        statement = await session.scalar(
            select(StorageStatement).where(
                StorageStatement.tenant_id == tenant_id,
                StorageStatement.seller_id == seller_id,
                StorageStatement.warehouse_id == wh_id,
                StorageStatement.period_start == period_start,
                StorageStatement.period_end == period_end,
            )
        )
        if statement is not None and statement.status != "draft":
            continue
        await session.execute(
            delete(StorageMeasurement).where(
                StorageMeasurement.tenant_id == tenant_id,
                StorageMeasurement.seller_id == seller_id,
                StorageMeasurement.warehouse_id == wh_id,
                StorageMeasurement.period_start == period_start,
                StorageMeasurement.period_end == period_end,
            )
        )
        if statement is None:
            session.add(
                StorageStatement(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=wh_id,
                    period_start=period_start,
                    period_end=period_end,
                    status="draft",
                )
            )
    open_scopes: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for seller_id, wh_id in scopes:
        statement = await session.scalar(
            select(StorageStatement).where(
                StorageStatement.tenant_id == tenant_id,
                StorageStatement.seller_id == seller_id,
                StorageStatement.warehouse_id == wh_id,
                StorageStatement.period_start == period_start,
                StorageStatement.period_end == period_end,
                StorageStatement.status == "draft",
            )
        )
        if statement is not None:
            open_scopes.add((seller_id, wh_id))
    session.add_all([row for row in rows if (row.seller_id, row.warehouse_id) in open_scopes])
    await session.commit()
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "measurements": len(rows),
        "problems": problems,
    }
