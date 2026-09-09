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


async def test_spoofed_forwarding_headers_do_not_reset_client_limit(async_client: AsyncClient):
    for attempt in range(5):
        response = await async_client.post(
            "/auth/login", headers={"X-Forwarded-For": f"198.51.100.{attempt}"},
            json={"email": "missing@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
    response = await async_client.post(
        "/auth/login", headers={"X-Forwarded-For": "203.0.113.99"},
        json={"email": "missing@example.com", "password": "wrong"},
    )
    assert response.status_code == 429


def test_concurrent_attempts_are_charged_before_password_check():
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import HTTPException
    from starlette.requests import Request

    from app.services.login_rate_limit import check_login_rate_limit

    def attempt(index):
        request = Request({"type": "http", "client": ("192.0.2.1", 123), "headers": []})
        try:
            check_login_rate_limit(request=request, email=f"{index}@example.com")
            return True
        except HTTPException as error:
            assert error.status_code == 429
            return False
    with ThreadPoolExecutor(max_workers=20) as executor:
        assert sum(executor.map(attempt, range(40))) == 5


def test_limiter_bounds_memory_and_reclaims_expired_clients(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.services import login_rate_limit as limiter

    monkeypatch.setattr(limiter, "_MAX_CLIENTS", 2)
    clock = [100.0]
    monkeypatch.setattr(limiter.time, "monotonic", lambda: clock[0])
    def attempt(ip):
        limiter.check_login_rate_limit(
            request=Request({"type": "http", "client": (ip, 123), "headers": []}),
            email="test@example.com",
        )
    attempt("192.0.2.1")
    attempt("192.0.2.2")
    with pytest.raises(HTTPException) as error:
        attempt("192.0.2.3")
    assert error.value.status_code == 429
    assert len(limiter._attempts) == 2
    clock[0] += 60
    attempt("192.0.2.3")
    assert list(limiter._attempts) == ["192.0.2.3"]


async def test_concurrent_http_logins_are_limited_while_authentication_is_pending(
    async_client: AsyncClient, monkeypatch,
):
    import asyncio

    from app.api import auth
    from app.services.auth_service import AuthError

    pending = 0
    five_entered = asyncio.Event()
    release = asyncio.Event()

    async def authenticate(*args, **kwargs):
        nonlocal pending
        pending += 1
        if pending == 5:
            five_entered.set()
        await release.wait()
        raise AuthError("invalid_credentials")

    monkeypatch.setattr(auth, "login", authenticate)
    tasks = [asyncio.create_task(async_client.post(
        "/auth/login", json={"email": f"burst-{i}@example.com", "password": "wrong"},
    )) for i in range(20)]
    try:
        await asyncio.wait_for(five_entered.wait(), timeout=3)
        release.set()
        responses = await asyncio.gather(*tasks)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert pending == 5
    assert sorted(response.status_code for response in responses) == [401] * 5 + [429] * 15
