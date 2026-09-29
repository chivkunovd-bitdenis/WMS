from __future__ import annotations

import urllib.parse
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response, StreamingResponse

from app.api.deps import (
    assert_inventory_read_access,
    get_current_user,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services.client_movement_report_service import (
    build_client_movement_workbook,
    list_client_movements,
)
from app.services.reporting_service import (
    MOVEMENT_PAGE_LIMIT,
    build_inventory_csv,
    build_inventory_report,
    build_overview,
    list_product_movements,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/client-movements")
async def get_client_movements(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    sku: Annotated[str | None, Query()] = None,
    barcode: Annotated[str | None, Query()] = None,
    marketplace: Annotated[str | None, Query()] = None,
    operation: Annotated[str | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, object]:
    await assert_inventory_read_access(session, user)
    try:
        rows, next_cursor = await list_client_movements(
            session,
            user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            sku=sku,
            barcode=barcode,
            marketplace=marketplace,
            operation=operation,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"rows": rows, "next_cursor": next_cursor, "limit": limit}


@router.get("/client-movements/export.xlsx")
async def export_client_movements(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    sku: Annotated[str | None, Query()] = None,
    barcode: Annotated[str | None, Query()] = None,
    marketplace: Annotated[str | None, Query()] = None,
    operation: Annotated[str | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    await assert_inventory_read_access(session, user)
    try:
        content = await build_client_movement_workbook(
            session,
            user.tenant_id,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            sku=sku,
            barcode=barcode,
            marketplace=marketplace,
            operation=operation,
            seller_id=seller_scope if seller_scope is not None else seller_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition("client-movements.xlsx")},
    )


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
) -> dict[str, object]:
    """Движения за период: когда приехало, когда уехало и по какому документу.

    Раскрыть можно товар (`product_id`) или вид движения (`operation`) — второй
    случай нужен группировке «по видам», где третьего уровня раньше не было.
    """
    await assert_inventory_read_access(session, user)
    try:
        rows, truncated = await list_product_movements(
            session,
            user.tenant_id,
            product_id=product_id,
            operation=operation,
            date_from=date_from,
            date_to=date_to,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            warehouse_id=warehouse_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return {"rows": rows, "truncated": truncated, "limit": MOVEMENT_PAGE_LIMIT}


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


@router.get("/inventory/export.csv")
async def export_inventory_report(
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
) -> StreamingResponse:
    await assert_inventory_read_access(session, user)
    try:
        content = await build_inventory_csv(
            session, user.tenant_id, date_from=date_from, date_to=date_to,
            group_by=group_by,
            seller_id=seller_scope if seller_scope is not None else seller_id,
            warehouse_id=warehouse_id,
            search=search, include_seller=seller_scope is None,
            sort_by=sort_by, sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)) from exc
    return StreamingResponse(
        content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=inventory-report.csv"},
    )
