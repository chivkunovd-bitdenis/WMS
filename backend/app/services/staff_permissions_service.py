from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_STAFF
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.user import User

PERM_SETTINGS = "settings"
PERM_MP_SHIPMENTS = "mp_shipments"
PERM_RECEPTION = "reception"
PERM_CELLS = "cells"
PERM_INVENTORY = "inventory"
PERM_PACKAGING = "packaging"

ALL_PERMISSIONS = (
    PERM_SETTINGS,
    PERM_MP_SHIPMENTS,
    PERM_RECEPTION,
    PERM_CELLS,
    PERM_INVENTORY,
    PERM_PACKAGING,
)


@dataclass(frozen=True)
class StaffPermissionsSnapshot:
    settings: bool = False
    mp_shipments: bool = False
    reception: bool = False
    cells: bool = False
    inventory: bool = False
    packaging: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            PERM_SETTINGS: self.settings,
            PERM_MP_SHIPMENTS: self.mp_shipments,
            PERM_RECEPTION: self.reception,
            PERM_CELLS: self.cells,
            PERM_INVENTORY: self.inventory,
            PERM_PACKAGING: self.packaging,
        }

    def has(self, permission: str) -> bool:
        return self.as_dict().get(permission, False)


ADMIN_ALL = StaffPermissionsSnapshot(
    settings=True,
    mp_shipments=True,
    reception=True,
    cells=True,
    inventory=True,
    packaging=True,
)


def _from_row(row: FfStaffPermissions | None) -> StaffPermissionsSnapshot:
    if row is None:
        return StaffPermissionsSnapshot()
    return StaffPermissionsSnapshot(
        settings=row.can_settings,
        mp_shipments=row.can_mp_shipments,
        reception=row.can_reception,
        cells=row.can_cells,
        inventory=row.can_inventory,
        packaging=row.can_packaging,
    )


async def get_staff_permissions(
    session: AsyncSession,
    user: User,
) -> StaffPermissionsSnapshot:
    if user.role == FULFILLMENT_ADMIN:
        return ADMIN_ALL
    if user.role != FULFILLMENT_STAFF:
        return StaffPermissionsSnapshot()
    row = await session.get(FfStaffPermissions, user.id)
    return _from_row(row)


async def list_staff_users(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> list[tuple[User, StaffPermissionsSnapshot]]:
    stmt = (
        select(User)
        .where(User.tenant_id == tenant_id, User.role == FULFILLMENT_STAFF)
        .options(selectinload(User.ff_staff_permissions))
        .order_by(User.created_at.asc())
    )
    result = await session.execute(stmt)
    rows: list[tuple[User, StaffPermissionsSnapshot]] = []
    for user in result.scalars().all():
        rows.append((user, _from_row(user.ff_staff_permissions)))
    return rows


async def update_staff_permissions(
    session: AsyncSession,
    *,
    acting_user: User,
    staff_user_id: uuid.UUID,
    permissions: StaffPermissionsSnapshot,
) -> tuple[User, StaffPermissionsSnapshot]:
    if acting_user.role != FULFILLMENT_ADMIN:
        raise PermissionError("forbidden")
    user = await session.get(
        User,
        staff_user_id,
        options=(selectinload(User.ff_staff_permissions),),
    )
    if user is None or user.tenant_id != acting_user.tenant_id:
        raise LookupError("user_not_found")
    if user.role != FULFILLMENT_STAFF:
        raise PermissionError("not_staff_user")
    row = user.ff_staff_permissions
    if row is None:
        row = FfStaffPermissions(user_id=user.id)
        session.add(row)
        user.ff_staff_permissions = row
    row.can_settings = permissions.settings
    row.can_mp_shipments = permissions.mp_shipments
    row.can_reception = permissions.reception
    row.can_cells = permissions.cells
    row.can_inventory = permissions.inventory
    row.can_packaging = permissions.packaging
    await session.commit()
    await session.refresh(user)
    await session.refresh(row)
    return user, _from_row(row)
