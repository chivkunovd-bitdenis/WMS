from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.seller_staff_permissions_service import (
    SellerPermissionsSnapshot,
    can_manage_seller_staff,
    create_seller_staff_user,
    list_seller_staff_users,
    update_seller_staff_permissions,
)

router = APIRouter(prefix="/auth/seller-staff-accounts", tags=["auth"])


class SellerPermissionsBody(BaseModel):
    documents: bool = True
    products: bool = True
    honest_sign: bool = True
    settings: bool = False
    staff: bool = False

    def to_snapshot(self) -> SellerPermissionsSnapshot:
        return SellerPermissionsSnapshot(
            documents=self.documents,
            products=self.products,
            honest_sign=self.honest_sign,
            settings=self.settings,
            staff=self.staff,
        )


class SellerStaffAccountCreate(BaseModel):
    email: EmailStr
    password: str | None = Field(default=None, max_length=128)
    permissions: SellerPermissionsBody = Field(default_factory=SellerPermissionsBody)

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


class SellerPermissionsOut(BaseModel):
    documents: bool
    products: bool
    honest_sign: bool
    settings: bool
    staff: bool


class SellerStaffAccountOut(BaseModel):
    id: str
    email: str
    role: str
    seller_id: str
    must_set_password: bool
    is_owner: bool
    permissions: SellerPermissionsOut


def _permissions_out(snapshot: SellerPermissionsSnapshot) -> SellerPermissionsOut:
    d = snapshot.as_dict()
    return SellerPermissionsOut(
        documents=d["documents"],
        products=d["products"],
        honest_sign=d["honest_sign"],
        settings=d["settings"],
        staff=d["staff"],
    )


def _account_out(
    user: User,
    perms: SellerPermissionsSnapshot,
    *,
    is_owner: bool,
) -> SellerStaffAccountOut:
    if user.seller_id is None:
        raise RuntimeError("seller staff account without seller_id")
    return SellerStaffAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        seller_id=str(user.seller_id),
        must_set_password=user.must_set_password,
        is_owner=is_owner,
        permissions=_permissions_out(perms),
    )


@router.get("", response_model=list[SellerStaffAccountOut])
async def get_seller_staff_accounts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SellerStaffAccountOut]:
    if user.seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
    if not await can_manage_seller_staff(session, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    rows = await list_seller_staff_users(
        session,
        tenant_id=user.tenant_id,
        seller_id=user.seller_id,
    )
    return [_account_out(u, p, is_owner=is_owner) for u, p, is_owner in rows]


@router.post("", response_model=SellerStaffAccountOut, status_code=201)
async def post_seller_staff_account(
    body: SellerStaffAccountCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerStaffAccountOut:
    try:
        created, perms = await create_seller_staff_user(
            session,
            acting_user=user,
            email=str(body.email),
            password=body.password,
            permissions=body.permissions.to_snapshot(),
        )
    except PermissionError as exc:
        code = exc.args[0] if exc.args else ""
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=code or "forbidden",
        ) from None
    except ValueError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "email_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email_taken",
            ) from None
        raise
    return _account_out(created, perms, is_owner=False)


@router.patch("/{user_id}/permissions", response_model=SellerStaffAccountOut)
async def patch_seller_staff_permissions(
    user_id: uuid.UUID,
    body: SellerPermissionsBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerStaffAccountOut:
    try:
        updated, perms = await update_seller_staff_permissions(
            session,
            acting_user=user,
            staff_user_id=user_id,
            permissions=body.to_snapshot(),
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_found",
        ) from None
    except PermissionError as exc:
        code = exc.args[0] if exc.args else ""
        if code in {"owner_protected", "self_update_forbidden", "not_seller_user"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=code,
            ) from None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=code or "forbidden",
        ) from None
    return _account_out(updated, perms, is_owner=False)
