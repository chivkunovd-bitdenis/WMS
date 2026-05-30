from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, seller_line_product_scope
from app.db.session import get_db
from app.models.user import User
from app.services import inventory_service
from app.services.sorting_location_service import SORTING_LOCATION_CODE

router = APIRouter(
    prefix="/operations/inventory-balances",
    tags=["operations"],
)


class InventoryBalanceRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    quantity_unpacked: int
    quantity_packed: int
    quantity_in_sorting: int
    quantity_in_storage: int
    reserved: int
    available: int


class ProductLocationHintOut(BaseModel):
    storage_location_id: str
    storage_location_code: str
    quantity: int
    reserved: int
    available: int


@router.get("/summary", response_model=list[InventoryBalanceRowOut])
async def get_inventory_balances_summary(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[InventoryBalanceRowOut]:
    rows = await inventory_service.list_balances_total(
        session,
        user.tenant_id,
        seller_product_owner_id=seller_scope,
        warehouse_id=warehouse_id,
    )
    return [
        InventoryBalanceRowOut(
            product_id=str(pid),
            sku_code=sku_code,
            product_name=product_name,
            quantity=qty,
            quantity_unpacked=unp,
            quantity_packed=pck,
            quantity_in_sorting=sort_qty,
            quantity_in_storage=max(0, qty - sort_qty),
            reserved=rsv,
            available=max(0, qty - sort_qty - rsv),
        )
        for pid, sku_code, product_name, qty, sort_qty, unp, pck, rsv in rows
    ]


@router.get("/locations-by-product", response_model=list[ProductLocationHintOut])
async def get_product_locations_in_warehouse(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    product_id: Annotated[uuid.UUID, Query()],
    warehouse_id: Annotated[uuid.UUID, Query()],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[ProductLocationHintOut]:
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
