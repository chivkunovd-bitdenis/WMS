from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, public_base_url
from app.db.session import get_db
from app.models.user import User
from app.schemas.user_profile import ProfilePatch
from app.services.auth_service import send_auth_link
from app.services.seller_staff_permissions_service import (
    SellerPermissionsSnapshot,
    can_manage_seller_staff,
    create_seller_staff_user,
    list_seller_staff_users,
    prepare_seller_staff_invite,
    update_seller_staff_permissions,
    update_seller_staff_profile,
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


class SellerStaffAccountCreate(ProfilePatch):
    email: EmailStr
    permissions: SellerPermissionsBody = Field(default_factory=SellerPermissionsBody)


class SellerStaffProfilePatch(ProfilePatch):
    email: EmailStr | None = None


class SellerPermissionsOut(BaseModel):
    documents: bool
    products: bool
    honest_sign: bool
    settings: bool
    staff: bool


class SellerStaffAccountOut(BaseModel):
    id: str
    email: str | None
    full_name: str | None = None
    job_title: str | None = None
    display_name: str = "ФИО не указано"
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
        full_name=user.full_name,
        job_title=user.job_title,
        display_name=user.display_name,
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
    request: Request,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerStaffAccountOut:
    try:
        created, perms = await create_seller_staff_user(
            session,
            acting_user=user,
            email=str(body.email),
            full_name=body.full_name,
            job_title=body.job_title,
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
    background_tasks.add_task(
        send_auth_link, created, purpose="invite", base_url=public_base_url(request),
    )
    return _account_out(created, perms, is_owner=False)


@router.post("/{user_id}/invite", status_code=204)
async def resend_seller_staff_invite(
    user_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        staff_user = await prepare_seller_staff_invite(
            session, acting_user=actor, staff_user_id=user_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="user_not_found") from None
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    background_tasks.add_task(
        send_auth_link, staff_user, purpose="invite", base_url=public_base_url(request),
    )
    return Response(status_code=204)


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


@router.patch("/{user_id}/profile", response_model=SellerStaffAccountOut)
async def patch_seller_staff_profile(
    user_id: uuid.UUID,
    body: SellerStaffProfilePatch,
    request: Request,
    background_tasks: BackgroundTasks,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> SellerStaffAccountOut:
    try:
        staff_user, perms, is_owner, invite = await update_seller_staff_profile(
            session, acting_user=actor, staff_user_id=user_id,
            full_name=body.full_name, job_title=body.job_title,
            email=str(body.email) if body.email is not None else None,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="user_not_found") from None
    except PermissionError:
        raise HTTPException(status_code=403, detail="forbidden") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if invite:
        background_tasks.add_task(
            send_auth_link, staff_user, purpose="invite", base_url=public_base_url(request),
        )
    return _account_out(staff_user, perms, is_owner=is_owner)
