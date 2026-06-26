from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    require_fulfillment_admin,
    resolve_effective_seller_id,
)
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.seller import Seller
from app.models.user import User
from app.services.auth_service import (
    AuthError,
    create_seller_user,
    login,
    register_fulfillment,
    set_initial_password,
)
from app.services.seller_shop_service import (
    SellerShopError,
    can_act_as_seller,
    list_delegatable_shops,
    list_switchable_shops,
    update_enabled_shops,
    user_can_manage_seller_shops,
)
from app.services.staff_permissions_service import get_staff_permissions
from app.services.tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


class RegisterBody(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    admin_email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(default="", max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StaffPermissionsOut(BaseModel):
    settings: bool
    mp_shipments: bool
    reception: bool
    cells: bool
    inventory: bool
    packaging: bool
    shift_lead: bool


class SellerShopOut(BaseModel):
    id: str
    name: str
    enabled: bool = False
    is_home: bool = False


class UserMeResponse(BaseModel):
    id: str
    email: str
    tenant_id: str
    role: str
    organization_name: str
    seller_id: str | None = None
    seller_name: str | None = None
    home_seller_id: str | None = None
    home_seller_name: str | None = None
    active_seller_id: str | None = None
    active_seller_name: str | None = None
    can_manage_seller_shops: bool = False
    switchable_shops: list[SellerShopOut] = Field(default_factory=list)
    delegatable_shops: list[SellerShopOut] = Field(default_factory=list)
    permissions: StaffPermissionsOut | None = None


class SwitchSellerBody(BaseModel):
    seller_id: uuid.UUID | None = None


class SellerShopsUpdateBody(BaseModel):
    enabled_seller_ids: list[uuid.UUID] = Field(default_factory=list)


class SellerAccountCreate(BaseModel):
    seller_id: uuid.UUID
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


class SetInitialPasswordBody(BaseModel):
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
    except AuthError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "password_setup_required":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="password_setup_required",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        ) from None
    return TokenResponse(access_token=token)


@router.post("/set-initial-password", response_model=TokenResponse)
async def set_initial_password_route(
    body: SetInitialPasswordBody,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        user = await set_initial_password(
            session,
            email=str(body.email),
            password=body.password,
        )
    except AuthError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "forbidden":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden",
            ) from None
        if code == "password_already_set":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="password_already_set",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        ) from None
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMeResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserMeResponse:
    from sqlalchemy import select

    from app.models.tenant import Tenant

    stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    res = await session.execute(stmt)
    tenant = res.scalar_one()
    home_seller_id_str: str | None = None
    home_seller_name: str | None = None
    if user.seller_id is not None:
        home_seller_id_str = str(user.seller_id)
        home = await session.get(Seller, user.seller_id)
        if home is not None:
            home_seller_name = home.name
    active_seller_id = await resolve_effective_seller_id(session, user, credentials)
    active_seller_id_str = str(active_seller_id) if active_seller_id else None
    active_seller_name: str | None = None
    if active_seller_id is not None:
        active = await session.get(Seller, active_seller_id)
        if active is not None:
            active_seller_name = active.name
    can_manage = user_can_manage_seller_shops(user)
    switchable = await list_switchable_shops(session, user)
    delegatable = await list_delegatable_shops(session, user)
    switchable_out = [
        SellerShopOut(
            id=str(s.id),
            name=s.name,
            enabled=True,
            is_home=s.id == user.seller_id,
        )
        for s in switchable
    ]
    delegatable_out = [
        SellerShopOut(
            id=str(s.id),
            name=s.name,
            enabled=enabled,
            is_home=False,
        )
        for s, enabled in delegatable
    ]
    perms_snapshot = await get_staff_permissions(session, user)
    perms_dict = perms_snapshot.as_dict()
    permissions = StaffPermissionsOut(
        settings=perms_dict["settings"],
        mp_shipments=perms_dict["mp_shipments"],
        reception=perms_dict["reception"],
        cells=perms_dict["cells"],
        inventory=perms_dict["inventory"],
        packaging=perms_dict["packaging"],
        shift_lead=perms_dict["shift_lead"],
    )
    return UserMeResponse(
        id=str(user.id),
        email=user.email,
        tenant_id=str(user.tenant_id),
        role=user.role,
        organization_name=tenant.name,
        seller_id=active_seller_id_str,
        seller_name=active_seller_name,
        home_seller_id=home_seller_id_str,
        home_seller_name=home_seller_name,
        active_seller_id=active_seller_id_str,
        active_seller_name=active_seller_name,
        can_manage_seller_shops=can_manage,
        switchable_shops=switchable_out,
        delegatable_shops=delegatable_out,
        permissions=permissions,
    )


@router.put("/seller-shops", response_model=list[SellerShopOut])
async def put_seller_shops(
    body: SellerShopsUpdateBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SellerShopOut]:
    if not user_can_manage_seller_shops(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        rows = await update_enabled_shops(session, user, body.enabled_seller_ids)
    except SellerShopError as exc:
        if exc.code == "seller_not_allowed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="seller_not_allowed",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from None
    return [
        SellerShopOut(id=str(s.id), name=s.name, enabled=enabled, is_home=False)
        for s, enabled in rows
    ]


@router.post("/switch-seller", response_model=TokenResponse)
async def switch_seller(
    body: SwitchSellerBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    target = body.seller_id if body.seller_id is not None else user.seller_id
    if not await can_act_as_seller(session, user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=target,
    )
    return TokenResponse(access_token=token)
