"""Seller-only, read-only FBS order list (WMS-616)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_seller_permission, get_current_user, get_effective_seller_id
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.seller_fbs_orders_service import (
    SellerFbsMarketplace,
    SellerFbsStatusGroup,
    list_seller_fbs_orders,
)
from app.services.seller_shop_service import user_can_manage_seller_shops
from app.services.seller_staff_permissions_service import PERM_DOCUMENTS

router = APIRouter(prefix="/seller-fbs", tags=["seller-fbs"])


async def _seller_fbs_scope(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> uuid.UUID:
    await assert_seller_permission(session, user, PERM_DOCUMENTS)
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
    # Delegated seller staff cannot widen scope with a forged seller_id claim.
    if not user_can_manage_seller_shops(user):
        if user.seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        return user.seller_id
    return effective_seller_id


class SellerFbsOrderOut(BaseModel):
    id: uuid.UUID
    marketplace: SellerFbsMarketplace
    external_order_id: str | None
    status_group: SellerFbsStatusGroup
    items_quantity: int | None
    received_at: datetime


class SellerFbsOrdersPageOut(BaseModel):
    items: list[SellerFbsOrderOut]
    total: int
    server_now: datetime


@router.get("/orders", response_model=SellerFbsOrdersPageOut)
async def get_seller_fbs_orders(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID, Depends(_seller_fbs_scope)],
    marketplace: Annotated[SellerFbsMarketplace | None, Query()] = None,
    status_group: Annotated[SellerFbsStatusGroup | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SellerFbsOrdersPageOut:
    items, total = await list_seller_fbs_orders(
        session,
        user.tenant_id,
        seller_id,
        marketplace=marketplace,
        status_group=status_group,
        limit=limit,
        offset=offset,
    )
    return SellerFbsOrdersPageOut(
        items=[SellerFbsOrderOut.model_validate(item, from_attributes=True) for item in items],
        total=total,
        server_now=datetime.now(tz=UTC),
    )
