from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import (
    assert_inventory_read_access,
    get_current_user,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services.reporting_service import (
    build_inventory_csv,
    build_inventory_report,
    build_overview,
)

router = APIRouter(prefix="/reports", tags=["reports"])


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
