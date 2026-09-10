"""WMS-270. Единый ответ /auth/login и отсутствие оракула по состоянию аккаунта.

Проверяем, что снаружи по коду и телу ответа нельзя различить:
- нет такой почты;
- пароль ещё не задан (must_set_password);
- пароль неверен.

Все три отдают HTTP 401 с одинаковым телом `{"detail": "invalid_credentials"}`.
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

from app.services.login_rate_limit import (
    configure_for_tests,
    reset_rate_limit_state,
)


@pytest.fixture(autouse=True)
def _reset_login_rate_limit() -> None:
    # Каждый тест — с чистого счётчика и штатным окном.
    reset_rate_limit_state()
    configure_for_tests(max_attempts=5, window_seconds=60)


async def _register_org(client: AsyncClient, *, slug: str, email: str) -> str:
    reg = await client.post(
        "/auth/register",
        json={
            "organization_name": f"Org {slug}",
            "slug": slug,
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return reg.json()["access_token"]


async def _create_seller_account(
    client: AsyncClient, admin_token: str, *, email: str
) -> None:
    # Заводим селлера без пароля, чтобы получить must_set_password=True.
    seller = await client.post(
        "/sellers",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": f"Seller {email}"},
    )
    assert seller.status_code in (200, 201), seller.text
    seller_id = seller.json()["id"]
    acc = await client.post(
        "/auth/seller-accounts",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"seller_id": seller_id, "email": email},
    )
    assert acc.status_code == 201, acc.text


@pytest.mark.asyncio
async def test_login_wrong_email_returns_unified_401(async_client: AsyncClient) -> None:
    # Заводим одну организацию, потом стучимся с несуществующей почтой.
    await _register_org(client=async_client, slug="leak-a", email="leak-a@example.com")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "nope@example.com", "password": "password123"},
    )
    assert resp.status_code == 401, resp.text
    assert resp.json() == {"detail": "invalid_credentials"}


@pytest.mark.asyncio
async def test_login_wrong_password_returns_unified_401(async_client: AsyncClient) -> None:
    await _register_org(client=async_client, slug="leak-b", email="leak-b@example.com")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "leak-b@example.com", "password": "wrongwrongwrong"},
    )
    assert resp.status_code == 401, resp.text
    assert resp.json() == {"detail": "invalid_credentials"}


@pytest.mark.asyncio
async def test_login_correct_credentials_returns_token(async_client: AsyncClient) -> None:
    await _register_org(client=async_client, slug="leak-c", email="leak-c@example.com")

    resp = await async_client.post(
        "/auth/login",
        json={"email": "leak-c@example.com", "password": "password123"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_pending_password_setup_hidden_as_401(async_client: AsyncClient) -> None:
    # Аккаунт селлера без пароля: раньше здесь утекало 403 password_setup_required.
    admin_token = await _register_org(
        client=async_client, slug="leak-d", email="leak-d-admin@example.com"
    )
    await _create_seller_account(
        async_client, admin_token, email="leak-d-seller@example.com"
    )

    # Ни пустой, ни какой-либо пароль по такой почте не должен намекать
    # на то, что аккаунт ждёт установки пароля.
    for pwd in ("", "wrongwrongwrong", "password123"):
        resp = await async_client.post(
            "/auth/login",
            json={"email": "leak-d-seller@example.com", "password": pwd},
        )
        assert resp.status_code == 401, (pwd, resp.text)
        assert resp.json() == {"detail": "invalid_credentials"}


@pytest.mark.asyncio
async def test_login_missing_vs_wrong_password_timing_close(
    async_client: AsyncClient,
) -> None:
    """Best-effort timing check.

    Времена ответа для «нет такой почты» и «пароль неверен» должны отличаться
    в разы не сильнее шума ASGI. Мы не пытаемся выйти в микросекунды: точка —
    что путь «нет пользователя» всё равно прогоняет bcrypt, и разница по времени
    не в порядке величины.
    """
    await _register_org(client=async_client, slug="leak-t", email="leak-t@example.com")

    async def _one(payload: dict[str, str]) -> float:
        # Прогреваем один раз, чтобы не мерить импорты/аллокацию SQLAlchemy.
        await async_client.post("/auth/login", json=payload)
        start = time.perf_counter()
        await async_client.post("/auth/login", json=payload)
        return time.perf_counter() - start

    # Мерим на другой почте, чтобы rate limit не выбил нас на 6-й попытке.
    reset_rate_limit_state()
    t_missing = await _one(
        {"email": "leak-timing-nobody@example.com", "password": "password123"}
    )
    reset_rate_limit_state()
    t_wrong = await _one(
        {"email": "leak-t@example.com", "password": "wrongwrongwrong"}
    )

    # Оба пути должны быть в одном порядке. Допуск щедрый (fudge factor 10x)
    # из-за шумных CI, но всё равно ловит случай, когда одна ветка не считает bcrypt.
    ratio = max(t_missing, t_wrong) / max(1e-6, min(t_missing, t_wrong))
    assert ratio < 10.0, (t_missing, t_wrong, ratio)
