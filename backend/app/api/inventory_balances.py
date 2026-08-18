from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_inventory_read_access,
    get_current_user,
    require_ff_permission,
    require_fulfillment_admin,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services import inventory_service, stock_direction_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE
from app.services.staff_permissions_service import PERM_INVENTORY

router = APIRouter(
    prefix="/operations/inventory-balances",
    tags=["operations"],
)
require_ff_inventory_access = require_ff_permission(PERM_INVENTORY)


class InventoryBalanceRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    seller_id: str | None = None
    seller_name: str | None = None
    packaging_instructions: str | None = None
    requires_honest_sign: bool = False
    quantity: int
    quantity_unpacked: int
    quantity_packed: int
    quantity_in_sorting: int
    quantity_in_storage: int
    reserved: int
    available: int
    quantity_fbs: int = 0
    quantity_reserved_directions: int = 0
    quantity_free_fbo: int = 0


class StockMonthlySnapshotOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    sku_code: str
    barcode: str | None = None
    snapshot_month: date
    quantity_total: int
    quantity_fbs: int
    quantity_reserved: int
    quantity_free_fbo: int


class StockMonthlySnapshotRunIn(BaseModel):
    month: date


class ProductLocationHintOut(BaseModel):
    storage_location_id: str
    storage_location_code: str
    quantity: int
    reserved: int
    available: int


def _snapshot_out(row: object) -> StockMonthlySnapshotOut:
    from app.models.stock_direction import StockMonthlySnapshot

    assert isinstance(row, StockMonthlySnapshot)
    return StockMonthlySnapshotOut(
        id=str(row.id),
        product_id=str(row.product_id),
        product_name=row.product.name,
        sku_code=row.product.sku_code,
        barcode=row.product.wb_barcode,
        snapshot_month=row.snapshot_month,
        quantity_total=int(row.quantity_total),
        quantity_fbs=int(row.quantity_fbs),
        quantity_reserved=int(row.quantity_reserved),
        quantity_free_fbo=int(row.quantity_free_fbo),
    )


@router.get("/summary", response_model=list[InventoryBalanceRowOut])
async def get_inventory_balances_summary(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[InventoryBalanceRowOut]:
    await assert_inventory_read_access(session, user)
    effective_seller = seller_scope
    if seller_id is not None:
        if user.role != FULFILLMENT_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden",
            )
        effective_seller = seller_id
    rows = await inventory_service.list_balances_total(
        session,
        user.tenant_id,
        seller_product_owner_id=effective_seller,
        warehouse_id=warehouse_id,
    )
    product_ids = [pid for pid, *_ in rows]
    distribution_map = await stock_direction_service.distributions_by_product(
        session,
        user.tenant_id,
        product_ids,
        warehouse_id=warehouse_id,
    )
    fbs_reserved_map = await stock_direction_service.fbs_reserved_totals_by_product(
        session,
        user.tenant_id,
        product_ids,
        warehouse_id=warehouse_id,
    )
    return [
        (
            lambda fbo_reserved, dist: InventoryBalanceRowOut(
                product_id=str(pid),
                sku_code=sku_code,
                product_name=product_name,
                seller_id=None,
                seller_name=None,
                packaging_instructions=None,
                requires_honest_sign=False,
                quantity=qty,
                quantity_unpacked=unp,
                quantity_packed=pck,
                quantity_in_sorting=sort_qty,
                quantity_in_storage=max(0, qty - sort_qty),
                reserved=rsv,
                available=(
                    max(0, dist.quantity_free_fbo - fbo_reserved)
                    if dist.quantity_fbs > 0 or dist.quantity_reserved > 0
                    else max(0, qty - sort_qty - rsv)
                ),
                quantity_fbs=dist.quantity_fbs,
                quantity_reserved_directions=dist.quantity_reserved,
                quantity_free_fbo=dist.quantity_free_fbo,
            )
        )(
            max(0, rsv - int(fbs_reserved_map.get(pid, 0))),
            distribution_map.get(
                pid,
                stock_direction_service.StockDistribution(
                    product_id=pid,
                    quantity_total=qty,
                    quantity_fbs=0,
                    quantity_reserved=0,
                    quantity_free_fbo=qty,
                ),
            ),
        )
        for pid, sku_code, product_name, qty, sort_qty, unp, pck, rsv in rows
    ]


@router.get("/monthly-snapshots", response_model=list[StockMonthlySnapshotOut])
async def get_monthly_stock_snapshots(
    user: Annotated[User, Depends(require_ff_inventory_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    month: Annotated[date, Query()],
) -> list[StockMonthlySnapshotOut]:
    rows = await stock_direction_service.list_monthly_snapshots(
        session,
        user.tenant_id,
        month,
    )
    return [_snapshot_out(row) for row in rows]


@router.post("/monthly-snapshots/run", response_model=list[StockMonthlySnapshotOut])
async def run_monthly_stock_snapshot(
    body: StockMonthlySnapshotRunIn,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[StockMonthlySnapshotOut]:
    try:
        rows = await stock_direction_service.take_monthly_snapshot(
            session,
            user.tenant_id,
            body.month,
        )
    except stock_direction_service.StockDirectionError as exc:
        if exc.code in {"monthly_snapshot_empty", "monthly_snapshot_historical_empty"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from exc
        raise
    return [_snapshot_out(row) for row in rows]


@router.get("/locations-by-product", response_model=list[ProductLocationHintOut])
async def get_product_locations_in_warehouse(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    product_id: Annotated[uuid.UUID, Query()],
    warehouse_id: Annotated[uuid.UUID, Query()],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[ProductLocationHintOut]:
    await assert_inventory_read_access(session, user)
    if seller_scope is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    rows = await inventory_service.list_locations_for_product_in_warehouse(
        session,
        user.tenant_id,
        warehouse_id,
        product_id,
    )
    return [
        ProductLocationHintOut(
            storage_location_id=str(loc_id),
            storage_location_code=code,
            quantity=on_hand,
            reserved=rsv,
            available=on_hand - rsv,
        )
        for loc_id, code, on_hand, rsv in rows
    ]


@router.get("", response_model=list[InventoryBalanceRowOut])
async def get_inventory_balances(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    storage_location_id: Annotated[uuid.UUID, Query()],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[InventoryBalanceRowOut]:
    await assert_inventory_read_access(session, user)
    rows = await inventory_service.list_balances_at_location(
        session,
        user.tenant_id,
        storage_location_id,
        seller_product_owner_id=seller_scope,
    )
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="location_not_found",
        )
    from app.models.storage_location import StorageLocation

    loc = await session.get(StorageLocation, storage_location_id)
    is_sorting = loc is not None and loc.code == SORTING_LOCATION_CODE
    return [
        InventoryBalanceRowOut(
            product_id=str(b.product_id),
            sku_code=p.sku_code,
            product_name=p.name,
            seller_id=str(p.seller_id) if p.seller_id else None,
            seller_name=p.seller.name if p.seller else None,
            packaging_instructions=p.packaging_instructions,
            requires_honest_sign=bool(p.requires_honest_sign),
            quantity=b.quantity,
            quantity_unpacked=int(b.quantity_unpacked),
            quantity_packed=int(b.quantity_packed),
            quantity_in_sorting=b.quantity if is_sorting else 0,
            quantity_in_storage=0 if is_sorting else b.quantity,
            reserved=rsv,
            available=0 if is_sorting else b.quantity - rsv,
        )
        for b, p, rsv in rows
    ]
