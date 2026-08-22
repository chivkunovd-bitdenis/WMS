"""Отчёт «Остатки сейчас» - снимок текущих остатков по товарам."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, select
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


async def build_on_hand_report(
    session: AsyncSession,
    scope: ReportingScope,
    period: ReportingPeriod,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Собрать отчёт «Остатки сейчас».

    Args:
        session: асинхронная сессия БД
        scope: доступ пользователя
        period: период отчёта
        filters: фильтры (group_by, search, warehouse_id, seller_id, marketplace_id)

    Returns:
        Данные отчёта с текущими остатками
    """
    group_by = filters.get("group_by", "product")
    search = filters.get("search", "")
    warehouse_id = filters.get("warehouse_id")
    seller_id_filter = filters.get("seller_id")

    # Если селлер, жёстко используем его ID из scope
    if scope.seller_ids:
        seller_id_filter = next(iter(scope.seller_ids))

    # Получить текущие остатки
    rows = await _get_on_hand_rows(
        session,
        tenant_id=scope.tenant_id,
        group_by=group_by,
        search=search,
        warehouse_id=warehouse_id,
        seller_id=seller_id_filter,
    )

    return {
        "meta": {
            "report_id": "on_hand",
            "title": "Остатки сейчас",
            "group_by": group_by,
            "period": {
                "start": period.current.start.isoformat(),
                "end": period.current.end.isoformat(),
            },
        },
        "rows": rows,
        "totals": _calculate_on_hand_totals(rows, group_by),
        "chart": {
            "type": "bar",
            "series": _build_on_hand_chart(rows, group_by),
        },
    }


async def _get_on_hand_rows(
    session: AsyncSession,
    tenant_id: Any,
    group_by: str,
    search: str = "",
    warehouse_id: Any = None,
    seller_id: Any = None,
) -> list[dict[str, Any]]:
    """Получить строки отчёта остатков."""
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
    rows_data = result.all()

    # Преобразовать в формат отчёта
    rows = []
    for balance, product, location, warehouse, seller in rows_data:
        # Получить последнее движение
        movement_query = select(InventoryMovement.created_at).where(
            and_(
                InventoryMovement.product_id == product.id,
                InventoryMovement.tenant_id == tenant_id,
            )
        ).order_by(InventoryMovement.created_at.desc()).limit(1)

        last_movement_result = await session.execute(movement_query)
        last_movement_dt = last_movement_result.scalar()
        last_movement_date = last_movement_dt.date() if last_movement_dt else None

        # Определить расхождение (текущий остаток < последней инвентаризации)
        # TODO: реализовать проверку с инвентаризацией
        has_discrepancy = False

        if group_by == "product":
            rows.append({
                "product_id": str(product.id),
                "sku_code": product.sku_code,
                "product_name": product.name,
                "wb_vendor_code": product.wb_vendor_code,
                "barcode": product.wb_barcode,
                "seller": seller.name if seller else "",
                "warehouse": warehouse.name,
                "cells": 1,  # TODO: считать реальное число ячеек
                "qty": balance.qty,
                "liters": balance.liters or 0,
                "last_movement": last_movement_date.strftime("%d.%m.%Y") if last_movement_date else "",
                "has_discrepancy": has_discrepancy,
            })
        elif group_by == "warehouse":
            # Агрегировать по складу
            rows.append({
                "warehouse": warehouse.name,
                "products_count": 1,  # TODO: считать уникальные товары
                "qty": balance.qty,
                "liters": balance.liters or 0,
            })
        elif group_by == "seller":
            # Агрегировать по селлеру
            rows.append({
                "seller": seller.name if seller else "Без селлера",
                "products_count": 1,
                "qty": balance.qty,
                "liters": balance.liters or 0,
            })
        elif group_by == "cell":
            # По ячейке
            rows.append({
                "warehouse": warehouse.name,
                "cell": location.code,
                "product": f"{product.sku_code} - {product.name}",
                "qty": balance.qty,
            })

    return rows


def _calculate_on_hand_totals(rows: list[dict[str, Any]], group_by: str) -> dict[str, Any]:
    """Рассчитать итоги для остатков."""
    if not rows:
        return {"qty": 0, "liters": 0}

    total_qty = sum(r.get("qty", 0) for r in rows)
    total_liters = sum(r.get("liters", 0) for r in rows)

    return {
        "qty": total_qty,
        "liters": total_liters,
    }


def _build_on_hand_chart(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    """Собрать данные графика остатков."""
    if group_by == "product" and len(rows) > 10:
        # Top-10 товаров по количеству
        top_rows = sorted(rows, key=lambda x: x.get("qty", 0), reverse=True)[:10]
    else:
        top_rows = rows

    return [
        {
            "name": r.get("product_name") or r.get("warehouse") or r.get("seller", "Неизвестно"),
            "value": r.get("qty", 0),
        }
        for r in top_rows
    ]
