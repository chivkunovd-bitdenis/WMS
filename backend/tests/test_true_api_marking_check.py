from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.product import Product
from app.models.seller_marking_credentials import SellerMarkingCredentials
from app.services import inbound_marking_service as receiving
from app.services import true_api_marking_check as api
from app.services.seller_marking_credentials_service import get_cz_token_for_seller
from tests.test_inbound_marking import CIS, _setup

CODES = [CIS, CIS.replace("SERIAL", "SECOND")]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"result": True, "quantity": 2}, [True, True]),
        ({"result": False, "quantity": 2}, [False, False]),
        ({"result": False, "codes": [CODES[1]]}, [True, False]),
        ({"result": False, "codes": [api.short_ki(CODES[1])]}, [True, False]),
        ({"result": True}, [None, None]),
        ({"result": 1, "quantity": 2}, [None, None]),
        ({"result": True, "quantity": 1}, [None, None]),
        ({"result": True, "quantity": True}, [None, None]),
        ({"result": False, "invalidcodes": [CODES[1]]}, [None, None]),
        ({"result": False, "codes": ["foreign"]}, [None, None]),
        ({"result": False, "codes": CODES}, [None, None]),
        ({"result": False, "codes": [CODES[1], CODES[1]]}, [None, None]),
        ({"result": False, "codes": [], "quantity": 2}, [None, None]),
    ],
)
def test_crypto_aggregate_requires_complete_unambiguous_answer(payload: Any, expected: Any) -> None:
    assert list(api.parse_crypto(payload, CODES).values()) == expected


def test_crypto_short_invalid_code_cannot_identify_two_different_signatures() -> None:
    codes = [CIS, CIS.replace("SIGNATURE", "OTHER")]
    assert list(
        api.parse_crypto({"result": False, "codes": [api.short_ki(CIS)]}, codes).values()
    ) == [None, None]


@pytest.mark.parametrize(
    ("outer", "verified", "status"),
    [
        ("INTRODUCED", True, "introduced"),
        ("INTRODUCED", None, "unavailable"),
        ("INTRODUCED", 1, "unavailable"),
        ("INTRODUCED", False, "problem"),
        (None, True, "unavailable"),
        ("FUTURE_STATUS", True, "unavailable"),
        ("RETIRED", True, "problem"),
        ("APPLIED", True, "problem"),
    ],
)
def test_status_and_crypto_are_separate_required_confirmations(
    outer: Any, verified: Any, status: str
) -> None:
    assert api.interpret({"cisInfo": {"status": outer}}, verified)["status"] == status


def test_info_reordering_duplicates_unknown_and_per_code_errors() -> None:
    short = [api.short_ki(code) for code in CODES]
    rows = [
        {"cisInfo": {"requestedCis": code, "cis": code, "status": "INTRODUCED"}} for code in short
    ]
    parsed = api.parse_info(list(reversed(rows)), short)
    assert parsed[short[0]] == rows[0]
    assert short[0] not in api.parse_info([*rows, rows[0]], short)
    assert (
        api.parse_info(
            {"cisInfo": {"requestedCis": short[0], "cis": "foreign", "status": "INTRODUCED"}}, short
        )
        == {}
    )
    assert api.interpret({**rows[0], "errorCode": "404"}, True)["status"] == "problem"
    assert api.interpret({**rows[0], "errorCode": "401"}, True)["status"] == "unavailable"
    assert (
        api.interpret({"cisInfo": {"status": "INTRODUCED", "ogvs": ["blocked"]}}, True)["status"]
        == "problem"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, 401, 429, 451, "offline", "malformed", "missing"])
async def test_http_short_info_full_crypto_and_truthful_unavailability(
    monkeypatch: pytest.MonkeyPatch,
    failure: Any,
) -> None:
    monkeypatch.setattr(api._PACING, "remaining_seconds", lambda _: 0.0)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-cz-only"
        assert request.url.host == "markirovka.crpt.ru"
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        if failure == "offline":
            raise httpx.ConnectError("offline", request=request)
        if type(failure) is int:
            return httpx.Response(failure)
        if failure == "malformed":
            return httpx.Response(200, content=b"not-json")
        if request.url.path.endswith("/info"):
            assert payload == [api.short_ki(code) for code in CODES]
            return httpx.Response(
                200,
                json=[]
                if failure == "missing"
                else [
                    {"cisInfo": {"requestedCis": code, "cis": code, "status": "INTRODUCED"}}
                    for code in reversed(payload)
                ],
            )
        assert payload == {"codes": CODES}  # Full cryptographic bytes and GS unchanged.
        return httpx.Response(200, json={"result": False, "codes": [CODES[1]]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await api.check_batch(client, CODES, "test-cz-only")
    assert [result[code]["status"] for code in CODES] == (
        ["introduced", "problem"] if failure is None else ["unavailable", "unavailable"]
    )
    assert len(calls) == (2 if failure in (None, "missing") else 1)


@pytest.mark.asyncio
async def test_missing_token_or_unprojectable_code_never_calls_http() -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("No HTTP without configured token / GS boundary")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        assert (await api.check_batch(client, [CIS], None))[CIS]["status"] == "unavailable"
        short = CIS.split("\x1d")[0]
        assert (await api.check_batch(client, [short], "test"))[short]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_pacing_reserves_two_seconds_between_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    calls = []
    monkeypatch.setattr(api._PACING, "_blocked_until", {})
    monkeypatch.setattr(api._PACING, "now", lambda: clock[0])

    async def sleep(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr(api.asyncio, "sleep", sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(clock[0])
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await api._post(client, "/cises/info", "test", [])
        await api._post(client, "/cises/check", "test", {"codes": []})
        await api._post(client, "/cises/info", "test", [])
    assert calls == [0.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_credential_scope_and_only_cz_is_decrypted(async_client: httpx.AsyncClient) -> None:
    tenant, _, _, _ = await _setup(async_client)
    async with SessionLocal() as session:
        product = await session.scalar(select(Product).where(Product.tenant_id == tenant))
        seller = product.seller_id
        row = await session.get(SellerMarkingCredentials, seller)
        row.suz_oms_token_enc = "invalid-encrypted-OMS-must-not-be-decrypted"
        row.mp_api_key_enc = "invalid-encrypted-MP-must-not-be-decrypted"
        await session.commit()
        assert await get_cz_token_for_seller(session, tenant, seller) == "test-cz-token"
        assert await get_cz_token_for_seller(session, uuid.uuid4(), seller) is None
        assert await get_cz_token_for_seller(session, tenant, uuid.uuid4()) is None
        row.cz_token_enc = "unreadable"
        await session.commit()
        assert await get_cz_token_for_seller(session, tenant, seller) is None


@pytest.mark.asyncio
async def test_receiving_batches_two_pending_codes_and_preserves_full_values(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api._PACING, "remaining_seconds", lambda _: 0.0)
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        for code in CODES:
            await receiving.attach_code(
                session, tenant, req, line_id=line, cis_code=code, actor_user_id=user
            )
        job = await receiving.schedule_check(session, tenant, req)
    calls = []

    async def fake_post(_client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        assert kwargs["headers"]["Authorization"] == "Bearer test-cz-token"
        body = kwargs["json"]
        if url.endswith("/info"):
            assert set(body) == {api.short_ki(code) for code in CODES}
            data: Any = [
                {"cisInfo": {"requestedCis": code, "cis": code, "status": "INTRODUCED"}}
                for code in body
            ]
        else:
            assert set(body["codes"]) == set(CODES)
            data = {"result": True, "quantity": 2}
        return httpx.Response(200, request=httpx.Request("POST", url), json=data)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert job is not None
    await receiving.run_check_job(job)
    assert calls == [api.BASE_URL + "/cises/info", api.BASE_URL + "/cises/check"]
    async with SessionLocal() as session:
        listed = await receiving.list_codes(session, tenant, req)
        assert not listed["checking"]
        assert {item["cis_code"] for item in listed["items"]} == set(CODES)
        assert all(item["cz_status"] == "introduced" for item in listed["items"])


@pytest.mark.asyncio
async def test_expired_worker_cannot_overwrite_retry_while_saving_response(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SessionLocal() as session:
        if session.bind is None or session.bind.dialect.name != "postgresql":
            pytest.skip("Requires PostgreSQL row locks")
    tenant, user, req, line = await _setup(async_client)
    async with SessionLocal() as session:
        await receiving.attach_code(
            session, tenant, req, line_id=line, cis_code=CIS, actor_user_id=user
        )
        old_id = await receiving.schedule_check(session, tenant, req)
        old = await session.get(BackgroundJob, old_id)
        old.created_at = datetime.now(UTC) - timedelta(days=1)
        await session.commit()
    response_ready = asyncio.Event()
    release_response = asyncio.Event()
    retry_prepared = asyncio.Event()
    release_retry_commit = asyncio.Event()
    calls = []

    async def check_batch(_client: Any, codes: list[str], _token: str | None) -> Any:
        calls.append(codes)
        if len(calls) == 1:
            response_ready.set()
            await release_response.wait()
            return {CIS: {**api.unavailable(), "status": "introduced", "reason": "old response"}}
        return {CIS: {**api.unavailable(), "status": "problem", "reason": "fresh retry response"}}

    monkeypatch.setattr(api, "check_batch", check_batch)
    old_task = asyncio.create_task(receiving.run_check_job(old_id))
    retry_task = None
    try:
        await asyncio.wait_for(response_ready.wait(), 5)
        async with SessionLocal() as retry_session:
            real_commit = AsyncSession.commit

            async def pause_retry_commit(self: AsyncSession) -> None:
                if self is retry_session:
                    # Real schedule_check already holds the receipt row. Flush its
                    # replacement job and pending snapshot, but pause before commit.
                    await self.flush()
                    retry_prepared.set()
                    await release_retry_commit.wait()
                await real_commit(self)

            monkeypatch.setattr(AsyncSession, "commit", pause_retry_commit)
            retry_task = asyncio.create_task(
                receiving.schedule_check(retry_session, tenant, req, force=True)
            )
            await asyncio.wait_for(retry_prepared.wait(), 5)
            release_response.set()
            # Old code waits on the event after caching running; fixed code waits
            # on the receipt before rereading the job. Both are actual PG waits.
            async with SessionLocal() as observer:
                for _ in range(250):
                    waiting = await observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                            "AND wait_event_type='Lock'"
                        )
                    )
                    await observer.rollback()
                    if waiting:
                        break
                    assert not old_task.done(), (
                        "Worker did not wait for the replacement transaction"
                    )
                    await asyncio.sleep(0.02)
                else:
                    pytest.fail("Worker never reached a PostgreSQL row-lock wait")
            release_retry_commit.set()
            new_id = await asyncio.wait_for(retry_task, 5)
            assert new_id is not None and new_id != old_id
        await asyncio.wait_for(old_task, 5)
        async with SessionLocal() as session:
            assert (await session.get(BackgroundJob, old_id)).status == "failed"
            assert (await session.get(BackgroundJob, new_id)).status == "pending"
            listed = await receiving.list_codes(session, tenant, req)
            assert listed["items"][0]["cz_status"] == "pending"
        await receiving.run_check_job(new_id)
        assert calls == [[CIS], [CIS]]
        async with SessionLocal() as session:
            listed = await receiving.list_codes(session, tenant, req)
            assert listed["items"][0]["cz_reason"] == "fresh retry response"
            assert not listed["checking"]
    finally:
        release_response.set()
        release_retry_commit.set()
        tasks = [old_task, *([retry_task] if retry_task is not None else [])]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
