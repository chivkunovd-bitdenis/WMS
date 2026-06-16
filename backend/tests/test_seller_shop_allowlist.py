from __future__ import annotations

import uuid

import pytest

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.models.user import User
from app.services.seller_shop_service import user_can_manage_seller_shops


def _seller_user(email: str, *, can_manage: bool = False) -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        email=email,
        password_hash="x",
        role=FULFILLMENT_SELLER,
        can_manage_seller_shops=can_manage,
    )


@pytest.mark.parametrize(
    "email",
    [
        "vitalik@mail.ru",
        "shop.vitaliy@example.com",
        "виталий@mail.ru",
        "denmarks@mail.ru",
        "owner.denmark@company.ru",
    ],
)
def test_shop_manager_markers_allow(email: str) -> None:
    assert user_can_manage_seller_shops(_seller_user(email)) is True


@pytest.mark.parametrize(
    "email",
    [
        "regular@mail.ru",
        "seller123@company.ru",
        "admin@example.com",
    ],
)
def test_regular_seller_email_denied(email: str) -> None:
    assert user_can_manage_seller_shops(_seller_user(email)) is False


def test_db_flag_allows_any_seller_email() -> None:
    assert user_can_manage_seller_shops(_seller_user("any@mail.ru", can_manage=True)) is True


def test_non_seller_role_denied_even_with_marker() -> None:
    user = User(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        seller_id=None,
        email="vitalik@mail.ru",
        password_hash="x",
        role=FULFILLMENT_ADMIN,
        can_manage_seller_shops=False,
    )
    assert user_can_manage_seller_shops(user) is False
