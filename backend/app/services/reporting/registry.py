"""Реестр доступных отчётов и их спецификации.

Каждый отчёт в реестре определён один раз и переиспользуется одинаково:
- одна ручка /reports/{report_id}
- один контрактный формат ответа
- один способ экспорта XLSX/CSV
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.reporting.period import ReportingPeriod
    from app.services.reporting.scope import ReportingScope


class ChartType(str, Enum):
    """Тип графика для отчёта."""
    BAR = "bar"
    LINE = "line"
    STACKED_BAR = "stacked_bar"


class Portal(str, Enum):
    """Портал доступа."""
    FF = "ff"
    SELLER = "seller"


@dataclass
class ColumnSpec:
    """Спецификация колонки в отчёте."""
    key: str
    label: str
    width: int  # в пикселях
    align: str = "left"  # "left", "right", "center"
    muted: bool = False  # серый цвет для подподосчётов


@dataclass
class ReportSpec:
    """Спецификация одного отчёта.

    Атрибуты:
        report_id: уникальный идентификатор отчёта
        title: название отчёта
        description: одна строка назначения
        portals: список порталов, на которых отчёт доступен
        columns: список колонок (структура зависит от отчёта)
        chart_type: тип графика (bar/line/stacked_bar)
        show_time_disclaimer: показывать оговорку про время события
        available_group_by: список доступных разрезов
        builder: функция, которая собирает данные отчёта
        has_discrepancy: разрешена ли заливка строк по расхождению
    """
    report_id: str
    title: str
    description: str
    portals: list[Portal]
    columns: list[ColumnSpec]
    chart_type: ChartType
    show_time_disclaimer: bool
    available_group_by: list[str]
    default_group_by: str
    builder: Callable[[AsyncSession, ReportingScope, ReportingPeriod, dict[str, Any]], Any]
    has_discrepancy: bool = False


def get_reports_registry() -> dict[str, ReportSpec]:
    """Получить реестр всех доступных отчётов.

    Реестр используется для:
    1. Валидации report_id в роутах
    2. Определения доступных отчётов для портала (фильтр по portals)
    3. Определения структуры ответа (columns, chart_type)
    4. Функции сборки данных

    Returns:
        Словарь report_id -> ReportSpec
    """
    # Импорты сервисов отчётов размещены здесь, чтобы избежать циклических зависимостей
    from app.services.reporting.reports.aging import build_aging_report
    from app.services.reporting.reports.inbound import build_inbound_report
    from app.services.reporting.reports.on_hand import build_on_hand_report
    from app.services.reporting.reports.outbound import build_outbound_report
    from app.services.reporting.reports.product_movements import build_product_movements_report

    return {
        "product_movements": ReportSpec(
            report_id="product_movements",
            title="Движения по товару",
            description="Приход, расход и перемещение товара за период по категориям",
            portals=[Portal.FF, Portal.SELLER],
            columns=[
                ColumnSpec("product", "Товар", 220),
                ColumnSpec("seller_article", "Артикул продавца", 140),
                ColumnSpec("wb_article", "Артикул WB", 120),
                ColumnSpec("size", "Размер", 80),
                ColumnSpec("barcode", "ШК", 140),
                ColumnSpec("intake", "Приёмка", 90, align="right"),
                ColumnSpec("transfer", "Перемещение", 90, align="right"),
                ColumnSpec("tz_import", "Загрузка ТЗ", 100, align="right"),
                ColumnSpec("mp_unload", "Отгрузка на МП", 110, align="right"),
                ColumnSpec("fbs", "FBS", 80, align="right"),
                ColumnSpec("outbound_shipment", "Отгрузка", 100, align="right"),
                ColumnSpec("discrepancy", "Корректировка", 110, align="right"),
                ColumnSpec("other", "Прочее", 90, align="right"),
            ],
            chart_type=ChartType.BAR,
            show_time_disclaimer=True,
            available_group_by=["product"],
            default_group_by="product",
            builder=build_product_movements_report,
            has_discrepancy=False,
        ),
        "on_hand": ReportSpec(
            report_id="on_hand",
            title="Остатки сейчас",
            description="Сколько единиц каждого товара лежит на складе",
            portals=[Portal.FF, Portal.SELLER],
            columns=[
                ColumnSpec("product", "Товар", 220),
                ColumnSpec("seller_article", "Артикул продавца", 140),
                ColumnSpec("barcode", "ШК", 140),
                ColumnSpec("seller", "Селлер", 160),
                ColumnSpec("warehouse", "Склад", 140),
                ColumnSpec("cells", "Ячеек занято", 100, align="right"),
                ColumnSpec("qty", "Остаток, шт", 100, align="right"),
                ColumnSpec("liters", "Литры", 100, align="right"),
                ColumnSpec("last_movement", "Последнее движение", 130),
            ],
            chart_type=ChartType.BAR,
            show_time_disclaimer=False,
            available_group_by=["product", "warehouse", "seller", "cell"],
            default_group_by="product",
            builder=build_on_hand_report,
            has_discrepancy=True,
        ),
        "inbound": ReportSpec(
            report_id="inbound",
            title="Приход за период",
            description="Сумма приёмок и загрузок товара туристических зон за выбранный период",
            portals=[Portal.FF, Portal.SELLER],
            columns=[
                ColumnSpec("product", "Товар", 220),
                ColumnSpec("seller_article", "Артикул продавца", 140),
                ColumnSpec("seller", "Селлер", 160),
                ColumnSpec("warehouse", "Склад", 140),
                ColumnSpec("total", "Всего принято", 110, align="right"),
                ColumnSpec("intake", "В т.ч. приёмка", 110, align="right", muted=True),
                ColumnSpec("tz_import", "В т.ч. загрузка ТЗ", 130, align="right", muted=True),
                ColumnSpec("avg_per_day", "Средний в день", 110, align="right"),
            ],
            chart_type=ChartType.LINE,
            show_time_disclaimer=True,
            available_group_by=["product", "seller", "warehouse", "day"],
            default_group_by="product",
            builder=build_inbound_report,
            has_discrepancy=False,
        ),
        "outbound": ReportSpec(
            report_id="outbound",
            title="Расход за период",
            description="Сумма отгрузок на маркетплейс и иные каналы за выбранный период",
            portals=[Portal.FF, Portal.SELLER],
            columns=[
                ColumnSpec("product", "Товар", 220),
                ColumnSpec("seller_article", "Артикул продавца", 140),
                ColumnSpec("seller", "Селлер", 160),
                ColumnSpec("warehouse", "Склад", 140),
                ColumnSpec("marketplace", "Маркетплейс", 120),
                ColumnSpec("total", "Всего расход", 110, align="right"),
                ColumnSpec("fbs", "В т.ч. FBS", 90, align="right", muted=True),
                ColumnSpec("mp_unload", "В т.ч. отгрузка на МП", 140, align="right", muted=True),
                ColumnSpec("other", "В т.ч. иные", 90, align="right", muted=True),
                ColumnSpec("avg_per_day", "Средний в день", 110, align="right"),
            ],
            chart_type=ChartType.LINE,
            show_time_disclaimer=True,
            available_group_by=["product", "seller", "warehouse", "marketplace", "day"],
            default_group_by="product",
            builder=build_outbound_report,
            has_discrepancy=False,
        ),
        "aging": ReportSpec(
            report_id="aging",
            title="Мёртвые остатки",
            description="Товары, которые не двигались долгое время, сгруппированные по ковшам дней",
            portals=[Portal.FF, Portal.SELLER],
            columns=[
                ColumnSpec("product", "Товар", 220),
                ColumnSpec("seller_article", "Артикул продавца", 140),
                ColumnSpec("seller", "Селлер", 160),
                ColumnSpec("warehouse", "Склад", 140),
                ColumnSpec("qty", "Остаток, шт", 100, align="right"),
                ColumnSpec("days_without_movement", "Дней без движения", 120, align="right"),
                ColumnSpec("bucket", "Ковш", 120),
                ColumnSpec("last_movement", "Последнее движение", 130),
            ],
            chart_type=ChartType.STACKED_BAR,
            show_time_disclaimer=False,
            available_group_by=["product", "warehouse", "seller"],
            default_group_by="product",
            builder=build_aging_report,
            has_discrepancy=False,
        ),
    }


def get_report_spec(report_id: str) -> ReportSpec | None:
    """Получить спецификацию отчёта по ID.

    Args:
        report_id: идентификатор отчёта

    Returns:
        ReportSpec или None если отчёт не найден
    """
    registry = get_reports_registry()
    return registry.get(report_id)
