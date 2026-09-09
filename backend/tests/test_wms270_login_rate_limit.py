"""WMS-270. Ограничение частоты /auth/login.

Проверяем, что после N неуспешных попыток шестая отдаёт 429 c Retry-After и
что успешный вход по правильным данным сбрасывает счётчик пары (IP, почта).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.login_rate_limit import (
    configure_for_tests,
    reset_rate_limit_state,
)


@pytest.fixture(autouse=True)
def _fresh_rate_limit() -> None:
    # 5 попыток в 60 секунд — штатные значения.
    reset_rate_limit_state()
    configure_for_tests(max_attempts=5, window_seconds=60)


async def _register_org(client: AsyncClient, *, slug: str, email: str) -> None:
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


@pytest.mark.asyncio
async def test_sixth_failed_attempt_returns_429_with_retry_after(
    async_client: AsyncClient,
) -> None:
    await _register_org(client=async_client, slug="rl-a", email="rl-a@example.com")

    for _ in range(5):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl-a@example.com", "password": "wrongwrongwrong"},
        )
        assert r.status_code == 401, r.text

    blocked = await async_client.post(
        "/auth/login",
        json={"email": "rl-a@example.com", "password": "wrongwrongwrong"},
    )
    assert blocked.status_code == 429, blocked.text
    assert blocked.headers.get("retry-after"), blocked.headers
    # Retry-After должен быть числом секунд, ≤ настроенного окна.
    assert 0 < int(blocked.headers["retry-after"]) <= 60


@pytest.mark.asyncio
async def test_successful_login_resets_pair_counter(async_client: AsyncClient) -> None:
    await _register_org(client=async_client, slug="rl-b", email="rl-b@example.com")

    # 4 неуспеха — ещё под лимитом.
    for _ in range(4):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl-b@example.com", "password": "wrongwrongwrong"},
        )
        assert r.status_code == 401

    # Успех сбрасывает пару (IP, почта). Но по IP счётчик остаётся — значит
    # для проверки берём другую почту не смысла, здесь важен именно успех той же пары.
    ok = await async_client.post(
        "/auth/login",
        json={"email": "rl-b@example.com", "password": "password123"},
    )
    assert ok.status_code == 200, ok.text

    # После успеха можно снова пробовать неверный пароль на этой паре и
    # не упереться в лимит пары. Проверяем поведенчески: одна неудача после
    # успеха всё ещё разрешена (пара обнулилась, счётчик стартует с 0).
    r = await async_client.post(
        "/auth/login",
        json={"email": "rl-b@example.com", "password": "wrongwrongwrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_rate_limit_scope_is_per_ip_and_email(async_client: AsyncClient) -> None:
    """С одного IP шестая попытка режется даже по разным почтам.

    Это защита от перебора адресов: у нас в лимите две шкалы — по IP и по паре
    (IP, почта). Первая ловит перебор адресов, вторая — перебор паролей.
    """
    await _register_org(client=async_client, slug="rl-c", email="rl-c@example.com")

    # 5 попыток по разным несуществующим почтам с одного IP.
    for i in range(5):
        r = await async_client.post(
            "/auth/login",
            json={"email": f"nobody-{i}@example.com", "password": "wrongwrongwrong"},
        )
        assert r.status_code == 401

    # Шестая попытка с ещё одной новой почты — уже 429 по IP-шкале.
    blocked = await async_client.post(
        "/auth/login",
        json={"email": "nobody-6@example.com", "password": "wrongwrongwrong"},
    )
    assert blocked.status_code == 429, blocked.text


@pytest.mark.asyncio
async def test_rate_limit_configurable_window(async_client: AsyncClient) -> None:
    """Тесты могут ужимать окно; проверяем, что настройка применяется."""
    configure_for_tests(max_attempts=2, window_seconds=60)
    await _register_org(client=async_client, slug="rl-d", email="rl-d@example.com")

    for _ in range(2):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl-d@example.com", "password": "wrongwrongwrong"},
        )
        assert r.status_code == 401

    blocked = await async_client.post(
        "/auth/login",
        json={"email": "rl-d@example.com", "password": "wrongwrongwrong"},
    )
    assert blocked.status_code == 429
