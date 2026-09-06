"""WMS-378/379/383: приглашение и сброс пароля ссылкой, закрытая регистрация."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.user import User
from tests.auth_helpers import password_link_token, set_password_via_link


async def _register_admin(client: AsyncClient, slug: str) -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Org {slug}",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_seller_account(client: AsyncClient, headers: dict[str, str], email: str) -> str:
    seller = await client.post("/sellers", headers=headers, json={"name": f"Селлер {email}"})
    assert seller.status_code == 201, seller.text
    created = await client.post(
        "/auth/seller-accounts",
        headers=headers,
        json={"seller_id": seller.json()["id"], "email": email},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


@pytest.mark.asyncio
async def test_public_registration_closed_by_default(async_client: AsyncClient) -> None:
    """Открытая регистрация организации закрыта, пока её явно не включили."""
    original = settings.allow_public_registration
    settings.allow_public_registration = False
    try:
        response = await async_client.post(
            "/auth/register",
            json={
                "organization_name": "Чужая организация",
                "slug": "chuzhaya",
                "admin_email": "stranger@example.com",
                "password": "password123",
            },
        )
    finally:
        settings.allow_public_registration = original
    assert response.status_code == 403
    assert response.json()["detail"] == "registration_closed"


@pytest.mark.asyncio
async def test_invite_link_sets_password_and_logs_in(async_client: AsyncClient) -> None:
    headers = await _register_admin(async_client, "invite-flow")
    email = "seller-invite-flow@example.com"
    await _create_seller_account(async_client, headers, email)

    # До установки пароля вход закрыт.
    login_before = await async_client.post(
        "/auth/login", json={"email": email, "password": ""}
    )
    assert login_before.status_code == 403
    assert login_before.json()["detail"] == "password_setup_required"

    accepted = await set_password_via_link(async_client, email, "novyparol123")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["access_token"]

    login_after = await async_client.post(
        "/auth/login", json={"email": email, "password": "novyparol123"}
    )
    assert login_after.status_code == 200, login_after.text


@pytest.mark.asyncio
async def test_invite_link_works_once(async_client: AsyncClient) -> None:
    """Ссылка перестаёт работать, как только пароль по ней задан."""
    headers = await _register_admin(async_client, "invite-once")
    email = "seller-invite-once@example.com"
    await _create_seller_account(async_client, headers, email)

    token = await password_link_token(email)
    first = await async_client.post(
        "/auth/set-password", json={"token": token, "password": "pervyparol123"}
    )
    assert first.status_code == 200, first.text

    second = await async_client.post(
        "/auth/set-password", json={"token": token, "password": "vtoroyparol123"}
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "link_used"

    # Старый пароль остался рабочим, вторая попытка ничего не переписала.
    login = await async_client.post(
        "/auth/login", json={"email": email, "password": "pervyparol123"}
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_password_reset_flow(async_client: AsyncClient) -> None:
    headers = await _register_admin(async_client, "reset-flow")
    email = "seller-reset-flow@example.com"
    await _create_seller_account(async_client, headers, email)
    assert (await set_password_via_link(async_client, email, "staryparol123")).status_code == 200

    requested = await async_client.post(
        "/auth/request-password-reset", json={"email": email}
    )
    assert requested.status_code == 204

    token = await password_link_token(email, purpose="reset")
    changed = await async_client.post(
        "/auth/set-password", json={"token": token, "password": "svezhiyparol123"}
    )
    assert changed.status_code == 200, changed.text

    old_login = await async_client.post(
        "/auth/login", json={"email": email, "password": "staryparol123"}
    )
    assert old_login.status_code == 401

    new_login = await async_client.post(
        "/auth/login", json={"email": email, "password": "svezhiyparol123"}
    )
    assert new_login.status_code == 200, new_login.text


@pytest.mark.asyncio
async def test_password_reset_request_hides_unknown_email(async_client: AsyncClient) -> None:
    """Ответ одинаковый и для существующей, и для незнакомой почты."""
    response = await async_client.post(
        "/auth/request-password-reset", json={"email": "nobody-here@example.com"}
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_broken_and_expired_links_rejected(async_client: AsyncClient) -> None:
    headers = await _register_admin(async_client, "bad-links")
    email = "seller-bad-links@example.com"
    await _create_seller_account(async_client, headers, email)

    garbage = await async_client.post(
        "/auth/set-password",
        json={"token": "a" * 40, "password": "lyuboyparol123"},
    )
    assert garbage.status_code == 400
    assert garbage.json()["detail"] == "link_invalid"

    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user_id = user.id

    expired = jwt.encode(
        {
            "typ": "auth_link",
            "purpose": "invite",
            "sub": str(user_id),
            "pwf": "0" * 16,
            "iat": datetime.now(tz=UTC) - timedelta(hours=200),
            "exp": datetime.now(tz=UTC) - timedelta(hours=100),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired_response = await async_client.post(
        "/auth/set-password", json={"token": expired, "password": "lyuboyparol123"}
    )
    assert expired_response.status_code == 410
    assert expired_response.json()["detail"] == "link_expired"

    # Ссылка на несуществующего пользователя — тот же отказ, без подсказок.
    stranger = jwt.encode(
        {
            "typ": "auth_link",
            "purpose": "invite",
            "sub": str(uuid.uuid4()),
            "pwf": "0" * 16,
            "iat": datetime.now(tz=UTC),
            "exp": datetime.now(tz=UTC) + timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    stranger_response = await async_client.post(
        "/auth/set-password", json={"token": stranger, "password": "lyuboyparol123"}
    )
    assert stranger_response.status_code == 400


@pytest.mark.asyncio
async def test_admin_resends_invite_only_inside_own_tenant(async_client: AsyncClient) -> None:
    first_headers = await _register_admin(async_client, "resend-one")
    email = "seller-resend-one@example.com"
    user_id = await _create_seller_account(async_client, first_headers, email)

    ok = await async_client.post(
        "/auth/invites/resend", headers=first_headers, json={"user_id": user_id}
    )
    assert ok.status_code == 204, ok.text

    other_headers = await _register_admin(async_client, "resend-two")
    forbidden = await async_client.post(
        "/auth/invites/resend", headers=other_headers, json={"user_id": user_id}
    )
    assert forbidden.status_code == 404
