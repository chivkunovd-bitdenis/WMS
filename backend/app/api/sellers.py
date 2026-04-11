from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin, seller_line_product_scope
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import create_seller, list_sellers

router = APIRouter(prefix="/sellers", tags=["sellers"])


class SellerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SellerOut(BaseModel):
    id: str
    name: str


@router.get("", response_model=list[SellerOut])
async def get_sellers(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[SellerOut]:
    rows = await list_sellers(session, user.tenant_id, seller_id=seller_scope)
    return [SellerOut(id=str(s.id), name=s.name) for s in rows]


@router.post("", response_model=SellerOut, status_code=201)
async def post_seller(
    body: SellerCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerOut:
    s = await create_seller(session, user.tenant_id, name=body.name)
    return SellerOut(id=str(s.id), name=s.name)
