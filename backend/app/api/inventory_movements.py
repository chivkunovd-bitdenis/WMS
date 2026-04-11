from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, seller_line_product_scope
from app.db.session import get_db
from app.models.user import User
from app.services import inventory_service as inv_svc

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
