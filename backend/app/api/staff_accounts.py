from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
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
    packaging_rate_rub: str
    packaging_billing: StaffPackagingBillingOut


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


@router.get("", response_model=list[StaffAccountOut])
async def get_staff_accounts(
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    billing_month: Annotated[str | None, Query()] = None,
) -> list[StaffAccountOut]:
    month = billing_month or current_billing_month_msk()
    rows = await list_staff_users(session, tenant_id=admin.tenant_id)
    staff_ids = [user.id for user, _ in rows]
    totals = await aggregate_staff_billing(
        session,
        tenant_id=admin.tenant_id,
        staff_user_ids=staff_ids,
        billing_month=month,
    )
    return [
        StaffAccountOut(
            id=str(user.id),
            email=user.email,
            role=user.role,
            must_set_password=user.must_set_password,
            permissions=_permissions_out(perms),
            packaging_rate_rub=kopecks_to_rub_str(int(user.packaging_rate_kopecks)),
            packaging_billing=StaffPackagingBillingOut(
                billing_month=month,
                units_packed=totals[user.id].units_packed,
                earned_rub=kopecks_to_rub_str(totals[user.id].earned_kopecks),
            ),
        )
        for user, perms in rows
    ]


@router.post("", response_model=StaffAccountOut, status_code=201)
async def post_staff_account(
    body: StaffAccountCreate,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StaffAccountOut:
    try:
        user = await create_staff_user(
            session,
            acting_user=admin,
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
    rows = await list_staff_users(session, tenant_id=admin.tenant_id)
    perms = StaffPermissionsSnapshot()
    for u, p in rows:
        if u.id == user.id:
            perms = p
            break
    month = current_billing_month_msk()
    billing = await aggregate_staff_billing(
        session,
        tenant_id=admin.tenant_id,
        staff_user_ids=[user.id],
        billing_month=month,
    )
    return StaffAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        must_set_password=user.must_set_password,
        permissions=_permissions_out(perms),
        packaging_rate_rub=kopecks_to_rub_str(int(user.packaging_rate_kopecks)),
        packaging_billing=StaffPackagingBillingOut(
            billing_month=month,
            units_packed=billing[user.id].units_packed,
            earned_rub=kopecks_to_rub_str(billing[user.id].earned_kopecks),
        ),
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
    rows = await list_staff_users(session, tenant_id=admin.tenant_id)
    perms = StaffPermissionsSnapshot()
    for u, p in rows:
        if u.id == user.id:
            perms = p
            break
    billing = await aggregate_staff_billing(
        session,
        tenant_id=admin.tenant_id,
        staff_user_ids=[user.id],
        billing_month=month,
    )
    return StaffAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        must_set_password=user.must_set_password,
        permissions=_permissions_out(perms),
        packaging_rate_rub=kopecks_to_rub_str(int(user.packaging_rate_kopecks)),
        packaging_billing=StaffPackagingBillingOut(
            billing_month=month,
            units_packed=billing[user.id].units_packed,
            earned_rub=kopecks_to_rub_str(billing[user.id].earned_kopecks),
        ),
    )


@router.patch("/{user_id}/permissions", response_model=StaffAccountOut)
async def patch_staff_permissions(
    user_id: uuid.UUID,
    body: StaffPermissionsBody,
    admin: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StaffAccountOut:
    try:
        user, perms = await update_staff_permissions(
            session,
            acting_user=admin,
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
        if code == "not_staff_user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="not_staff_user",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from None
    month = current_billing_month_msk()
    billing = await aggregate_staff_billing(
        session,
        tenant_id=admin.tenant_id,
        staff_user_ids=[user.id],
        billing_month=month,
    )
    return StaffAccountOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        must_set_password=user.must_set_password,
        permissions=_permissions_out(perms),
        packaging_rate_rub=kopecks_to_rub_str(int(user.packaging_rate_kopecks)),
        packaging_billing=StaffPackagingBillingOut(
            billing_month=month,
            units_packed=billing[user.id].units_packed,
            earned_rub=kopecks_to_rub_str(billing[user.id].earned_kopecks),
        ),
    )
