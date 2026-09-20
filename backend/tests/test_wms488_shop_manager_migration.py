from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.models.seller import Seller
from app.models.seller_shop_delegation import SellerShopDelegation
from app.models.tenant import Tenant
from app.models.user import User


def _migration() -> ModuleType:
    path = (
        Path(__file__).parents[1] / "alembic/versions/20260921_0488_explicit_shop_manager_grants.py"
    )
    spec = importlib.util.spec_from_file_location("wms488_grants", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _upgrade(connection: Connection) -> None:
    migration = _migration()
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()


@pytest.mark.parametrize("slug", ["avpack", "avpack-9uczh"])
async def test_migration_preserves_only_existing_eligible_delegated_grants(
    db_session: AsyncSession,
    slug: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("shop_manager_emails", raising=False)
    monkeypatch.delenv("SHOP_MANAGER_EMAILS", raising=False)
    monkeypatch.setenv("WMS_SHOP_MANAGER_EMAILS", " Exact@Merchant.Ru , ")
    tenant = Tenant(name="AVpack", slug=slug)
    foreign = Tenant(name="Other", slug="other")
    db_session.add_all([tenant, foreign])
    await db_session.flush()
    home = Seller(tenant_id=tenant.id, name="Home")
    target = Seller(tenant_id=tenant.id, name="Delegated")
    foreign_shop = Seller(tenant_id=foreign.id, name="Foreign")
    db_session.add_all([home, target, foreign_shop])
    await db_session.flush()

    # email, home, delegation target, enabled, existing flag, role, expected flag
    cases = [
        ("vitalik-enabled@merchant.ru", home, target, True, False, FULFILLMENT_SELLER, True),
        ("vitaliy-disabled@merchant.ru", home, target, False, False, FULFILLMENT_SELLER, True),
        (" DENMARK-UPPER@MERCHANT.RU ", home, target, False, False, FULFILLMENT_SELLER, True),
        ("виталий@merchant.ru", home, target, True, False, FULFILLMENT_SELLER, True),
        ("exact@merchant.ru", home, target, False, False, FULFILLMENT_SELLER, True),
        ("not-exact@merchant.ru", home, target, True, False, FULFILLMENT_SELLER, False),
        ("ordinary@merchant.ru", home, target, True, False, FULFILLMENT_SELLER, False),
        ("vitalik-new@merchant.ru", home, None, False, False, FULFILLMENT_SELLER, False),
        ("vitalik-other@merchant.ru", home, foreign_shop, True, False, FULFILLMENT_SELLER, False),
        ("vitalik-no-home@merchant.ru", None, target, True, False, FULFILLMENT_SELLER, False),
        (
            "vitalik-bad-home@merchant.ru",
            foreign_shop,
            target,
            True,
            False,
            FULFILLMENT_SELLER,
            False,
        ),
        ("vitalik-self@merchant.ru", home, home, True, False, FULFILLMENT_SELLER, False),
        ("vitalik-admin@merchant.ru", home, target, True, False, FULFILLMENT_ADMIN, False),
        ("explicit@merchant.ru", home, None, False, True, FULFILLMENT_SELLER, True),
    ]
    expected = {}
    for email, seller, delegated, enabled, flag, role, outcome in cases:
        user = User(
            tenant_id=tenant.id,
            seller_id=seller.id if seller else None,
            email=email,
            password_hash="unused",
            role=role,
            can_manage_seller_shops=flag,
        )
        db_session.add(user)
        await db_session.flush()
        expected[user.id] = flag if slug == "avpack-9uczh" else outcome
        if delegated is not None:
            db_session.add(
                SellerShopDelegation(
                    user_id=user.id,
                    target_seller_id=delegated.id,
                    enabled=enabled,
                )
            )
    await db_session.flush()
    delegation_query = select(
        SellerShopDelegation.id,
        SellerShopDelegation.user_id,
        SellerShopDelegation.target_seller_id,
        SellerShopDelegation.enabled,
    ).order_by(SellerShopDelegation.id)
    before = (await db_session.execute(delegation_query)).all()
    connection = await db_session.connection()
    for _ in range(2):
        await connection.run_sync(_upgrade)
        actual = dict(
            (await db_session.execute(select(User.id, User.can_manage_seller_shops))).all()
        )
        assert actual == expected
        assert (await db_session.execute(delegation_query)).all() == before


@pytest.mark.parametrize(
    ("environment", "dotenv", "expected"),
    [
        (
            {"shop_manager_emails": "", "WMS_SHOP_MANAGER_EMAILS": "fallback@merchant.ru"},
            "",
            "fallback@merchant.ru",
        ),
        (
            {"WMS_SHOP_MANAGER_EMAILS": ""},
            "WMS_SHOP_MANAGER_EMAILS=dotenv@merchant.ru\n",
            "dotenv@merchant.ru",
        ),
        ({"SHOP_MANAGER_EMAILS": "alias@merchant.ru"}, "", "alias@merchant.ru"),
        ({"wms_shop_manager_emails": "lower@merchant.ru"}, "", "lower@merchant.ru"),
        (
            {
                "shop_manager_emails": "primary@merchant.ru",
                "WMS_SHOP_MANAGER_EMAILS": "other@merchant.ru",
            },
            "",
            "primary@merchant.ru",
        ),
    ],
)
def test_migration_keeps_legacy_configuration_resolution(
    monkeypatch,
    tmp_path: Path,
    environment: dict[str, str],
    dotenv: str,
    expected: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    for alias in (
        "shop_manager_emails",
        "WMS_SHOP_MANAGER_EMAILS",
        "SHOP_MANAGER_EMAILS",
        "wms_shop_manager_emails",
    ):
        monkeypatch.delenv(alias, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    (tmp_path / ".env").write_text(dotenv)
    assert _migration()._LegacyAllowlist().emails == expected
