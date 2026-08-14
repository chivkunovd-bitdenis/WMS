from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin
from app.core.roles import FULFILLMENT_ADMIN
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import AuthError, create_staff_user
from app.services.staff_packaging_billing_service import (
    aggregate_staff_billing,
    current_billing_month_msk,
    kopecks_to_rub_str,
    update_staff_packaging_rate,
)
from app.services.staff_permissions_service import (
    StaffPermissionsSnapshot,
    can_manage_ff_staff,
    list_staff_users,
    update_staff_permissions,
)

router = APIRouter(prefix="/auth/staff-accounts", tags=["auth"])


class StaffPermissionsBody(BaseModel):
    settings: bool = False
    mp_shipments: bool = False
    reception: bool = False
    cells: bool = False
    inventory: bool = False
    packaging: bool = False
    shift_lead: bool = False

    def to_snapshot(self) -> StaffPermissionsSnapshot:
        return StaffPermissionsSnapshot(
            settings=self.settings,
            mp_shipments=self.mp_shipments,
            reception=self.reception,
            cells=self.cells,
            inventory=self.inventory,
            packaging=self.packaging,
            shift_lead=self.shift_lead,
        )


class StaffAccountCreate(BaseModel):
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


class StaffPermissionsOut(BaseModel):
    settings: bool
    mp_shipments: bool
    reception: bool
    cells: bool
    inventory: bool
    packaging: bool
    shift_lead: bool


class StaffPackagingBillingOut(BaseModel):
    billing_month: str
    units_packed: int
    earned_rub: str


class StaffAccountOut(BaseModel):
    id: str
    email: str
    role: str
    must_set_password: bool
    permissions: StaffPermissionsOut
    packaging_rate_rub: str | None = None
    packaging_billing: StaffPackagingBillingOut | None = None


class StaffPackagingRatePatch(BaseModel):
    rate_rub: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


def _permissions_out(snapshot: StaffPermissionsSnapshot) -> StaffPermissionsOut:
    d = snapshot.as_dict()
    return StaffPermissionsOut(
        settings=d["settings"],
        mp_shipments=d["mp_shipments"],
        reception=d["reception"],
        cells=d["cells"],
        inventory=d["inventory"],
        packaging=d["packaging"],
        shift_lead=d["shift_lead"],
    )


def _staff_account_out(user: User, perms: StaffPermissionsSnapshot) -> StaffAccountOut:
    return StaffAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        must_set_password=user.must_set_password,
        permissions=_permissions_out(perms),
    )


async def _staff_permissions_for_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> StaffPermissionsSnapshot:
    rows = await list_staff_users(session, tenant_id=tenant_id)
    for row_user, perms in rows:
        if row_user.id == user_id:
            return perms
    return StaffPermissionsSnapshot()


async def _staff_account_out_for_actor(
    session: AsyncSession,
    *,
    actor: User,
    staff_user: User,
    perms: StaffPermissionsSnapshot,
    billing_month: str | None = None,
) -> StaffAccountOut:
    out = _staff_account_out(staff_user, perms)
    if actor.role != FULFILLMENT_ADMIN:
        return out

    month = billing_month or current_billing_month_msk()
    billing = await aggregate_staff_billing(
        session,
        tenant_id=actor.tenant_id,
        staff_user_ids=[staff_user.id],
        billing_month=month,
    )
    return out.model_copy(
        update={
            "packaging_rate_rub": kopecks_to_rub_str(int(staff_user.packaging_rate_kopecks)),
            "packaging_billing": StaffPackagingBillingOut(
                billing_month=month,
                units_packed=billing[staff_user.id].units_packed,
                earned_rub=kopecks_to_rub_str(billing[staff_user.id].earned_kopecks),
            ),
        }
    )


@router.get("", response_model=list[StaffAccountOut], response_model_exclude_none=True)
async def get_staff_accounts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    billing_month: Annotated[str | None, Query()] = None,
) -> list[StaffAccountOut]:
    if not await can_manage_ff_staff(session, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    rows = await list_staff_users(session, tenant_id=user.tenant_id)
    if user.role != FULFILLMENT_ADMIN:
        return [_staff_account_out(row_user, perms) for row_user, perms in rows]

    month = billing_month or current_billing_month_msk()
    staff_ids = [row_user.id for row_user, _ in rows]
    totals = await aggregate_staff_billing(
        session,
        tenant_id=user.tenant_id,
        staff_user_ids=staff_ids,
        billing_month=month,
    )
    return [
        StaffAccountOut(
            id=str(row_user.id),
            email=row_user.email,
            role=row_user.role,
            must_set_password=row_user.must_set_password,
            permissions=_permissions_out(perms),
            packaging_rate_rub=kopecks_to_rub_str(int(row_user.packaging_rate_kopecks)),
            packaging_billing=StaffPackagingBillingOut(
                billing_month=month,
                units_packed=totals[row_user.id].units_packed,
                earned_rub=kopecks_to_rub_str(totals[row_user.id].earned_kopecks),
            ),
        )
        for row_user, perms in rows
    ]


@router.post("", response_model=StaffAccountOut, status_code=201, response_model_exclude_none=True)
async def post_staff_account(
    body: StaffAccountCreate,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StaffAccountOut:
    if not await can_manage_ff_staff(session, actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    try:
        staff_user = await create_staff_user(
            session,
            acting_user=actor,
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
    perms = await _staff_permissions_for_user(
        session,
        tenant_id=actor.tenant_id,
        user_id=staff_user.id,
    )
    return await _staff_account_out_for_actor(
        session,
        actor=actor,
        staff_user=staff_user,
        perms=perms,
    )


@router.patch("/{user_id}/packaging-rate", response_model=StaffAccountOut)
async def patch_staff_packaging_rate(
    user_id: uuid.UUID,
    body: StaffPackagingRatePatch,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    billing_month: Annotated[str | None, Query()] = None,
) -> StaffAccountOut:
    month = billing_month or current_billing_month_msk()
    try:
        user = await update_staff_packaging_rate(
            session,
            acting_user=admin,
            staff_user_id=user_id,
            rate_rub=body.rate_rub,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user_not_found",
        ) from None
    except PermissionError as exc:
        code = exc.args[0] if exc.args else ""
        if code == "not_staff_user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="not_staff_user",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_rate",
        ) from None
    perms = await _staff_permissions_for_user(
        session,
        tenant_id=admin.tenant_id,
        user_id=user.id,
    )
    return await _staff_account_out_for_actor(
        session,
        actor=admin,
        staff_user=user,
        perms=perms,
        billing_month=month,
    )


@router.patch(
    "/{user_id}/permissions",
    response_model=StaffAccountOut,
    response_model_exclude_none=True,
)
async def patch_staff_permissions(
    user_id: uuid.UUID,
    body: StaffPermissionsBody,
    actor: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StaffAccountOut:
    if not await can_manage_ff_staff(session, actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    try:
        user, perms = await update_staff_permissions(
            session,
            acting_user=actor,
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
        if code == "self_update_forbidden":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="self_update_forbidden",
            ) from None
        if code == "not_staff_user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="not_staff_user",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from None
    return await _staff_account_out_for_actor(
        session,
        actor=actor,
        staff_user=user,
        perms=perms,
    )
