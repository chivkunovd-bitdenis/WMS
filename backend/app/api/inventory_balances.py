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

router = APIRouter(
    prefix="/operations/inventory-balances",
    tags=["operations"],
)


class InventoryBalanceRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    quantity: int


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
    return [
        InventoryBalanceRowOut(
            product_id=str(b.product_id),
            sku_code=p.sku_code,
            product_name=p.name,
            quantity=b.quantity,
        )
        for b, p in rows
    ]
