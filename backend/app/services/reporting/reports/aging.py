"""Отчёт «Мёртвые остатки» - товары, не двигавшиеся долгое время."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

if TYPE_CHECKING:
    from app.services.reporting.period import ReportingPeriod
    from app.services.reporting.scope import ReportingScope


def _get_bucket(days_without_movement: int) -> tuple[str, str]:
    """Определить ковш для дней без движения.

    Returns:
        (bucket_key, bucket_label) - ключ и подпись ковша
    """
    if days_without_movement <= 30:
        return ("0_30", "0–30")
    elif days_without_movement <= 60:
        return ("30_60", "30–60")
    elif days_without_movement <= 90:
        return ("60_90", "60–90")
    else:
        return ("90_plus", "90+")


async def build_aging_report(
    session: AsyncSession,
    scope: ReportingScope,
    period: ReportingPeriod,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Собрать отчёт «Мёртвые остатки».

    Args:
        session: асинхронная сессия БД
        scope: доступ пользователя
        period: период отчёта
        filters: фильтры (group_by, search, warehouse_id, seller_id)

    Returns:
        Данные отчёта с мёртвыми остатками сгруппированными по ковшам
    """
    group_by = filters.get("group_by", "product")
    search = filters.get("search", "")
    warehouse_id = filters.get("warehouse_id")
    seller_id_filter = filters.get("seller_id")

    # Если селлер, жёстко используем его ID
    if scope.seller_ids:
        seller_id_filter = next(iter(scope.seller_ids))

    reference_date = date.today()

    # Получить старые остатки
    rows = await _get_aging_rows(
        session,
        tenant_id=scope.tenant_id,
        reference_date=reference_date,
        group_by=group_by,
        search=search,
        warehouse_id=warehouse_id,
        seller_id=seller_id_filter,
    )

    # Подготовить данные для графика (распределение по ковшам)
    bucket_distribution = _calculate_bucket_distribution(rows)

    return {
        "meta": {
            "report_id": "aging",
            "title": "Мёртвые остатки",
            "group_by": group_by,
            "period": {
                "start": period.current.start.isoformat(),
                "end": period.current.end.isoformat(),
            },
            "reference_date": reference_date.isoformat(),
        },
        "rows": rows,
        "totals": _calculate_aging_totals(rows),
        "chart": {
            "type": "stacked_bar",
            "series": bucket_distribution,
        },
    }


async def _get_aging_rows(
    session: AsyncSession,
    tenant_id: Any,
    reference_date: date,
    group_by: str,
    search: str = "",
    warehouse_id: Any = None,
    seller_id: Any = None,
) -> list[dict[str, Any]]:
    """Получить строки отчёта aging."""
    # Сначала получить все товары с положительным остатком
    query = select(
        InventoryBalance,
        Product,
        StorageLocation,
        Warehouse,
        Seller,
    ).join(
        Product, InventoryBalance.product_id == Product.id
    ).join(
        StorageLocation, InventoryBalance.storage_location_id == StorageLocation.id
    ).join(
        Warehouse, StorageLocation.warehouse_id == Warehouse.id
    ).outerjoin(
        Seller, Product.seller_id == Seller.id
    ).where(
        and_(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.qty > 0,
        )
    )

    if warehouse_id:
        query = query.where(StorageLocation.warehouse_id == warehouse_id)
    if seller_id:
        query = query.where(Product.seller_id == seller_id)
    if search:
        search_pattern = f"%{search}%"
        from sqlalchemy import or_
        query = query.where(
            or_(
                Product.sku_code.ilike(search_pattern),
                Product.name.ilike(search_pattern),
            )
        )

    result = await session.execute(query)
    balances_data = result.all()

    rows = []
    for balance, product, location, warehouse, seller in balances_data:
        # Найти последнее движение товара
        movement_query = select(InventoryMovement.created_at).where(
            and_(
                InventoryMovement.product_id == product.id,
                InventoryMovement.tenant_id == tenant_id,
            )
        ).order_by(InventoryMovement.created_at.desc()).limit(1)

        movement_result = await session.execute(movement_query)
        last_movement_dt = movement_result.scalar()

        if last_movement_dt:
            # Если движение есть, считаем дни без движения
            days_without_movement = (reference_date - last_movement_dt.date()).days
        else:
            # Если движения нет, считаем бесконечность
            days_without_movement = 999

        bucket_key, bucket_label = _get_bucket(days_without_movement)
        last_movement_date = last_movement_dt.date() if last_movement_dt else None

        if group_by == "product":
            rows.append({
                "product_id": str(product.id),
                "sku_code": product.sku_code,
                "product_name": product.name,
                "wb_vendor_code": product.wb_vendor_code,
                "seller": seller.name if seller else "",
                "warehouse": warehouse.name,
                "qty": balance.qty,
                "days_without_movement": days_without_movement,
                "bucket_key": bucket_key,
                "bucket_label": bucket_label,
                "last_movement": last_movement_date.strftime("%d.%m.%Y") if last_movement_date else "",
            })
        elif group_by == "warehouse":
            rows.append({
                "warehouse": warehouse.name,
                "qty": balance.qty,
                "days_without_movement": days_without_movement,
                "bucket_key": bucket_key,
                "bucket_label": bucket_label,
            })
        elif group_by == "seller":
            rows.append({
                "seller": seller.name if seller else "Без селлера",
                "qty": balance.qty,
                "days_without_movement": days_without_movement,
                "bucket_key": bucket_key,
                "bucket_label": bucket_label,
            })

    return rows


def _calculate_aging_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Рассчитать итоги для aging."""
    if not rows:
        return {
            "total_qty": 0,
            "avg_days_without_movement": 0,
            "bucket_distribution": {},
        }

    total_qty = sum(r.get("qty", 0) for r in rows)
    avg_days = sum(r.get("days_without_movement", 0) for r in rows) // len(rows) if rows else 0

    # Распределение по ковшам
    bucket_counts = {}
    for row in rows:
        bucket = row.get("bucket_key", "unknown")
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + row.get("qty", 0)

    return {
        "total_qty": total_qty,
        "avg_days_without_movement": avg_days,
        "bucket_distribution": bucket_counts,
    }


def _calculate_bucket_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Собрать данные распределения по ковшам для графика."""
    bucket_data: dict[str, int] = {
        "0_30": 0,
        "30_60": 0,
        "60_90": 0,
        "90_plus": 0,
    }

    for row in rows:
        bucket = row.get("bucket_key", "unknown")
        if bucket in bucket_data:
            bucket_data[bucket] += row.get("qty", 0)

    bucket_labels = {
        "0_30": "0–30 дней",
        "30_60": "30–60 дней",
        "60_90": "60–90 дней",
        "90_plus": "90+ дней",
    }

    return [
        {
            "name": bucket_labels.get(key, key),
            "value": value,
        }
        for key, value in bucket_data.items()
    ]
