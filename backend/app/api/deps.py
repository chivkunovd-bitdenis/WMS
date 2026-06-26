from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FF_PORTAL_ROLES, FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import get_user_by_id
from app.services.seller_shop_service import (
    SellerShopError,
    assert_can_act_as_seller,
    user_can_manage_seller_shops,
)
from app.services.staff_permissions_service import (
    PERM_CELLS,
    PERM_MP_SHIPMENTS,
    PERM_PACKAGING,
    PERM_RECEPTION,
    PERM_SHIFT_LEAD,
    get_staff_permissions,
)
from app.services.tokens import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def resolve_effective_seller_id(
    session: AsyncSession,
    user: User,
    credentials: HTTPAuthorizationCredentials | None,
) -> uuid.UUID | None:
    """Seller scope: JWT seller_id when delegated, else user's home seller."""
    if user.role != FULFILLMENT_SELLER:
        return user.seller_id
    home_seller_id = user.seller_id
    if home_seller_id is None:
        return None
    if not user_can_manage_seller_shops(user):
        return home_seller_id
    if credentials is None or credentials.scheme.lower() != "bearer":
        return home_seller_id
    try:
        payload = decode_access_token(credentials.credentials)
        raw = payload.get("seller_id")
        if not isinstance(raw, str):
            return home_seller_id
        active_seller_id = uuid.UUID(raw)
    except (jwt.PyJWTError, ValueError):
        return home_seller_id
    if active_seller_id == home_seller_id:
        return home_seller_id
    try:
        await assert_can_act_as_seller(session, user, active_seller_id)
    except SellerShopError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from None
    return active_seller_id


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not_authenticated",
        )
    try:
        payload = decode_access_token(credentials.credentials)
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise jwt.InvalidTokenError("missing sub")
        user_id = uuid.UUID(sub)
        tenant_raw = payload.get("tenant_id")
        if not isinstance(tenant_raw, str):
            raise jwt.InvalidTokenError("missing tenant_id")
        token_tenant_id = uuid.UUID(tenant_raw)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_token",
        ) from None
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user_not_found",
        )
    if user.tenant_id != token_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_mismatch",
        )
    return user


async def get_effective_seller_id(
    user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> uuid.UUID | None:
    return await resolve_effective_seller_id(session, user, credentials)


async def require_fulfillment_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != FULFILLMENT_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    return user


async def require_ff_or_seller(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    if user.role == FULFILLMENT_SELLER and user.seller_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="seller_not_linked",
        )
    return user


async def require_ff_portal_member(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role not in FF_PORTAL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    return user


def require_ff_permission(
    permission: str,
) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if user.role == FULFILLMENT_ADMIN:
            return user
        if user.role == FULFILLMENT_STAFF:
            perms = await get_staff_permissions(session, user)
            if perms.has(permission):
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    return _dep


def require_ff_or_seller_with_permission(
    permission: str,
) -> Callable[..., Awaitable[User]]:
    async def _dep(
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if user.role == FULFILLMENT_ADMIN:
            return user
        if user.role == FULFILLMENT_SELLER:
            if user.seller_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="seller_not_linked",
                )
            return user
        if user.role == FULFILLMENT_STAFF:
            perms = await get_staff_permissions(session, user)
            if perms.has(permission):
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )

    return _dep


require_reception_access = require_ff_permission(PERM_RECEPTION)
require_mp_shipments_access = require_ff_or_seller_with_permission(PERM_MP_SHIPMENTS)
require_cells_access = require_ff_permission(PERM_CELLS)
require_packaging_access = require_ff_permission(PERM_PACKAGING)
require_shift_lead = require_ff_permission(PERM_SHIFT_LEAD)


async def seller_line_product_scope(
    user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> uuid.UUID | None:
    """For fulfillment_seller: filter operations to active seller when set."""
    if user.role == FULFILLMENT_SELLER:
        seller_id = await resolve_effective_seller_id(session, user, credentials)
        if seller_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="seller_not_linked",
            )
        return seller_id
    return None
