"""Отчёт «Приход за период» - сумма приёмок и загрузок ТЗ."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import (
    MOVEMENT_TYPE_INBOUND_INTAKE,
    MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
    InventoryMovement,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.warehouse import Warehouse

if TYPE_CHECKING:
    from app.services.reporting.period import ReportingPeriod
    from app.services.reporting.scope import ReportingScope


async def build_inbound_report(
    session: AsyncSession,
    scope: ReportingScope,
    period: ReportingPeriod,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Собрать отчёт «Приход за период».

    Args:
        session: асинхронная сессия БД
        scope: доступ пользователя
        period: период отчёта
        filters: фильтры (group_by, search, warehouse_id, seller_id)

    Returns:
        Данные отчёта с приходами
    """
    group_by = filters.get("group_by", "product")
    search = filters.get("search", "")
    warehouse_id = filters.get("warehouse_id")
    seller_id_filter = filters.get("seller_id")

    # Если селлер, жёстко используем его ID
    if scope.seller_ids:
        seller_id_filter = next(iter(scope.seller_ids))

    start_dt, end_dt = period.current.to_datetimes_utc()

    # Получить движения приёмки/ТЗ
    rows = await _get_inbound_rows(
        session,
        tenant_id=scope.tenant_id,
        date_from=start_dt,
        date_to=end_dt,
        group_by=group_by,
        search=search,
        warehouse_id=warehouse_id,
        seller_id=seller_id_filter,
    )

    return {
        "meta": {
            "report_id": "inbound",
            "title": "Приход за период",
            "group_by": group_by,
            "period": {
                "start": period.current.start.isoformat(),
                "end": period.current.end.isoformat(),
                "days": period.current.days(),
            },
        },
        "rows": rows,
        "totals": _calculate_inbound_totals(rows),
        "chart": {
            "type": "line",
            "series": _build_inbound_chart(rows, group_by),
        },
    }


async def _get_inbound_rows(
    session: AsyncSession,
    tenant_id: Any,
    date_from: Any,
    date_to: Any,
    group_by: str,
    search: str = "",
    warehouse_id: Any = None,
    seller_id: Any = None,
) -> list[dict[str, Any]]:
    """Получить строки отчёта приходов."""
    query = select(
        func.sum(InventoryMovement.quantity_delta).label("total_qty"),
        func.sum(
            func.case(
                (InventoryMovement.movement_type == MOVEMENT_TYPE_INBOUND_INTAKE, InventoryMovement.quantity_delta),
                else_=0,
            )
        ).label("intake_qty"),
        func.sum(
            func.case(
                (InventoryMovement.movement_type == MOVEMENT_TYPE_PRODUCT_TZ_IMPORT, InventoryMovement.quantity_delta),
                else_=0,
            )
        ).label("tz_import_qty"),
        Product,
        Seller,
        Warehouse,
        func.cast(InventoryMovement.created_at, any).label("movement_date"),
    ).join(
        Product, InventoryMovement.product_id == Product.id
    ).outerjoin(
        Seller, Product.seller_id == Seller.id
    ).outerjoin(
        Warehouse, and_(
            InventoryMovement.storage_location_id.is_(None),
        ),
    ).where(
        and_(
            InventoryMovement.tenant_id == tenant_id,
            InventoryMovement.created_at >= date_from,
            InventoryMovement.created_at <= date_to,
            InventoryMovement.movement_type.in_([
                MOVEMENT_TYPE_INBOUND_INTAKE,
                MOVEMENT_TYPE_PRODUCT_TZ_IMPORT,
            ]),
            InventoryMovement.quantity_delta > 0,
        )
    )

    if warehouse_id:
        query = query.where(Warehouse.id == warehouse_id)
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

    if group_by == "product":
        query = query.group_by(Product.id, Seller.id)
    elif group_by == "seller":
        query = query.group_by(Seller.id)
    elif group_by == "warehouse":
        query = query.group_by(Warehouse.id)
    elif group_by == "day":
        query = query.group_by(func.date(InventoryMovement.created_at))

    result = await session.execute(query)
    rows_data = result.all()

    rows = []
    for row in rows_data:
        total_qty = row.total_qty or 0
        intake_qty = row.intake_qty or 0
        tz_import_qty = row.tz_import_qty or 0
        days_in_period = 30  # TODO: получить реальное число дней

        if group_by == "product":
            rows.append({
                "product_id": str(row.Product.id),
                "sku_code": row.Product.sku_code,
                "product_name": row.Product.name,
                "wb_vendor_code": row.Product.wb_vendor_code,
                "seller": row.Seller.name if row.Seller else "",
                "total": total_qty,
                "intake": intake_qty,
                "tz_import": tz_import_qty,
                "avg_per_day": total_qty // days_in_period if days_in_period > 0 else 0,
            })
        elif group_by == "seller":
            rows.append({
                "seller": row.Seller.name if row.Seller else "Без селлера",
                "products_count": 1,
                "total": total_qty,
                "intake": intake_qty,
                "tz_import": tz_import_qty,
            })
        elif group_by == "warehouse":
            rows.append({
                "warehouse": row.Warehouse.name if row.Warehouse else "Неизвестно",
                "products_count": 1,
                "total": total_qty,
            })
        elif group_by == "day":
            rows.append({
                "date": row.movement_date.strftime("%d.%m.%Y") if row.movement_date else "",
                "products_count": 1,
                "total": total_qty,
            })

    return rows


def _calculate_inbound_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Рассчитать итоги для приходов."""
    if not rows:
        return {"total": 0, "intake": 0, "tz_import": 0}

    total = sum(r.get("total", 0) for r in rows)
    intake = sum(r.get("intake", 0) for r in rows)
    tz_import = sum(r.get("tz_import", 0) for r in rows)

    return {
        "total": total,
        "intake": intake,
        "tz_import": tz_import,
    }


def _build_inbound_chart(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    """Собрать данные графика приходов."""
    if not rows:
        return []

    return [
        {
            "name": r.get("product_name") or r.get("seller") or r.get("warehouse") or r.get("date", ""),
            "value": r.get("total", 0),
        }
        for r in rows
    ]
