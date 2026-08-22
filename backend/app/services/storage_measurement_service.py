from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement


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


def _seconds(a: datetime, b: datetime) -> Decimal:
    return Decimal(str(max(0, (b - a).total_seconds()))) / Decimal(86400)


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
    period_end_exclusive = datetime.combine(period_end + timedelta(days=1), time.min, MOSCOW)

    locations = select(StorageLocation).where(
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.deleted_at.is_(None),
    )
    if warehouse_id is not None:
        locations = locations.where(StorageLocation.warehouse_id == warehouse_id)
    location_rows = list((await session.scalars(locations)).all())
    operational = {row.id: row.warehouse_id for row in location_rows}
    movements = list(
        (
            await session.scalars(
                select(InventoryMovement)
                .where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.storage_location_id.in_(operational or {uuid.UUID(int=0)}),
                )
                .order_by(InventoryMovement.created_at, InventoryMovement.id)
            )
        ).all()
    )
    if seller_id is not None:
        seller_product_ids = set(
            (
                await session.scalars(
                    select(Product.id).where(
                        Product.tenant_id == tenant_id,
                        Product.seller_id == seller_id,
                    )
                )
            ).all()
        )
        movements = [m for m in movements if m.product_id in seller_product_ids]
    product_ids = {m.product_id for m in movements}
    products = {
        p.id: p
        for p in (await session.scalars(select(Product).where(Product.id.in_(product_ids)))).all()
    }
    events = {
        e.product_id: e
        for e in (
            await session.scalars(
                select(ProductDimensionEvent).where(
                    ProductDimensionEvent.tenant_id == tenant_id,
                    ProductDimensionEvent.applied.is_(True),
                )
            )
        ).all()
    }

    rows: list[StorageMeasurement] = []
    problems = 0
    grouped: dict[tuple[uuid.UUID, uuid.UUID], list[InventoryMovement]] = {}
    for movement in movements:
        product = products.get(movement.product_id)
        if product is None or product.seller_id is None:
            continue
        movement_warehouse_id = getattr(movement, "warehouse_id", None)
        warehouse = movement_warehouse_id or operational.get(movement.storage_location_id)
        if warehouse is not None:
            grouped.setdefault((product.seller_id, warehouse), []).append(movement)
    for (seller_id, wh_id), group in grouped.items():
        by_product: dict[uuid.UUID, list[InventoryMovement]] = {}
        for movement in group:
            by_product.setdefault(movement.product_id, []).append(movement)
        for product_id, product_moves in by_product.items():
            quantity = 0
            cursor = period_start_at
            quantity_days = Decimal(0)
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
                cursor = at
                quantity += movement.quantity_delta
                if at >= period_end_exclusive:
                    break
            if cursor < period_end_exclusive:
                if quantity < 0:
                    raise StorageMeasurementError("negative_reconstructed_stock")
                quantity_days += Decimal(quantity) * _seconds(cursor, period_end_exclusive)
            product = products[product_id]
            event = events.get(product_id)
            volume = (
                event.volume_liters
                if event
                else (
                    Decimal(str(product.volume_liters))
                    if product.volume_liters is not None
                    else None
                )
            )
            if quantity_days > 0 and volume is None:
                problems += 1
            rows.append(
                StorageMeasurement(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=wh_id,
                    product_id=product_id,
                    dimension_event_id=event.id if event else None,
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=quantity_days,
                    liter_days=quantity_days * volume if volume is not None else Decimal(0),
                    status="missing_dimensions"
                    if quantity_days > 0 and volume is None
                    else "calculated",
                )
            )
    seller_ids = {seller_id} if seller_id is not None else set(
        (await session.scalars(select(Seller.id).where(Seller.tenant_id == tenant_id))).all()
    )
    warehouse_ids = set(operational.values())
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
