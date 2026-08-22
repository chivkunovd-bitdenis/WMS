"""API роуты для раздела «Отчёты» (/reports/*).

Контракт:
- GET /reports — список доступных отчётов
- GET /reports/{report_id} — данные отчёта
- GET /reports/{report_id}/export — выгрузка в XLSX/CSV
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_inventory_read_access, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.reporting import (
    CompareMode,
    PeriodPreset,
    ReportingPeriod,
    get_report_spec,
    get_reports_registry,
    resolve_reporting_scope,
)
from app.services.reporting.excel_export import ExportLimitExceeded, export_to_csv, export_to_xlsx
from app.services.reporting.registry import Portal

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)


class ReportInfoOut(BaseModel):
    """Информация об одном доступном отчёте."""

    report_id: str
    title: str
    description: str


class ReportsListOut(BaseModel):
    """Список доступных отчётов."""

    reports: list[ReportInfoOut]


@router.get("", response_model=ReportsListOut)
async def list_reports(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReportsListOut:
    """Получить список доступных отчётов для текущего пользователя.

    Возвращает только отчёты, доступные на портале пользователя (ФФ или Селлер).
    """
    await assert_inventory_read_access(session, user)

    # Определить портал пользователя
    portal = Portal.SELLER if user.seller_id else Portal.FF

    registry = get_reports_registry()
    available_reports = []

    for report_id, spec in registry.items():
        if portal in spec.portals:
            available_reports.append(
                ReportInfoOut(
                    report_id=report_id,
                    title=spec.title,
                    description=spec.description,
                )
            )

    return ReportsListOut(reports=available_reports)


class ReportDataOut(BaseModel):
    """Данные отчёта."""

    meta: dict[str, Any]
    rows: list[dict[str, Any]]
    compare_rows: list[dict[str, Any]] | None = None
    totals: dict[str, Any]
    chart: dict[str, Any]


@router.get("/{report_id}", response_model=ReportDataOut)
async def get_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    period: Annotated[str, Query()] = "month",
    compare: Annotated[str, Query()] = "previous",
    group_by: Annotated[str, Query()] = "",
    search: Annotated[str, Query()] = "",
    warehouse_id: Annotated[str | None, Query()] = None,
    seller_id: Annotated[str | None, Query()] = None,
    marketplace_id: Annotated[str | None, Query()] = None,
) -> ReportDataOut:
    """Получить данные отчёта.

    Query параметры:
        - date_from, date_to: диапазон дат (если period="custom")
        - period: пресет периода (today/week/month/quarter/year/custom)
        - compare: режим сравнения (none/previous/year_ago)
        - group_by: разрез отчёта (product/warehouse/seller/marketplace/day/cell)
        - search: поиск по товару
        - warehouse_id, seller_id, marketplace_id: фильтры

    Returns:
        Данные отчёта в формате ReportDataOut
    """
    await assert_inventory_read_access(session, user)

    # Валидировать report_id
    spec = get_report_spec(report_id)
    if not spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Отчёт {report_id} не найден",
        )

    # Проверить доступ к отчёту на основе портала
    portal = Portal.SELLER if user.seller_id else Portal.FF
    if portal not in spec.portals:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"У вас нет доступа к отчёту {report_id}",
        )

    # Резолвить scope доступа пользователя
    scope = await resolve_reporting_scope(user, session)

    # Построить период
    try:
        if period == "custom":
            if not date_from or not date_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Для периода 'custom' требуются date_from и date_to",
                )
            if date_from > date_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Дата 'с' не может быть позже даты 'по'",
                )
            reporting_period = ReportingPeriod.from_dates(
                start=date_from,
                end=date_to,
                compare_mode=CompareMode(compare),
            )
        else:
            reporting_period = ReportingPeriod.from_preset(
                preset=PeriodPreset(period),
                compare_mode=CompareMode(compare),
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Использовать default group_by если не указан
    if not group_by:
        group_by = spec.default_group_by

    # Валидировать group_by
    if group_by not in spec.available_group_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Для отчёта {report_id} недоступен разрез '{group_by}'",
        )

    # Собрать фильтры
    filters: dict[str, Any] = {
        "group_by": group_by,
        "search": search,
        "warehouse_id": warehouse_id,
        "seller_id": seller_id,
        "marketplace_id": marketplace_id,
    }

    # Вызвать builder отчёта
    try:
        report_data = await spec.builder(session, scope, reporting_period, filters)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Отчёт не открылся. Повторите запрос через минуту",
        ) from e

    return ReportDataOut(**report_data)


@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    format: Annotated[str, Query()] = "xlsx",
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    period: Annotated[str, Query()] = "month",
    compare: Annotated[str, Query()] = "previous",
    group_by: Annotated[str, Query()] = "",
    search: Annotated[str, Query()] = "",
    warehouse_id: Annotated[str | None, Query()] = None,
    seller_id: Annotated[str | None, Query()] = None,
    marketplace_id: Annotated[str | None, Query()] = None,
) -> StreamingResponse:
    """Экспортировать данные отчёта в XLSX или CSV.

    Поддерживаемые форматы: xlsx, csv
    Лимит: 25 000 строк
    """
    await assert_inventory_read_access(session, user)

    # Валидировать report_id
    spec = get_report_spec(report_id)
    if not spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Отчёт {report_id} не найден",
        )

    # Проверить доступ
    portal = Portal.SELLER if user.seller_id else Portal.FF
    if portal not in spec.portals:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"У вас нет доступа к отчёту {report_id}",
        )

    # Резолвить scope
    scope = await resolve_reporting_scope(user, session)

    # Построить период
    try:
        if period == "custom":
            if not date_from or not date_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Для периода 'custom' требуются date_from и date_to",
                )
            if date_from > date_to:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Дата 'с' не может быть позже даты 'по'",
                )
            reporting_period = ReportingPeriod.from_dates(
                start=date_from,
                end=date_to,
                compare_mode=CompareMode(compare),
            )
        else:
            reporting_period = ReportingPeriod.from_preset(
                preset=PeriodPreset(period),
                compare_mode=CompareMode(compare),
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Использовать default group_by если не указан
    if not group_by:
        group_by = spec.default_group_by

    # Валидировать group_by
    if group_by not in spec.available_group_by:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Для отчёта {report_id} недоступен разрез '{group_by}'",
        )

    # Собрать фильтры
    filters: dict[str, Any] = {
        "group_by": group_by,
        "search": search,
        "warehouse_id": warehouse_id,
        "seller_id": seller_id,
        "marketplace_id": marketplace_id,
    }

    # Получить данные отчёта
    try:
        report_data = await spec.builder(session, scope, reporting_period, filters)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Отчёт не открылся. Повторите запрос через минуту",
        ) from e

    rows = report_data.get("rows", [])

    # Проверить лимит
    if len(rows) > 25000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Больше 25 000 строк — разбейте на несколько периодов",
        )

    # Подготовить колонки для экспорта
    export_columns = [col.key for col in spec.columns]

    # Экспортировать в нужном формате
    try:
        if format == "xlsx":
            content = export_to_xlsx(rows, export_columns, title=spec.title)
            return StreamingResponse(
                iter([content]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={report_id}.xlsx"},
            )
        elif format == "csv":
            content = export_to_csv(rows, export_columns)
            return StreamingResponse(
                iter([content.encode("utf-8")]),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={report_id}.csv"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неподдерживаемый формат: {format}. Используйте xlsx или csv",
            )
    except ExportLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


# NOTE: Существующий роут GET /operations/inventory-movements/summary остаётся
# deprecated и требует отдельного редиректа (может быть добавлен позже как миграция).
