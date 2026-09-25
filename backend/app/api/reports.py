from __future__ import annotations

import urllib.parse
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.deps import (
    assert_inventory_read_access,
    get_current_user,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services.reporting_service import (
    MOVEMENT_PAGE_LIMIT,
    build_inventory_report,
    build_inventory_workbook,
    build_overview,
    inventory_workbook_filename,
    list_product_movements,
    normalize_period,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _content_disposition(filename: str) -> str:
    """RFC 5987: заголовок не может нести кириллицу как есть — даём ASCII-запасной
    вариант и полное имя в filename* для браузеров, которые его понимают."""
    ascii_fallback = "report.xlsx"
    encoded = urllib.parse.quote(filename)
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


@router.get("/inventory")
async def get_inventory_report(user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()], date_to: Annotated[datetime, Query()],
    group_by: Annotated[str, Query()] = "product", page: Annotated[int, Query(ge=1)] = 1,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    # WMS-531 R5: параметр принимается и полностью игнорируется, чтобы старый
    # клиент со складом в адресе не получил ошибку до переделки экрана.
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str, Query()] = "asc",
) -> dict[str, object]:
    await assert_inventory_read_access(session, user)
    try:
        return await build_inventory_report(session, user.tenant_id, date_from=date_from,
            date_to=date_to, group_by=group_by, page=page,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            warehouse_id=warehouse_id, search=search, sort_by=sort_by,
            sort_order=sort_order)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)) from exc


@router.get("/inventory/movements")
async def get_product_movements(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    operation: Annotated[str | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict[str, object]:
    """Движения за период: когда приехало, когда уехало и по какому документу.

    Раскрыть можно товар (`product_id`) или вид движения (`operation`) — второй
    случай нужен группировке «по видам», где третьего уровня раньше не было.
    `page` — постраничная догрузка (WMS-531 R11, порция — `MOVEMENT_PAGE_LIMIT`).
    """
    await assert_inventory_read_access(session, user)
    try:
        rows, truncated, total = await list_product_movements(
            session,
            user.tenant_id,
            product_id=product_id,
            operation=operation,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            warehouse_id=warehouse_id,
            page=page,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return {
        "rows": rows, "truncated": truncated, "total": total,
        "page": page, "limit": MOVEMENT_PAGE_LIMIT,
    }


@router.get("/overview")
async def get_reports_overview(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    await assert_inventory_read_access(session, user)
    try:
        return await build_overview(
            session,
            user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            warehouse_id=warehouse_id,
            search=search,
            include_technical_warnings=user.role == FULFILLMENT_ADMIN,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/inventory/export.xlsx")
async def export_inventory_workbook(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()], date_to: Annotated[datetime, Query()],
    group_by: Annotated[str, Query()] = "product",
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str, Query()] = "asc",
) -> Response:
    """WMS-531 R12. Заменяет прежнюю ручку `/inventory/export.csv`: у CSV и Excel
    было разное содержимое, и оставлять оба формата значило держать два
    источника цифр (D6). Кабинет селлера (`seller_scope`) получает файл без
    колонки и уровня «Селлер» — как и раньше для CSV."""
    await assert_inventory_read_access(session, user)
    effective_seller_id = seller_scope if seller_scope is not None else seller_id
    try:
        content = await build_inventory_workbook(
            session, user.tenant_id, date_from=date_from, date_to=date_to,
            group_by=group_by, seller_id=effective_seller_id,
            warehouse_id=warehouse_id, search=search,
            include_seller=seller_scope is None,
            sort_by=sort_by, sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)) from exc
    normalized_from, normalized_to = normalize_period(date_from, date_to)
    filename = inventory_workbook_filename(normalized_from, normalized_to)
    return Response(
        content=content, media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )
