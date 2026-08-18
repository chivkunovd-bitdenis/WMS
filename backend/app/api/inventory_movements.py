from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_inventory_read_access,
    get_current_user,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services import inventory_service as inv_svc
from app.services.inventory_movement_report_service import (
    REPORT_GROUP_LABELS,
    REPORT_GROUP_ORDER,
    list_product_movement_summary,
)

router = APIRouter(
    prefix="/operations/inventory-movements",
    tags=["operations"],
)


class InventoryMovementRowOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    storage_location_id: str
    quantity_delta: int
    movement_type: str
    created_at: str


@router.get("", response_model=list[InventoryMovementRowOut])
async def list_inventory_movements(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[InventoryMovementRowOut]:
    rows = await inv_svc.list_recent_movements(
        session,
        user.tenant_id,
        limit=limit,
        seller_product_owner_id=seller_scope,
    )
    return [
        InventoryMovementRowOut(
            id=str(m.id),
            product_id=str(m.product_id),
            sku_code=p.sku_code,
            storage_location_id=str(m.storage_location_id),
            quantity_delta=m.quantity_delta,
            movement_type=m.movement_type,
            created_at=m.created_at.isoformat(),
        )
        for m, p in rows
    ]


class MovementGroupOut(BaseModel):
    key: str
    label: str
    in_qty: int
    out_qty: int


class ProductMovementSummaryRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    wb_vendor_code: str | None = None
    wb_barcode: str | None = None
    photo_url: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    groups: list[MovementGroupOut]
    total_in: int
    total_out: int
    net: int


@router.get("/summary", response_model=list[ProductMovementSummaryRowOut])
async def get_inventory_movements_summary(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    date_from: Annotated[datetime, Query()],
    date_to: Annotated[datetime, Query()],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> list[ProductMovementSummaryRowOut]:
    """Read-only отчёт «приход/расход по товару» за период (раздел «Отчёты» ФФ).

    Ничего не пересчитывает: суммирует уже записанные InventoryMovement, сгруппированные
    по товару и по человеко-понятной категории движения. См. inventory_movement_report_service.
    """
    await assert_inventory_read_access(session, user)
    if date_to <= date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_to must be after date_from",
        )
    effective_seller = seller_scope
    if seller_id is not None:
        if user.role != FULFILLMENT_ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        effective_seller = seller_id

    rows = await list_product_movement_summary(
        session,
        user.tenant_id,
        date_from=date_from,
        date_to=date_to,
        seller_id=effective_seller,
        warehouse_id=warehouse_id,
        search=search,
    )
    return [
        ProductMovementSummaryRowOut(
            product_id=str(r.product_id),
            sku_code=r.sku_code,
            product_name=r.product_name,
            wb_vendor_code=r.wb_vendor_code,
            wb_barcode=r.wb_barcode,
            photo_url=r.photo_url,
            seller_id=str(r.seller_id) if r.seller_id else None,
            seller_name=r.seller_name,
            groups=[
                MovementGroupOut(
                    key=key,
                    label=REPORT_GROUP_LABELS[key],
                    in_qty=r.groups.get(key, (0, 0))[0],
                    out_qty=r.groups.get(key, (0, 0))[1],
                )
                for key in REPORT_GROUP_ORDER
                if key in r.groups
            ],
            total_in=r.total_in,
            total_out=r.total_out,
            net=r.net,
        )
        for r in rows
    ]
