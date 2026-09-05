from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.stock_direction import StockDirection, StockMonthlySnapshot
from app.models.storage_location import StorageLocation
from app.services.fbs_stock_publish_service import schedule_seller_stock_publish

MSK = ZoneInfo("Europe/Moscow")


class StockDirectionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StockDirectionTotals:
    fbs: int = 0
    reserved: int = 0
    total: int = 0
    has_any: bool = False


@dataclass(frozen=True, slots=True)
class StockDistribution:
    product_id: uuid.UUID
    quantity_total: int
    quantity_fbs: int
    quantity_reserved: int
    quantity_free_fbo: int


def normalize_snapshot_month(value: date) -> date:
    return date(value.year, value.month, 1)


def current_snapshot_month() -> date:
    return normalize_snapshot_month(datetime.now(MSK).date())


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise StockDirectionError("empty_name")
    return cleaned


def _clean_comment(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned if cleaned else None


async def _get_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    seller_scope: uuid.UUID | None = None,
) -> Product:
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id:
        raise StockDirectionError("product_not_found")
    if seller_scope is not None and product.seller_id != seller_scope:
        raise StockDirectionError("forbidden")
    return product


async def product_on_hand_total(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> int:
    stmt = select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
        InventoryBalance.tenant_id == tenant_id,
        InventoryBalance.product_id == product_id,
    )
    return int(await session.scalar(stmt) or 0)


async def _direction_quantity_total(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    exclude_direction_id: uuid.UUID | None = None,
) -> int:
    stmt = select(func.coalesce(func.sum(StockDirection.quantity), 0)).where(
        StockDirection.tenant_id == tenant_id,
        StockDirection.product_id == product_id,
    )
    if exclude_direction_id is not None:
        stmt = stmt.where(StockDirection.id != exclude_direction_id)
    return int(await session.scalar(stmt) or 0)


async def _assert_directions_fit_stock(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    next_quantity: int,
    exclude_direction_id: uuid.UUID | None = None,
) -> None:
    if next_quantity < 0:
        raise StockDirectionError("invalid_quantity")
    on_hand = await product_on_hand_total(session, tenant_id, product_id)
    already = await _direction_quantity_total(
        session,
        tenant_id,
        product_id,
        exclude_direction_id=exclude_direction_id,
    )
    if already + next_quantity > on_hand:
        raise StockDirectionError("directions_exceed_stock")


async def list_stock_directions(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    seller_scope: uuid.UUID | None = None,
) -> list[StockDirection]:
    await _get_product(session, tenant_id, product_id, seller_scope=seller_scope)
    stmt = (
        select(StockDirection)
        .where(
            StockDirection.tenant_id == tenant_id,
            StockDirection.product_id == product_id,
        )
        # created_at приходит из CURRENT_TIMESTAMP: в PostgreSQL это микросекунды,
        # а в SQLite — целые секунды, и два направления, заведённые подряд,
        # получают одно значение. Без третьего ключа порядок между ними не
        # определён, и список прыгает при каждом открытии. Разрешаем по имени:
        # id здесь случайный UUID и в качестве ключа бессмыслен.
        .order_by(
            StockDirection.is_fbs.desc(),
            StockDirection.created_at.asc(),
            StockDirection.name.asc(),
        )
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_stock_direction(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    name: str,
    quantity: int,
    is_fbs: bool,
    comment: str | None = None,
    seller_scope: uuid.UUID | None = None,
) -> StockDirection:
    product = await _get_product(session, tenant_id, product_id, seller_scope=seller_scope)
    clean_name = _clean_name(name)
    clean_comment = _clean_comment(comment)
    await _assert_directions_fit_stock(
        session,
        tenant_id,
        product_id,
        next_quantity=int(quantity),
    )
    direction = StockDirection(
        tenant_id=tenant_id,
        product_id=product_id,
        name=clean_name,
        comment=clean_comment,
        quantity=int(quantity),
        is_fbs=False,
    )
    session.add(direction)
    schedule_seller_stock_publish(session, tenant_id, product.seller_id)
    await session.commit()
    await session.refresh(direction)
    return direction


async def update_stock_direction(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    direction_id: uuid.UUID,
    *,
    name: str | None = None,
    quantity: int | None = None,
    is_fbs: bool | None = None,
    comment: str | None = None,
    set_comment: bool = False,
    seller_scope: uuid.UUID | None = None,
) -> StockDirection:
    direction = await session.get(StockDirection, direction_id)
    if direction is None or direction.tenant_id != tenant_id:
        raise StockDirectionError("direction_not_found")
    product = await _get_product(
        session,
        tenant_id,
        direction.product_id,
        seller_scope=seller_scope,
    )
    if quantity is not None:
        await _assert_directions_fit_stock(
            session,
            tenant_id,
            direction.product_id,
            next_quantity=int(quantity),
            exclude_direction_id=direction.id,
        )
        direction.quantity = int(quantity)
    if name is not None:
        direction.name = _clean_name(name)
    if set_comment:
        direction.comment = _clean_comment(comment)
    direction.is_fbs = False
    direction.updated_at = datetime.now(UTC)
    schedule_seller_stock_publish(session, tenant_id, product.seller_id)
    await session.commit()
    await session.refresh(direction)
    return direction


async def delete_stock_direction(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    direction_id: uuid.UUID,
    *,
    seller_scope: uuid.UUID | None = None,
) -> None:
    direction = await session.get(StockDirection, direction_id)
    if direction is None or direction.tenant_id != tenant_id:
        raise StockDirectionError("direction_not_found")
    product = await _get_product(
        session,
        tenant_id,
        direction.product_id,
        seller_scope=seller_scope,
    )
    await session.delete(direction)
    schedule_seller_stock_publish(session, tenant_id, product.seller_id)
    await session.commit()


async def direction_totals_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> dict[uuid.UUID, StockDirectionTotals]:
    if not product_ids:
        return {}
    fbs_qty = func.coalesce(
        func.sum(case((StockDirection.is_fbs.is_(True), StockDirection.quantity), else_=0)),
        0,
    )
    reserved_qty = func.coalesce(
        func.sum(case((StockDirection.is_fbs.is_(False), StockDirection.quantity), else_=0)),
        0,
    )
    count_qty = func.count(StockDirection.id)
    stmt = (
        select(StockDirection.product_id, fbs_qty, reserved_qty, count_qty)
        .where(
            StockDirection.tenant_id == tenant_id,
            StockDirection.product_id.in_(product_ids),
        )
        .group_by(StockDirection.product_id)
    )
    rows = (await session.execute(stmt)).all()
    return {
        product_id: StockDirectionTotals(
            fbs=int(fbs or 0),
            reserved=int(reserved or 0),
            total=int(fbs or 0) + int(reserved or 0),
            has_any=int(count or 0) > 0,
        )
        for product_id, fbs, reserved, count in rows
    }


async def fbs_reserved_totals_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    warehouse_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, int]:
    from app.services.fbs_stock_availability_service import fbs_reserved_by_product

    return await fbs_reserved_by_product(session, tenant_id, warehouse_id, product_ids)


async def stock_totals_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    warehouse_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryBalance.product_id,
            func.coalesce(func.sum(InventoryBalance.quantity), 0),
        )
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id.in_(product_ids),
        )
        .group_by(InventoryBalance.product_id)
    )
    if warehouse_id is not None:
        stmt = stmt.join(
            StorageLocation,
            StorageLocation.id == InventoryBalance.storage_location_id,
        ).where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id == warehouse_id,
        )
    return {pid: int(qty or 0) for pid, qty in (await session.execute(stmt)).all()}


async def distributions_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    *,
    warehouse_id: uuid.UUID | None = None,
) -> dict[uuid.UUID, StockDistribution]:
    stock_totals = await stock_totals_by_product(
        session,
        tenant_id,
        product_ids,
        warehouse_id=warehouse_id,
    )
    direction_totals = await direction_totals_by_product(session, tenant_id, product_ids)
    from app.services.fbs_stock_availability_service import fbs_allocated_available_by_product

    allocated = await fbs_allocated_available_by_product(
        session, tenant_id, warehouse_id, product_ids
    )
    reserved = await fbs_reserved_totals_by_product(
        session, tenant_id, product_ids, warehouse_id=warehouse_id
    )
    units_products = set(await session.scalars(select(Product.id).where(
        Product.tenant_id == tenant_id,
        Product.id.in_(product_ids),
        Product.fbs_units_mode.is_(True),
    )))
    distributions: dict[uuid.UUID, StockDistribution] = {}
    for product_id in product_ids:
        total = int(stock_totals.get(product_id, 0))
        directions = direction_totals.get(product_id, StockDirectionTotals())
        fbs = allocated.get(product_id, 0) + (
            reserved.get(product_id, 0) if product_id in units_products else 0
        )
        distributions[product_id] = StockDistribution(
            product_id=product_id,
            quantity_total=total,
            quantity_fbs=fbs,
            quantity_reserved=directions.total,
            quantity_free_fbo=max(0, total - directions.total - fbs),
        )
    return distributions


async def consume_fbs_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> None:
    if quantity < 1:
        raise StockDirectionError("invalid_quantity")
    totals = await direction_totals_by_product(session, tenant_id, [product_id])
    if not totals.get(product_id, StockDirectionTotals()).has_any:
        return
    remaining = quantity
    stmt = (
        select(StockDirection)
        .where(
            StockDirection.tenant_id == tenant_id,
            StockDirection.product_id == product_id,
            StockDirection.is_fbs.is_(True),
        )
        .order_by(StockDirection.created_at.asc())
        .with_for_update()
    )
    directions = list((await session.execute(stmt)).scalars().all())
    if sum(int(d.quantity) for d in directions) < quantity:
        raise StockDirectionError("insufficient_fbs_pool")
    for direction in directions:
        if remaining <= 0:
            break
        deduct = min(int(direction.quantity), remaining)
        direction.quantity = int(direction.quantity) - deduct
        direction.updated_at = datetime.now(UTC)
        remaining -= deduct


async def restore_fbs_pool(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
) -> None:
    if quantity < 1:
        raise StockDirectionError("invalid_quantity")
    totals = await direction_totals_by_product(session, tenant_id, [product_id])
    if not totals.get(product_id, StockDirectionTotals()).has_any:
        return
    stmt = (
        select(StockDirection)
        .where(
            StockDirection.tenant_id == tenant_id,
            StockDirection.product_id == product_id,
            StockDirection.is_fbs.is_(True),
        )
        .order_by(StockDirection.created_at.asc())
        .with_for_update()
    )
    direction = (await session.execute(stmt)).scalars().first()
    if direction is None:
        raise StockDirectionError("insufficient_fbs_pool")
    direction.quantity = int(direction.quantity) + quantity
    direction.updated_at = datetime.now(UTC)


async def list_monthly_snapshots(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    month: date,
) -> list[StockMonthlySnapshot]:
    snapshot_month = normalize_snapshot_month(month)
    stmt = (
        select(StockMonthlySnapshot)
        .join(Product, Product.id == StockMonthlySnapshot.product_id)
        .options(selectinload(StockMonthlySnapshot.product))
        .where(
            StockMonthlySnapshot.tenant_id == tenant_id,
            StockMonthlySnapshot.snapshot_month == snapshot_month,
        )
        .order_by(Product.sku_code)
    )
    return list((await session.execute(stmt)).scalars().all())


async def take_monthly_snapshot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    month: date,
) -> list[StockMonthlySnapshot]:
    snapshot_month = normalize_snapshot_month(month)
    existing_snapshots = await list_monthly_snapshots(session, tenant_id, snapshot_month)
    if existing_snapshots:
        return existing_snapshots
    if snapshot_month != current_snapshot_month():
        raise StockDirectionError("monthly_snapshot_historical_empty")

    products = list(
        (
            await session.execute(
                select(Product.id).where(Product.tenant_id == tenant_id).order_by(Product.sku_code)
            )
        ).scalars()
    )
    if not products:
        raise StockDirectionError("monthly_snapshot_empty")
    distributions = await distributions_by_product(session, tenant_id, products)
    snapshots: list[StockMonthlySnapshot] = []
    for product_id in products:
        dist = distributions[product_id]
        row = StockMonthlySnapshot(
            tenant_id=tenant_id,
            product_id=product_id,
            snapshot_month=snapshot_month,
            quantity_total=dist.quantity_total,
            quantity_fbs=dist.quantity_fbs,
            quantity_reserved=dist.quantity_reserved,
            quantity_free_fbo=dist.quantity_free_fbo,
        )
        session.add(row)
        snapshots.append(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        persisted = await list_monthly_snapshots(session, tenant_id, snapshot_month)
        if persisted:
            return persisted
        raise
    return await list_monthly_snapshots(session, tenant_id, snapshot_month)
