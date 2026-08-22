"""Отчёт «Движения по товару» - существующий отчёт, переиспользуемый в новом каркасе.

Этот отчёт уже реализован в inventory_movement_report_service.py как list_product_movement_summary.
Здесь мы просто адаптируем его к новому контракту /reports/{report_id}.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_movement_report_service import (
    REPORT_GROUP_LABELS,
    list_product_movement_summary,
)

if TYPE_CHECKING:
    from app.services.reporting.period import ReportingPeriod
    from app.services.reporting.scope import ReportingScope


async def build_product_movements_report(
    session: AsyncSession,
    scope: ReportingScope,
    period: ReportingPeriod,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Собрать отчёт «Движения по товару».

    Args:
        session: асинхронная сессия БД
        scope: доступ пользователя (seller_ids и т.д.)
        period: период отчёта с возможностью сравнения
        filters: дополнительные фильтры (поиск, разрез и т.д.)

    Returns:
        Данные отчёта в формате {meta, rows, totals, chart, compare}
    """
    start_dt, end_dt = period.current.to_datetimes_utc()

    # Получить данные текущего периода
    rows = await list_product_movement_summary(
        session,
        tenant_id=scope.tenant_id,
        seller_id=next(iter(scope.seller_ids)) if scope.seller_ids else None,
        date_from=start_dt,
        date_to=end_dt,
        search=filters.get("search"),
    )

    # Сравнение (если запрошено)
    compare_rows = None
    if period.compare:
        compare_start_dt, compare_end_dt = period.compare.to_datetimes_utc()
        compare_rows = await list_product_movement_summary(
            session,
            tenant_id=scope.tenant_id,
            seller_id=next(iter(scope.seller_ids)) if scope.seller_ids else None,
            date_from=compare_start_dt,
            date_to=compare_end_dt,
            search=filters.get("search"),
        )

    # Формировать ответ в контракте
    return {
        "meta": {
            "report_id": "product_movements",
            "title": "Движения по товару",
            "group_labels": REPORT_GROUP_LABELS,
            "period": {
                "start": period.current.start.isoformat(),
                "end": period.current.end.isoformat(),
            },
            "compare": {
                "mode": period.compare_mode.value,
                "start": period.compare.start.isoformat() if period.compare else None,
                "end": period.compare.end.isoformat() if period.compare else None,
            } if period.compare else None,
        },
        "rows": [_row_to_dict(row) for row in rows],
        "compare_rows": [_row_to_dict(row) for row in compare_rows] if compare_rows else None,
        "totals": _calculate_totals(rows),
        "chart": {
            "type": "bar",
            "series": _build_chart_data(rows),
        },
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Преобразовать строку отчёта в словарь."""
    return {
        "product_id": str(row.product_id),
        "sku_code": row.sku_code,
        "product_name": row.product_name,
        "wb_vendor_code": row.wb_vendor_code,
        "wb_barcode": row.wb_barcode,
        "seller_id": str(row.seller_id) if row.seller_id else None,
        "seller_name": row.seller_name,
        "photo_url": row.photo_url,
        "groups": {k: {"in": v[0], "out": v[1]} for k, v in row.groups.items()},
    }


def _calculate_totals(rows: list[Any]) -> dict[str, int]:
    """Рассчитать итоги для строк сводки."""
    totals: dict[str, dict[str, int]] = {}

    for row in rows:
        for group_key, (in_qty, out_qty) in row.groups.items():
            if group_key not in totals:
                totals[group_key] = {"in": 0, "out": 0}
            totals[group_key]["in"] += in_qty
            totals[group_key]["out"] += out_qty

    return totals


def _build_chart_data(rows: list[Any]) -> list[dict[str, Any]]:
    """Собрать данные для графика (по группам движений)."""
    chart_data: dict[str, int] = {}

    for row in rows:
        for group_key, (in_qty, out_qty) in row.groups.items():
            if group_key not in chart_data:
                chart_data[group_key] = 0
            chart_data[group_key] += in_qty + out_qty

    return [
        {
            "name": REPORT_GROUP_LABELS.get(key, key),
            "value": value,
        }
        for key, value in chart_data.items()
    ]
