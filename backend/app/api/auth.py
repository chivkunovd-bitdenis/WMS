from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin
from app.db.session import get_db
from app.models.seller import Seller
from app.models.user import User
from app.services.auth_service import (
    AuthError,
    create_seller_user,
    login,
    register_fulfillment,
)
from app.services.tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMeResponse(BaseModel):
    id: str
    email: str
    tenant_id: str
    role: str
    organization_name: str
    seller_id: str | None = None
    seller_name: str | None = None


class SellerAccountCreate(BaseModel):
    seller_id: uuid.UUID
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SellerAccountOut(BaseModel):
    id: str
    email: str
    role: str
    seller_id: str


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        user, _tenant = await register_fulfillment(
            session,
            organization_name=body.organization_name,
            slug=body.slug,
            admin_email=str(body.admin_email),
            password=body.password,
        )
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="slug_or_email_taken",
        ) from None

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return TokenResponse(access_token=token)


@router.post("/seller-accounts", response_model=SellerAccountOut, status_code=201)
async def create_seller_account(
    body: SellerAccountCreate,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerAccountOut:
    try:
        user = await create_seller_user(
            session,
            acting_user=admin,
            seller_id=body.seller_id,
            email=str(body.email),
            password=body.password,
        )
    except AuthError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "seller_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            ) from None
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
    assert user.seller_id is not None
    return SellerAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        seller_id=str(user.seller_id),
    )


@router.post("/login", response_model=TokenResponse)
async def login_route(
    body: LoginBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        _user, token = await login(
            session, email=str(body.email), password=body.password
        )
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        ) from None
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMeResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserMeResponse:
    from sqlalchemy import select

    from app.models.tenant import Tenant

    stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    res = await session.execute(stmt)
    tenant = res.scalar_one()
    seller_name: str | None = None
    seller_id_str: str | None = None
    if user.seller_id is not None:
        seller_id_str = str(user.seller_id)
        seller = await session.get(Seller, user.seller_id)
        if seller is not None:
            seller_name = seller.name
    return UserMeResponse(
        id=str(user.id),
        email=user.email,
        tenant_id=str(user.tenant_id),
        role=user.role,
        organization_name=tenant.name,
        seller_id=seller_id_str,
        seller_name=seller_name,
    )
