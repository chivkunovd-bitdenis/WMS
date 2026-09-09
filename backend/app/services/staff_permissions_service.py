from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_STAFF
from app.models.document_event import (
    DOCUMENT_TYPE_STAFF_USER,
    EVENT_PERMISSIONS_CHANGED,
)
from app.models.ff_staff_permissions import FfStaffPermissions
from app.models.user import User
from app.services.document_event_service import (
    current_document_event_actor,
    record_document_event_safely,
)

PERM_SETTINGS = "settings"
PERM_MP_SHIPMENTS = "mp_shipments"
PERM_RECEPTION = "reception"
PERM_CELLS = "cells"
PERM_INVENTORY = "inventory"
PERM_PACKAGING = "packaging"
PERM_SHIFT_LEAD = "shift_lead"

ALL_PERMISSIONS = (
    PERM_SETTINGS,
    PERM_MP_SHIPMENTS,
    PERM_RECEPTION,
    PERM_CELLS,
    PERM_INVENTORY,
    PERM_PACKAGING,
    PERM_SHIFT_LEAD,
)


@dataclass(frozen=True)
class StaffPermissionsSnapshot:
    settings: bool = False
    mp_shipments: bool = False
    reception: bool = False
    cells: bool = False
    inventory: bool = False
    packaging: bool = False
    shift_lead: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            PERM_SETTINGS: self.settings,
            PERM_MP_SHIPMENTS: self.mp_shipments,
            PERM_RECEPTION: self.reception,
            PERM_CELLS: self.cells,
            PERM_INVENTORY: self.inventory,
            PERM_PACKAGING: self.packaging,
            PERM_SHIFT_LEAD: self.shift_lead,
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
    shift_lead=True,
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
        shift_lead=row.can_shift_lead,
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


async def can_manage_ff_staff(session: AsyncSession, user: User) -> bool:
    if user.role == FULFILLMENT_ADMIN:
        return True
    if user.role != FULFILLMENT_STAFF:
        return False
    return (await get_staff_permissions(session, user)).settings


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
    if not await can_manage_ff_staff(session, acting_user):
        raise PermissionError("forbidden")
    if acting_user.id == staff_user_id:
        raise PermissionError("self_update_forbidden")
    user = await session.scalar(
        select(User)
        .where(User.id == staff_user_id, User.tenant_id == acting_user.tenant_id)
        .options(selectinload(User.ff_staff_permissions))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or user.tenant_id != acting_user.tenant_id:
        raise LookupError("user_not_found")
    if user.role != FULFILLMENT_STAFF:
        raise PermissionError("not_staff_user")
    row = user.ff_staff_permissions
    before = _from_row(row).as_dict()
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
    row.can_shift_lead = permissions.shift_lead
    after = permissions.as_dict()
    # WMS-325: append-only факт смены прав в существующем document_event; acting_user
    # — тот, кто нажал кнопку, target — тот, кому меняют права. Пишем ДО commit,
    # чтобы событие и права уехали в одну транзакцию. Новую таблицу не заводим.
    if before != after:
        actor = current_document_event_actor()
        await record_document_event_safely(
            session,
            tenant_id=user.tenant_id,
            document_type=DOCUMENT_TYPE_STAFF_USER,
            document_id=user.id,
            event_type=EVENT_PERMISSIONS_CHANGED,
            source=actor.source,
            actor_user_id=acting_user.id,
            payload_json={
                "role": "fulfillment_staff",
                "target_user_id": str(user.id),
                "acting_user_id": str(acting_user.id),
                "before": before,
                "after": after,
            },
        )
    await session.commit()
    await session.refresh(user)
    await session.refresh(row)
    return user, _from_row(row)
