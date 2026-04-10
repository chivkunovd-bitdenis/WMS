from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN
from app.models.tenant import Tenant
from app.models.user import User
from app.services.passwords import hash_password, verify_password
from app.services.tokens import create_access_token


class AuthError(Exception):
    pass


async def register_fulfillment(
    session: AsyncSession,
    *,
    organization_name: str,
    slug: str,
    admin_email: str,
    password: str,
) -> tuple[User, Tenant]:
    tenant = Tenant(name=organization_name, slug=slug.strip().lower())
    user = User(
        tenant=tenant,
        email=admin_email.strip().lower(),
        password_hash=hash_password(password),
        role=FULFILLMENT_ADMIN,
        seller_id=None,
    )
    session.add(tenant)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("slug_or_email_taken") from exc
    await session.refresh(user)
    await session.refresh(tenant)
    return user, tenant


async def login(session: AsyncSession, *, email: str, password: str) -> tuple[User, str]:
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials")
    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, role=user.role
    )
    return user, token


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)
