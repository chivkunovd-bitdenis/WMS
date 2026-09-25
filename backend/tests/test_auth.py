from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import Settings, settings
from app.db.session import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User


@pytest.mark.asyncio
async def test_same_email_has_separate_ff_and_seller_logins(async_client: AsyncClient) -> None:
    email = "same-person@example.com"
    password = "shared-password123"
    ff = await async_client.post("/auth/register", json={
        "organization_name": "Same Person FF", "slug": "same-person-ff",
        "admin_email": email, "password": password,
    })
    assert ff.status_code == 200, ff.text
    ff_token = ff.json()["access_token"]

    seller = await async_client.post(
        "/sellers/with-account", json={
            "name": "Same Person Seller", "email": email, "password": password,
        }, headers={"Authorization": f"Bearer {ff_token}"},
    )
    assert seller.status_code == 201, seller.text
    assert seller.json()["role"] == "fulfillment_seller"

    for portal, expected_role in (
        ("fulfillment", "fulfillment_admin"),
        ("seller", "fulfillment_seller"),
    ):
        response = await async_client.post("/auth/login", json={
            "email": email, "password": password, "portal": portal,
        })
        assert response.status_code == 200, response.text
        profile = await async_client.get("/auth/me", headers={
            "Authorization": f"Bearer {response.json()['access_token']}"
        })
        assert profile.status_code == 200
        assert profile.json()["role"] == expected_role

    legacy_login = await async_client.post("/auth/login", json={
        "email": email, "password": password,
    })
    assert legacy_login.status_code == 200
    legacy_profile = await async_client.get("/auth/me", headers={
        "Authorization": f"Bearer {legacy_login.json()['access_token']}"
    })
    assert legacy_profile.json()["role"] == "fulfillment_admin"

    duplicate_seller = await async_client.post(
        "/sellers/with-account", json={
            "name": "Another Seller", "email": email, "password": password,
        }, headers={"Authorization": f"Bearer {ff_token}"},
    )
    assert duplicate_seller.status_code == 409


@pytest.mark.asyncio
async def test_ff_registration_accepts_existing_seller_email(async_client: AsyncClient) -> None:
    owner = await async_client.post("/auth/register", json={
        "organization_name": "Original FF", "slug": "original-ff",
        "admin_email": "original-owner@example.com", "password": "password123",
    })
    assert owner.status_code == 200
    seller = await async_client.post("/sellers/with-account", json={
        "name": "Existing Seller", "email": "seller-then-ff@example.com",
        "password": "seller-password123",
    }, headers={"Authorization": f"Bearer {owner.json()['access_token']}"})
    assert seller.status_code == 201

    ff = await async_client.post("/auth/register", json={
        "organization_name": "New FF", "slug": "new-ff",
        "admin_email": "seller-then-ff@example.com",
        "password": "ff-password123",
    })
    assert ff.status_code == 200, ff.text
    profile = await async_client.get("/auth/me", headers={
        "Authorization": f"Bearer {ff.json()['access_token']}"
    })
    assert profile.json()["organization_name"] == "New FF"
    assert profile.json()["role"] == "fulfillment_admin"


@pytest.mark.asyncio
async def test_register_login_me(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The public form must work with the shipped default, independently of
    # conftest's explicit registration override used by other API tests.
    default_enabled = Settings.model_fields["allow_public_registration"].default
    assert default_enabled is True
    monkeypatch.setattr(settings, "allow_public_registration", default_enabled)
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Test",
            "slug": "ff-test",
            "admin_email": "admin@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    assert token

    me = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == "admin@example.com"
    assert body["organization_name"] == "FF Test"
    assert body["role"] == "fulfillment_admin"
    assert body["address_storage_enabled"] is True
    assert body["separate_marking_print_enabled"] is False
    # WMS-433/R23: тестовое окружение не задаёт WMS_ASSISTANT_ENABLED_TENANTS,
    # поэтому пустая переменная по умолчанию выключает помощника у всех.
    assert body["assistant_enabled"] is False

    login = await async_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_register_creates_default_warehouse(async_client: AsyncClient) -> None:
    """WMS-062: у новой организации сразу есть один «Основной» склад, и повторных нет."""
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Warehouse Default",
            "slug": "ff-warehouse-default",
            "admin_email": "wh-default@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]

    warehouses = await async_client.get(
        "/warehouses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert warehouses.status_code == 200, warehouses.text
    items = warehouses.json()
    assert isinstance(items, list)
    names = [w["name"] for w in items]
    assert names == ["Основной"], names
    codes = [w["code"] for w in items]
    assert codes == ["main"], codes
    assert items[0]["barcode"].startswith("WH-")


@pytest.mark.asyncio
async def test_register_duplicate_slug(async_client: AsyncClient) -> None:
    payload = {
        "organization_name": "A",
        "slug": "same-slug",
        "admin_email": "a@example.com",
        "password": "password123",
    }
    r1 = await async_client.post("/auth/register", json=payload)
    assert r1.status_code == 200
    r2 = await async_client.post(
        "/auth/register",
        json={
            **payload,
            "admin_email": "b@example.com",
        },
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "slug_or_email_taken"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 1
        assert await session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.asyncio
async def test_register_duplicate_email_rolls_back_new_organization(
    async_client: AsyncClient,
) -> None:
    payload = {
        "organization_name": "Original",
        "slug": "original",
        "admin_email": "existing@example.com",
        "password": "password123",
    }
    assert (await async_client.post("/auth/register", json=payload)).status_code == 200
    duplicate = await async_client.post(
        "/auth/register", json={**payload, "slug": "duplicate", "organization_name": "Duplicate"}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "slug_or_email_taken"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(Tenant)) == 1
        assert await session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.asyncio
async def test_assistant_enabled_reflects_tenant_list_and_false_for_seller_role(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WMS-433/R23: /auth/me.assistant_enabled — true только для роли портала ФФ

    тенанта из списка (здесь «*» — включено всем); селлерская роль всегда
    false (R20: помощник в первом срезе — только портал ФФ), даже когда
    тенант включён.
    """
    from sqlalchemy import select

    from app.core.settings import settings
    from app.db.session import SessionLocal
    from app.models.seller import Seller
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.services.passwords import hash_password
    from app.services.tokens import create_access_token

    slug = "assist-me-role-check"
    monkeypatch.setattr(settings, "assistant_enabled_tenants", "*")

    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Assistant Me Role Check",
            "slug": slug,
            "admin_email": "assist-me-admin@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_me = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {reg.json()['access_token']}"}
    )
    assert admin_me.status_code == 200, admin_me.text
    assert admin_me.json()["assistant_enabled"] is True

    async with SessionLocal() as session:
        tenant = (await session.scalars(select(Tenant).where(Tenant.slug == slug))).one()
        seller = Seller(tenant_id=tenant.id, name="Assist Seller")
        session.add(seller)
        await session.flush()
        seller_user = User(
            tenant_id=tenant.id,
            seller_id=seller.id,
            email="assist-me-seller@example.com",
            password_hash=hash_password("password123"),
            role="fulfillment_seller",
        )
        session.add(seller_user)
        await session.flush()
        seller_token = create_access_token(
            user_id=seller_user.id,
            tenant_id=tenant.id,
            role=seller_user.role,
            seller_id=seller.id,
        )
        await session.commit()

    seller_me = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {seller_token}"}
    )
    assert seller_me.status_code == 200, seller_me.text
    assert seller_me.json()["assistant_enabled"] is False
