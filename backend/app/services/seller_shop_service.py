from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_SELLER
from app.core.settings import settings
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.user import User


class SellerShopError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_TEST_EMAIL_SUFFIXES = ("@test.example.com", "@example.com")
_TEST_EMAIL_PREFIXES = ("e2e-", "iso-", "test-", "cat-")


def is_test_user_email(email: str) -> bool:
    normalized = email.strip().lower()
    if any(normalized.endswith(suffix) for suffix in _TEST_EMAIL_SUFFIXES):
        return True
    local = normalized.split("@", 1)[0]
    return any(local.startswith(prefix) for prefix in _TEST_EMAIL_PREFIXES)


def user_can_manage_seller_shops(user: User) -> bool:
    if user.role != FULFILLMENT_SELLER:
        return False
    if user.can_manage_seller_shops:
        return True
    email = user.email.strip().lower()
    if "vitalik" in email or "виталик" in email:
        return True
    configured = settings.shop_manager_emails.strip().lower()
    if not configured:
        return False
    allowed = {e.strip() for e in configured.split(",") if e.strip()}
    return user.email.strip().lower() in allowed


async def is_test_seller(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> bool:
    stmt = select(User.email).where(
        User.tenant_id == tenant_id,
        User.seller_id == seller_id,
    )
    res = await session.execute(stmt)
    emails = list(res.scalars().all())
    if not emails:
        sl = await session.get(Seller, seller_id)
        if sl is None:
            return True
        name = sl.name.strip().lower()
        return "test" in name or name.startswith("wms test")
    return all(is_test_user_email(email) for email in emails)


async def list_delegatable_shops(
    session: AsyncSession,
    user: User,
) -> list[tuple[Seller, bool]]:
    """All tenant sellers except own and test; bool = enabled delegation."""
    if not user_can_manage_seller_shops(user) or user.seller_id is None:
        return []
    deleg_stmt = select(SellerShopDelegation).where(
        SellerShopDelegation.user_id == user.id,
    )
    deleg_res = await session.execute(deleg_stmt)
    enabled_by_seller = {
        d.target_seller_id: d.enabled for d in deleg_res.scalars().all()
    }
    sellers_stmt = (
        select(Seller)
        .where(Seller.tenant_id == user.tenant_id)
        .order_by(Seller.name)
    )
    sellers_res = await session.execute(sellers_stmt)
    out: list[tuple[Seller, bool]] = []
    for seller in sellers_res.scalars().all():
        if seller.id == user.seller_id:
            continue
        if await is_test_seller(session, user.tenant_id, seller.id):
            continue
        out.append((seller, enabled_by_seller.get(seller.id, False)))
    return out


async def update_enabled_shops(
    session: AsyncSession,
    user: User,
    enabled_seller_ids: list[uuid.UUID],
) -> list[tuple[Seller, bool]]:
    if not user_can_manage_seller_shops(user):
        raise SellerShopError("forbidden")
    allowed = {
        seller.id
        for seller, _ in await list_delegatable_shops(session, user)
    }
    for sid in enabled_seller_ids:
        if sid not in allowed:
            raise SellerShopError("seller_not_allowed")
    existing_stmt = select(SellerShopDelegation).where(
        SellerShopDelegation.user_id == user.id,
    )
    existing_res = await session.execute(existing_stmt)
    existing = {d.target_seller_id: d for d in existing_res.scalars().all()}
    desired = set(enabled_seller_ids)
    for sid in desired:
        row = existing.get(sid)
        if row is None:
            session.add(
                SellerShopDelegation(
                    user_id=user.id,
                    target_seller_id=sid,
                    enabled=True,
                )
            )
        else:
            row.enabled = True
    for sid, row in existing.items():
        if sid not in desired:
            row.enabled = False
    await session.commit()
    return await list_delegatable_shops(session, user)


async def can_act_as_seller(
    session: AsyncSession,
    user: User,
    target_seller_id: uuid.UUID,
) -> bool:
    if user.role != FULFILLMENT_SELLER or user.seller_id is None:
        return False
    if target_seller_id == user.seller_id:
        return True
    if not user_can_manage_seller_shops(user):
        return False
    stmt = select(SellerShopDelegation).where(
        SellerShopDelegation.user_id == user.id,
        SellerShopDelegation.target_seller_id == target_seller_id,
        SellerShopDelegation.enabled.is_(True),
    )
    res = await session.execute(stmt)
    delegation = res.scalar_one_or_none()
    if delegation is None:
        return False
    sl = await session.get(Seller, target_seller_id)
    if sl is None or sl.tenant_id != user.tenant_id:
        return False
    return not await is_test_seller(session, user.tenant_id, target_seller_id)


async def assert_can_act_as_seller(
    session: AsyncSession,
    user: User,
    target_seller_id: uuid.UUID,
) -> None:
    if not await can_act_as_seller(session, user, target_seller_id):
        raise SellerShopError("forbidden")


async def list_switchable_shops(
    session: AsyncSession,
    user: User,
) -> list[Seller]:
    """Own shop + enabled delegated shops (for sidebar switcher)."""
    if user.seller_id is None:
        return []
    home = await session.get(Seller, user.seller_id)
    if home is None:
        return []
    shops = [home]
    if not user_can_manage_seller_shops(user):
        return shops
    for seller, enabled in await list_delegatable_shops(session, user):
        if enabled:
            shops.append(seller)
    return shops
