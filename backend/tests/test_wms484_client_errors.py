from __future__ import annotations

import json
import logging

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.services import client_error_service as service


@pytest.fixture(autouse=True)
def reset_client_error_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_counts", {})


@pytest_asyncio.fixture
async def auth(async_client: AsyncClient) -> tuple[dict[str, str], dict[str, str]]:
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Client errors", "slug": "client-errors",
        "admin_email": "client-errors@example.com", "password": "password123",
    })
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    return headers, me.json()


def records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == service.__name__]


def logged_payload(caplog: pytest.LogCaptureFixture) -> dict[str, str]:
    record = records(caplog)[-1]
    assert record.levelno == logging.ERROR
    text = record.getMessage()
    assert text.startswith("client error ")
    assert "\n" not in text  # one physical log line, even for a multiline stack
    result: dict[str, str] = json.loads(text.removeprefix("client error "))
    return result


async def test_report_204_and_log_identity(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers, me = auth
    body = {
        "message": "Не удалось удалить узел", "stack": "Error: removeChild\n at workspace:12",
        "url": "/app/ff/fbs", "screen": "fbs", "component": "workspace", "action": "react",
        "user_agent": "test-browser", "app_build": "client-abc.js",
    }
    response = await async_client.post("/client-errors", headers=headers, json=body)
    assert response.status_code == 204
    assert response.content == b""
    assert len(records(caplog)) == 1
    assert logged_payload(caplog) == {
        **body, "user_id": me["id"], "tenant_id": me["tenant_id"], "role": me["role"],
    }


async def test_long_fields_and_stack_are_trimmed(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = {name: "x" * (limit + 50) for name, limit in service.FIELD_LIMITS.items()}
    body["stack"] = "\n".join(f"frame {i}" for i in range(80))
    response = await async_client.post("/client-errors", headers=auth[0], json=body)
    assert response.status_code == 204
    data = logged_payload(caplog)
    for name, limit in service.FIELD_LIMITS.items():
        assert len(json.dumps(data[name], ensure_ascii=False).encode()) - 2 <= limit
    assert data["message"] == "x" * service.FIELD_LIMITS["message"]
    assert data["stack"].splitlines() == [f"frame {i}" for i in range(40)]
    assert len(records(caplog)[0].getMessage().encode()) < service.MAX_BODY_BYTES


async def test_oversized_body_keeps_truncated_first_field(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = json.dumps({"message": "я" * 100_000, "stack": "beyond limit"}, ensure_ascii=False)
    response = await async_client.post(
        "/client-errors", headers={**auth[0], "Content-Type": "application/json"},
        content=body.encode(),
    )
    assert response.status_code == 204
    data = logged_payload(caplog)
    assert data["message"] == "я" * 1000
    assert data["stack"] == ""
    assert len(records(caplog)[0].getMessage().encode()) < service.MAX_BODY_BYTES


async def test_unauthenticated_401(
    async_client: AsyncClient, caplog: pytest.LogCaptureFixture,
) -> None:
    response = await async_client.post("/client-errors", json={"message": "anonymous"})
    assert response.status_code == 401
    assert not records(caplog)


async def test_rate_limit_and_window_reset(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Replace this module's clock, not the event loop's time.monotonic.
    class Clock:
        now = 100.0

        @staticmethod
        def monotonic() -> float:
            return Clock.now

    monkeypatch.setattr(service, "time", Clock)
    for i in range(21):
        response = await async_client.post(
            "/client-errors", headers=auth[0], json={"message": str(i)},
        )
        assert response.status_code == 204
    assert len(records(caplog)) == 20
    Clock.now = 160.0
    response = await async_client.post("/client-errors", headers=auth[0], json={"message": "next"})
    assert response.status_code == 204
    assert len(records(caplog)) == 21
    assert logged_payload(caplog)["message"] == "next"


async def test_rate_limit_is_per_user(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    for _ in range(20):
        await async_client.post("/client-errors", headers=auth[0], json={"message": "first"})
    reg = await async_client.post("/auth/register", json={
        "organization_name": "Another", "slug": "another-client-errors",
        "admin_email": "another-client-errors@example.com", "password": "password123",
    })
    assert reg.status_code == 200
    response = await async_client.post("/client-errors", json={"message": "second"}, headers={
        "Authorization": f"Bearer {reg.json()['access_token']}",
    })
    assert response.status_code == 204
    assert len(records(caplog)) == 21
    assert logged_payload(caplog)["message"] == "second"


@pytest.mark.parametrize("body", [b"not-json", b"[]", b'{"message":null,"stack":{}}'])
async def test_malformed_input_never_500(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    body: bytes,
) -> None:
    response = await async_client.post("/client-errors", headers=auth[0], content=body)
    assert response.status_code == 204


async def test_logging_failure_never_500(
    async_client: AsyncClient,
    auth: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_log(*args: object, **kwargs: object) -> None:
        raise RuntimeError("log unavailable")

    monkeypatch.setattr(service.logger, "error", broken_log)
    response = await async_client.post("/client-errors", headers=auth[0], json={"message": "test"})
    assert response.status_code == 204
