from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.roles import FULFILLMENT_SELLER
from app.models.seller_staff_permissions import SellerStaffPermissions
from app.models.user import User
from app.services.passwords import hash_password

PERM_DOCUMENTS = "documents"
PERM_PRODUCTS = "products"
PERM_HONEST_SIGN = "honest_sign"
PERM_SETTINGS = "settings"
PERM_STAFF = "staff"

ALL_SELLER_PERMISSIONS = (
    PERM_DOCUMENTS,
    PERM_PRODUCTS,
    PERM_HONEST_SIGN,
    PERM_SETTINGS,
    PERM_STAFF,
)


@dataclass(frozen=True)
class SellerPermissionsSnapshot:
    documents: bool = False
    products: bool = False
    honest_sign: bool = False
    settings: bool = False
    staff: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            PERM_DOCUMENTS: self.documents,
            PERM_PRODUCTS: self.products,
            PERM_HONEST_SIGN: self.honest_sign,
            PERM_SETTINGS: self.settings,
            PERM_STAFF: self.staff,
        }

    def has(self, permission: str) -> bool:
        return self.as_dict().get(permission, False)


OWNER_ALL = SellerPermissionsSnapshot(
    documents=True,
    products=True,
    honest_sign=True,
    settings=True,
    staff=True,
)


def _from_row(row: SellerStaffPermissions | None) -> SellerPermissionsSnapshot:
    if row is None:
        return OWNER_ALL
    return SellerPermissionsSnapshot(
        documents=row.can_documents,
        products=row.can_products,
        honest_sign=row.can_honest_sign,
        settings=row.can_settings,
        staff=row.can_staff,
    )


async def get_seller_permissions(
    session: AsyncSession,
    user: User,
) -> SellerPermissionsSnapshot:
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        return SellerPermissionsSnapshot()
    row = await session.get(SellerStaffPermissions, user.id)
    return _from_row(row)


async def can_manage_seller_staff(
    session: AsyncSession,
    user: User,
) -> bool:
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        return False
    return (await get_seller_permissions(session, user)).staff


async def list_seller_staff_users(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[tuple[User, SellerPermissionsSnapshot, bool]]:
    stmt = (
        select(User)
        .where(
            User.tenant_id == tenant_id,
            User.seller_id == seller_id,
            User.role == FULFILLMENT_SELLER,
        )
        .options(selectinload(User.seller_staff_permissions))
        .order_by(User.created_at.asc())
    )
    res = await session.execute(stmt)
    rows: list[tuple[User, SellerPermissionsSnapshot, bool]] = []
    for user in res.scalars().all():
        is_owner = user.seller_staff_permissions is None
        rows.append((user, _from_row(user.seller_staff_permissions), is_owner))
    return rows


async def create_seller_staff_user(
    session: AsyncSession,
    *,
    acting_user: User,
    email: str,
    password: str | None,
    permissions: SellerPermissionsSnapshot,
) -> tuple[User, SellerPermissionsSnapshot]:
    if not await can_manage_seller_staff(session, acting_user):
        raise PermissionError("forbidden")
    if acting_user.seller_id is None:
        raise PermissionError("seller_not_linked")
    if password and password.strip():
        password_hash = hash_password(password)
        must_set_password = False
    else:
        password_hash = hash_password(secrets.token_urlsafe(64))
        must_set_password = True
    user = User(
        tenant_id=acting_user.tenant_id,
        seller_id=acting_user.seller_id,
        email=email.strip().lower(),
        password_hash=password_hash,
        must_set_password=must_set_password,
        role=FULFILLMENT_SELLER,
    )
    session.add(user)
    await session.flush()
    row = SellerStaffPermissions(
        user_id=user.id,
        can_documents=permissions.documents,
        can_products=permissions.products,
        can_honest_sign=permissions.honest_sign,
        can_settings=permissions.settings,
        can_staff=permissions.staff,
    )
    session.add(row)
    user.seller_staff_permissions = row
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("email_taken") from exc
    await session.refresh(user)
    await session.refresh(row)
    return user, _from_row(row)


async def update_seller_staff_permissions(
    session: AsyncSession,
    *,
    acting_user: User,
    staff_user_id: uuid.UUID,
    permissions: SellerPermissionsSnapshot,
) -> tuple[User, SellerPermissionsSnapshot]:
    if not await can_manage_seller_staff(session, acting_user):
        raise PermissionError("forbidden")
    if acting_user.seller_id is None:
        raise PermissionError("seller_not_linked")
    user = await session.get(
        User,
        staff_user_id,
        options=(selectinload(User.seller_staff_permissions),),
    )
    if (
        user is None
        or user.tenant_id != acting_user.tenant_id
        or user.seller_id != acting_user.seller_id
    ):
        raise LookupError("user_not_found")
    if user.role != FULFILLMENT_SELLER:
        raise PermissionError("not_seller_user")
    row = await session.get(SellerStaffPermissions, user.id)
    if row is None:
        raise PermissionError("owner_protected")
    if acting_user.id == staff_user_id:
        raise PermissionError("self_update_forbidden")
    row.can_documents = permissions.documents
    row.can_products = permissions.products
    row.can_honest_sign = permissions.honest_sign
    row.can_settings = permissions.settings
    row.can_staff = permissions.staff
    await session.commit()
    await session.refresh(user)
    await session.refresh(row)
    return user, _from_row(row)
