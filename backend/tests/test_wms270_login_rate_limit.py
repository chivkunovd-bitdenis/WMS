"""WMS-270. Ограничение частоты /auth/login.

Проверяем лимит по IP, включая параллельные запросы. Успешный вход освобождает
только собственную попытку; прежние ошибки остаются в окне ограничения.
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
async def test_successful_login_releases_only_its_own_attempt(async_client: AsyncClient) -> None:
    await _register_org(client=async_client, slug="rl-b", email="rl-b@example.com")

    # 4 неуспеха — ещё под лимитом.
    for _ in range(4):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl-b@example.com", "password": "wrongwrongwrong"},
        )
        assert r.status_code == 401

    # Успех освобождает пятую попытку, четыре предыдущие ошибки остаются.
    ok = await async_client.post(
        "/auth/login",
        json={"email": "rl-b@example.com", "password": "password123"},
    )
    assert ok.status_code == 200, ok.text

    # Освободилось ровно одно место.
    r = await async_client.post(
        "/auth/login",
        json={"email": "rl-b@example.com", "password": "wrongwrongwrong"},
    )
    assert r.status_code == 401
    blocked = await async_client.post(
        "/auth/login",
        json={"email": "rl-b@example.com", "password": "wrongwrongwrong"},
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_scope_is_per_ip_across_emails(async_client: AsyncClient) -> None:
    """С одного IP шестая попытка режется даже по разным почтам.

    Смена адреса почты не освобождает попытки этого IP.
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
            "/auth/login",
            headers={"X-Forwarded-For": f"198.51.100.{attempt}"},
            json={"email": "missing@example.com", "password": "wrong"},
        )
        assert response.status_code == 401
    response = await async_client.post(
        "/auth/login",
        headers={"X-Forwarded-For": "203.0.113.99"},
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
    async_client: AsyncClient,
    monkeypatch,
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
    tasks = [
        asyncio.create_task(
            async_client.post(
                "/auth/login",
                json={"email": f"burst-{i}@example.com", "password": "wrong"},
            )
        )
        for i in range(20)
    ]
    try:
        await asyncio.wait_for(five_entered.wait(), timeout=3)
        release.set()
        responses = await asyncio.gather(*tasks)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert pending == 5
    assert sorted(response.status_code for response in responses) == [401] * 5 + [429] * 15


async def test_asgi_trusted_proxy_preserves_clients_and_ignores_spoofed_prefix(
    async_client: AsyncClient,
    monkeypatch,
):
    from httpx import ASGITransport
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from app.api import auth
    from app.main import app
    from app.services.auth_service import AuthError

    async def reject(*args, **kwargs):
        raise AuthError("invalid_credentials")

    monkeypatch.setattr(auth, "login", reject)
    proxy_app = ProxyHeadersMiddleware(app, trusted_hosts=["172.21.0.0/16"])
    transport = ASGITransport(app=proxy_app, client=("172.21.0.6", 12345))
    body = {"email": "proxy-test@example.com", "password": "wrong"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            for address in ("203.0.113.100", "203.0.113.101"):
                response = await client.post(
                    "/auth/login", json=body, headers={"X-Forwarded-For": address}
                )
                assert response.status_code == 401
        response = await client.post(
            "/auth/login", json=body, headers={"X-Forwarded-For": "192.0.2.99, 203.0.113.100"}
        )
        assert response.status_code == 429
    # An untrusted direct peer cannot manufacture a new client via raw XFF.
    transport = ASGITransport(app=proxy_app, client=("198.51.100.90", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = []
        for number in range(6):
            response = await client.post(
                "/auth/login", json=body, headers={"X-Forwarded-For": f"192.0.2.{number + 1}"}
            )
            statuses.append(response.status_code)
        assert statuses == [401] * 5 + [429]


async def test_password_reset_limits_work_before_scheduling_mail(
    async_client: AsyncClient, monkeypatch
):
    from app.api import auth

    calls = []

    async def reset(*args, **kwargs):
        calls.append(kwargs["email"])

    monkeypatch.setattr(auth, "request_password_reset", reset)
    statuses = []
    for number in range(6):
        response = await async_client.post(
            "/auth/request-password-reset", json={"email": f"reset-{number}@example.com"}
        )
        statuses.append(response.status_code)
    assert statuses == [204] * 5 + [429]
    assert len(calls) == 5
