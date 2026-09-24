"""Narrow regression coverage for the four WMS-517 review findings."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from test_withdrawal_ledger import document, info  # type: ignore[import-not-found]

from app.api.marking_withdrawals import router
from app.core.settings import settings
from app.db.withdrawal_repository import current_items
from app.models.base import Base
from app.services.true_api_withdrawal import (
    AuthSession,
    Environment,
    TrueApiConfig,
    TrueApiError,
    TrueApiWithdrawalClient,
)
from app.services.withdrawal_recovery import apply_recovery, claim_work
from app.tasks import withdrawal_recovery as worker


@pytest.mark.asyncio
async def test_b3_closes_worker_before_any_provider_resources(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await document(db_session)  # Persisted, due provider document cannot bypass B3.
    monkeypatch.setattr(settings, "withdrawal_browser_auth_profile_verified", False)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("B3 must stop before DB leases/Redis/limiter/HTTP/recovery")

    monkeypatch.setattr(worker, "SessionLocal", forbidden)
    monkeypatch.setattr(Redis, "from_url", forbidden)
    monkeypatch.setattr(worker, "RedisParticipantLimiter", forbidden)
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(worker, "TrueApiWithdrawalClient", forbidden)
    monkeypatch.setattr(worker, "recover_one", forbidden)
    monkeypatch.setattr(worker, "submit_one", forbidden)
    assert await worker.run_withdrawal_recovery() == 0
    assert await worker.run_withdrawal_jobs() == 0


def test_no_persistent_mod_registry_or_api() -> None:
    assert not any("withdrawal_mod" in name for name in Base.metadata.tables)
    assert not any("/mods" in getattr(route, "path", "") for route in router.routes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "errors,common,code,message",
    [
        ([{"code": "E42", "error": "Фактическая ошибка"}], None, "E42", "Фактическая ошибка"),
        (
            [],
            [{"errorCode": "INTRO_ERROR", "errorMessage": "Ошибка ЧЗ"}],
            "INTRO_ERROR",
            "Ошибка ЧЗ",
        ),
        ({"errors": [{"code": 29, "message": "Неверный JSON"}]}, None, "29", "Неверный JSON"),
    ],
)
async def test_terminal_reject_projects_provider_fields_and_preserves_raw(
    db_session: AsyncSession,
    errors: Any,
    common: Any,
    code: str,
    message: str,
) -> None:
    scope, operation, doc = await document(db_session)
    work = await claim_work(db_session)
    assert work is not None
    result = replace(info(doc, "CHECKED_NOT_OK"), errors=errors, common_errors=common)
    await apply_recovery(db_session, work, info=result)
    items = await current_items(db_session, scope, operation.id)
    assert items
    for item in items:
        assert item.state == "failed"
        assert item.error is not None
        assert item.error["code"] == code and item.error["message"] == message
        assert item.error["errors"] == errors and item.error["commonErrors"] == common


class FixtureLimiter:
    async def acquire(self, environment: Environment, participant_inn: str) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pages,valid",
    [
        ([{"result": [], "total": 0, "nextPage": False}], True),
        (
            [
                {"result": [{}], "total": 2, "nextPage": True},
                {"result": [{"inn": "another"}], "total": 2, "nextPage": False},
            ],
            True,
        ),
        ([{"result": [{}], "total": 2, "nextPage": False}], False),
        ([{"result": [{}], "total": 0, "nextPage": False}], False),
        (
            [
                {"result": [{}], "total": 2, "nextPage": True},
                {"result": [{}], "total": 3, "nextPage": False},
            ],
            False,
        ),
        ([{"result": [], "total": 2, "nextPage": True}], False),
        ([{"result": [{}], "total": 1, "nextPage": True}], False),
        ([{"result": [], "total": -1, "nextPage": False}], False),
    ],
)
async def test_mod_pages_require_stable_exact_total(
    pages: list[dict[str, Any]],
    valid: bool,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.url.path.endswith("/mods/list")
        assert request.url.params["page"] == str(calls)
        response = pages[calls]
        calls += 1
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TrueApiWithdrawalClient(
            http, TrueApiConfig(Environment.SANDBOX), FixtureLimiter(), "7701234567"
        )
        auth = AuthSession(
            Environment.SANDBOX,
            "7701234567",
            datetime.now(UTC) + timedelta(hours=1),
            str(uuid.uuid4()),
        )
        if valid:
            assert await client.registered_mods(auth, pg="lp") == [
                row for page in pages for row in page["result"]
            ]
        else:
            with pytest.raises(TrueApiError):
                await client.registered_mods(auth, pg="lp")
    assert calls == len(pages)
