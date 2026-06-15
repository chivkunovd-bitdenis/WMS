from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin, seller_line_product_scope
from app.db.session import get_db
from app.models.seller import Seller
from app.models.user import User
from app.services.auth_service import AuthError, create_seller_with_account
from app.services.catalog_service import create_seller, list_sellers
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows

router = APIRouter(prefix="/sellers", tags=["sellers"])


class SellerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SellerWithAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str | None = Field(default=None, max_length=128)

    @field_validator("password")
    @classmethod
    def normalize_optional_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if len(s) < 8:
            raise ValueError("password must be at least 8 characters")
        return s


class SellerOut(BaseModel):
    id: str
    name: str


class SellerWithAccountOut(BaseModel):
    seller_id: str
    seller_name: str
    user_id: str
    email: str
    role: str


class SellerWbCatalogAdminOut(BaseModel):
    """WB catalog row for FF admin (same shape as seller inbound picker)."""

    id: str
    name: str
    sku_code: str
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    wb_subject_name: str | None = None
    wb_primary_image_url: str | None = None
    wb_barcodes: list[str]
    wb_primary_barcode: str | None = None


@router.get("", response_model=list[SellerOut])
async def get_sellers(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[SellerOut]:
    rows = await list_sellers(session, user.tenant_id, seller_id=seller_scope)
    return [SellerOut(id=str(s.id), name=s.name) for s in rows]


@router.get(
    "/{seller_id}/wb-catalog",
    response_model=list[SellerWbCatalogAdminOut],
)
async def get_seller_wb_catalog_for_admin(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SellerWbCatalogAdminOut]:
    sl = await session.get(Seller, seller_id)
    if sl is None or sl.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="seller_not_found")
    rows = await list_seller_wb_catalog_rows(session, user.tenant_id, seller_id)
    return [SellerWbCatalogAdminOut(**r.as_dict()) for r in rows]


@router.post("", response_model=SellerOut, status_code=201)
async def post_seller(
    body: SellerCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerOut:
    s = await create_seller(session, user.tenant_id, name=body.name)
    return SellerOut(id=str(s.id), name=s.name)


@router.post("/with-account", response_model=SellerWithAccountOut, status_code=201)
async def post_seller_with_account(
    body: SellerWithAccountCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerWithAccountOut:
    try:
        seller, account = await create_seller_with_account(
            session,
            acting_user=user,
            name=body.name,
            email=str(body.email),
            password=body.password,
        )
    except AuthError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "email_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email_taken",
            ) from None
        if code == "forbidden":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden",
            ) from None
        raise
    return SellerWithAccountOut(
        seller_id=str(seller.id),
        seller_name=seller.name,
        user_id=str(account.id),
        email=account.email,
        role=account.role,
    )
