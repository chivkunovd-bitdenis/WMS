from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.models.seller import Seller
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
        must_set_password=False,
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
    if user is None:
        raise AuthError("invalid_credentials")
    if user.must_set_password:
        if password.strip() == "":
            raise AuthError("password_setup_required")
        raise AuthError("invalid_credentials")
    if not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials")
    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        seller_id=user.seller_id,
    )
    return user, token


async def create_seller_user(
    session: AsyncSession,
    *,
    acting_user: User,
    seller_id: uuid.UUID,
    email: str,
    password: str | None,
) -> User:
    if acting_user.role != FULFILLMENT_ADMIN:
        raise AuthError("forbidden")
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != acting_user.tenant_id:
        raise AuthError("seller_not_found")
    if password and password.strip():
        password_hash = hash_password(password)
        must_set_password = False
    else:
        password_hash = hash_password(secrets.token_urlsafe(64))
        must_set_password = True
    user = User(
        tenant_id=acting_user.tenant_id,
        seller_id=seller_id,
        email=email.strip().lower(),
        password_hash=password_hash,
        must_set_password=must_set_password,
        role=FULFILLMENT_SELLER,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AuthError("email_taken") from exc
    await session.refresh(user)
    return user


async def set_initial_password(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError("invalid_credentials")
    if user.role != FULFILLMENT_SELLER:
        raise AuthError("forbidden")
    if not user.must_set_password:
        raise AuthError("password_already_set")
    user.password_hash = hash_password(password)
    user.must_set_password = False
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)
