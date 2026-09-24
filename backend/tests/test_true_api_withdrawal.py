from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import tempfile
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import true_api_withdrawal as api

FIXTURES = json.loads((Path(__file__).parent / "fixtures/true_api_v731.json").read_text())
INN = "0000000000"
TOKEN = FIXTURES["auth_uuid"]["uuidToken"]
DOC_ID = FIXTURES["document_info_error"][0]["number"]
CIS = "010460000000000021LLLLLLLLLLLLL"
SIGNATURE = base64.b64encode(b"test-signature-bytes").decode()
EXACT = (
    f'{{ "inn": "0000000000", "action": "DISTANCE", "action_date": "{api._moscow_today()}", '
    '"products": [{"cis": "010460000000000021LLLLLLLLLLLLL", "product_cost": 12345}] }\n'
).encode()


class RecordingLimiter:
    """Test-only limiter; production has no bypass/default limiter."""

    def __init__(self) -> None:
        self.calls: list[tuple[api.Environment, str]] = []

    async def acquire(self, environment: api.Environment, participant_inn: str) -> None:
        self.calls.append((environment, participant_inn))


def session(**overrides: Any) -> api.AuthSession:
    values = dict(
        environment=api.Environment.SANDBOX,
        participant_inn=INN,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        token=TOKEN,
    )
    values.update(overrides)
    return api.AuthSession(**values)


def client(http: httpx.AsyncClient, limiter: Any = None) -> api.TrueApiWithdrawalClient:
    return api.TrueApiWithdrawalClient(
        http,
        # Mock transport exercises the contract, never a physical certificate.
        api.TrueApiConfig(api.Environment.SANDBOX),
        limiter or RecordingLimiter(),
        INN,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("certificate_hours", [2, 12])
async def test_exact_auth_contract_uuid_field_expiry_and_no_secret_repr(
    certificate_hours: int,
) -> None:
    calls = []
    limiter = RecordingLimiter()
    now = datetime.now(UTC)
    cert_expiry = now + timedelta(hours=certificate_hours)
    payload = {**FIXTURES["auth_uuid"], "expireDate": (now + timedelta(hours=15)).isoformat()}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "markirovka.sandbox.crptech.ru"
        assert "Authorization" not in request.headers
        if request.method == "GET":
            assert request.url.path == "/api/v3/true-api/auth/key"
            return httpx.Response(200, json=FIXTURES["auth_key"])
        assert request.url.path == "/api/v3/true-api/auth/simpleSignIn"
        expected = dict(
            uuid=FIXTURES["auth_key"]["uuid"], data=SIGNATURE, unitedToken=True, inn=INN
        )
        assert json.loads(request.content) == expected
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        transport = client(http, limiter)
        challenge = await transport.challenge()
        assert challenge.data == FIXTURES["auth_key"]["data"]
        assert challenge.data not in repr(challenge)
        auth = await transport.sign_in(
            challenge.uuid,
            SIGNATURE,
            certificate_expires_at=cert_expiry,
        )
    assert auth.token == TOKEN
    assert TOKEN not in repr(auth)
    if certificate_hours == 2:
        assert auth.expires_at == cert_expiry
    else:
        assert now + timedelta(hours=10) <= auth.expires_at < now + timedelta(hours=10, seconds=1)
    assert len(calls) == len(limiter.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{"token": TOKEN}, {"uuidToken": "jwt", "expireDate": "bad"}])
async def test_auth_does_not_accept_legacy_token_or_leak_auth_body(response: Any) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as http:
        with pytest.raises(api.TrueApiError) as exc:
            await client(http).sign_in(
                FIXTURES["auth_key"]["uuid"],
                SIGNATURE,
                certificate_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
    assert exc.value.response_body == b""
    assert TOKEN not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("as_json", [True, False])
@pytest.mark.parametrize("status", [200, 201])
async def test_create_sends_original_bytes_exact_four_fields_and_returns_only_id(
    as_json: bool,
    status: int,
) -> None:
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == (
            "https://markirovka.sandbox.crptech.ru/api/v3/true-api/lk/documents/create?pg=lp"
        )
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        data = json.loads(request.content)
        assert data == {
            "document_format": "MANUAL",
            "type": "LK_RECEIPT",
            "signature": SIGNATURE,
            "product_document": base64.b64encode(EXACT).decode(),
        }
        assert base64.b64decode(data["product_document"]) == EXACT
        assert "Idempotency-Key" not in request.headers
        return (
            httpx.Response(status, json=DOC_ID) if as_json else httpx.Response(status, text=DOC_ID)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert (
            await client(http, limiter).create_document(
                session(), pg="lp", exact_payload=EXACT, detached_signature=SIGNATURE
            )
            == DOC_ID
        )
    assert limiter.calls == [(api.Environment.SANDBOX, INN)]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403, 422, 429, 500, 502, 503, 302])
async def test_create_preserves_error_bytes_and_never_retries_or_redirects(status: int) -> None:
    calls = []
    body = json.dumps(FIXTURES["create_error"], ensure_ascii=False).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, content=body, headers={"Location": "/another-create"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as http:
        with pytest.raises(api.TrueApiError) as exc:
            await client(http).create_document(
                session(), pg="lp", exact_payload=EXACT, detached_signature=SIGNATURE
            )
    assert len(calls) == 1
    assert exc.value.response_body == body
    assert exc.value.status_code == status
    assert exc.value.create_outcome == (
        api.CreateOutcome.DEFINITE_REJECT
        if status in {400, 401, 403, 422}
        else api.CreateOutcome.UNCERTAIN
    )
    assert TOKEN not in str(exc.value)
    assert "signature" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "disconnect", "connect", "bad_json", "fake_id"])
async def test_uncertain_create_never_performs_second_post(failure: str) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret request", request=request)
        if failure == "disconnect":
            raise httpx.RemoteProtocolError("secret request", request=request)
        if failure == "connect":
            raise httpx.ConnectError("secret request", request=request)
        return httpx.Response(200, text="garbage" if failure == "bad_json" else '{"id":"fake"}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(api.TrueApiError) as exc:
            await client(http).create_document(
                session(), pg="lp", exact_payload=EXACT, detached_signature=SIGNATURE
            )
    assert len(calls) == 1
    assert exc.value.create_outcome == api.CreateOutcome.UNCERTAIN
    assert "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_cises_official_batch_preserves_nullable_facts_and_per_code_errors() -> None:
    good = deepcopy(FIXTURES["cises_info"][0])
    good["cisInfo"].update(requestedCis=CIS, cis=CIS, ownerInn=INN)
    bad_code = CIS + "2"
    bad = deepcopy(FIXTURES["cises_not_found"][0])
    bad["cisInfo"].update(requestedCis=bad_code, cis=bad_code)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/v3/true-api/cises/info")
        assert json.loads(request.content) == [CIS, bad_code]
        return httpx.Response(200, json=[bad, good])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        response = await client(http).cises_info(session(), [CIS, bad_code])
    assert response.unresolved == ()
    assert response.by_cis[CIS].product_group == "milk"
    assert response.by_cis[CIS].product_group_id == 8
    assert response.by_cis[CIS].owner_inn == INN
    assert response.by_cis[CIS].status_ex is None
    assert response.by_cis[bad_code].product_group is None
    assert response.by_cis[bad_code].error_message == "КИ не найден"
    assert response.by_cis[bad_code].error_code == "404"
    assert response.raw == [bad, good]
    assert api.parse_cises([good, good, bad], [CIS, bad_code]).unresolved == (CIS,)


@pytest.mark.asyncio
async def test_cises_404_is_a_per_code_answer_not_transport_exception() -> None:
    rows = deepcopy(FIXTURES["cises_not_found"])
    rows[0]["cisInfo"].update(requestedCis=CIS, cis=CIS)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, json=rows))
    ) as http:
        answer = await client(http).cises_info(session(), [CIS])
    assert answer.by_cis[CIS].error_message == "КИ не найден"
    assert answer.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,outcome",
    [
        ("CHECKED_OK", "succeeded"),
        ("CHECKED_NOT_OK", "failed"),
        ("PARSE_ERROR", "failed"),
        ("PROCESSING_ERROR", "failed"),
        ("IN_PROGRESS", "pending"),
        ("WAIT_FOR_CONTINUATION", "pending"),
        ("UNDEFINED", "unknown"),
        ("ACCEPTED", "unknown"),
        ("NEW_STATUS", "unknown"),
        (None, "unknown"),
    ],
)
async def test_v4_info_array_exact_query_errors_and_withdrawal_statuses(
    status: str | None,
    outcome: str,
) -> None:
    data = deepcopy(FIXTURES["document_info_error"])
    data[0].update(type="LK_RECEIPT", status=status, body=json.loads(EXACT))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            f"https://markirovka.sandbox.crptech.ru/api/v4/true-api/doc/{DOC_ID}/info?pg=lp&body=true"
        )
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await client(http).document_info(session(), pg="lp", document_id=DOC_ID)
    assert result.outcome == outcome
    assert result.body == json.loads(EXACT)
    assert result.errors == data[0]["errors"]
    assert result.common_errors == data[0]["commonErrors"]
    assert result.raw == data[0]


@pytest.mark.asyncio
async def test_v4_list_exact_reconciliation_filters_and_cursor() -> None:
    data = deepcopy(FIXTURES["document_list"])
    calls = []
    now = datetime(2026, 9, 23, 10, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.path == "/api/v4/true-api/doc/list"
        params = dict(request.url.params)
        expected = {
            "pg": "lp",
            "dateFrom": "2026-09-23T10:00:00.000Z",
            "dateTo": "2026-09-23T10:05:00.000Z",
            "senderInn": INN,
            "documentType": "LK_RECEIPT",
            "documentFormat": "MANUAL",
            "limit": "1000",
            "order": "ASC",
        }
        if len(calls) == 2:
            expected.update(
                did=data["results"][0]["number"],
                orderedColumnValue=data["results"][0]["docDate"],
                pageDir="NEXT",
            )
        assert params == expected
        return httpx.Response(
            200, json=data if len(calls) == 1 else {"results": [], "nextPage": False}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        transport = client(http)
        page = await transport.list_documents(
            session(), pg="lp", date_from=now, date_to=now + timedelta(minutes=5)
        )
        assert page.next_cursor == api.DocumentCursor(
            data["results"][0]["number"], data["results"][0]["docDate"]
        )
        last = await transport.list_documents(
            session(),
            pg="lp",
            date_from=now,
            date_to=now + timedelta(minutes=5),
            cursor=page.next_cursor,
        )
        assert not last.next_page
        assert not last.results


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "auth",
    [
        session(environment=api.Environment.PRODUCTION),
        session(participant_inn="1111111111"),
        session(expires_at=datetime(2000, 1, 1, tzinfo=UTC)),
        session(token="legacy-jwt"),
    ],
)
async def test_cross_environment_participant_expired_or_jwt_auth_never_leaves_server(
    auth: api.AuthSession,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid session must not reach HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError):
            await client(http).document_info(auth, pg="lp", document_id=DOC_ID)


@pytest.mark.asyncio
async def test_limiter_failure_prevents_outbound_and_does_not_fallback() -> None:
    class BrokenRedis:
        async def eval(self, *_: Any) -> Any:
            raise ConnectionError("Redis unavailable")

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Limiter failure must not reach HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ConnectionError):
            await client(http, api.RedisParticipantLimiter(BrokenRedis())).challenge()


@pytest.mark.asyncio
async def test_limiter_waits_then_reacquires_same_participant_key(monkeypatch: Any) -> None:
    calls = []
    sleeps = []

    class ScriptRedis:
        async def eval(self, script: str, numkeys: int, *keys: str) -> int:
            calls.append((script, numkeys, keys))
            return 15000 if len(calls) == 1 else 0

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(api.asyncio, "sleep", sleep)
    await api.RedisParticipantLimiter(ScriptRedis()).acquire(api.Environment.SANDBOX, INN)
    assert sleeps == [0.015]
    assert len(calls) == 2
    assert calls[0][1:] == (1, (f"wms:true-api:rate:sandbox:{INN}",))
    assert calls[0] == calls[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("violation", ["count", "bytes", "duplicate", "signature"])
async def test_create_boundary_failures_happen_before_http(
    violation: str, monkeypatch: Any
) -> None:
    payload = EXACT
    signature = SIGNATURE
    if violation == "count":
        monkeypatch.setattr(api, "MAX_DOCUMENT_CISES", 0)
    elif violation == "bytes":
        monkeypatch.setattr(api, "MAX_DOCUMENT_BYTES", len(EXACT) - 1)
    elif violation == "duplicate":
        data = json.loads(EXACT)
        data["products"] *= 2
        payload = json.dumps(data).encode()
    else:
        signature += "\n"

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid document must not reach HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError):
            await client(http).create_document(
                session(), pg="lp", exact_payload=payload, detached_signature=signature
            )


def test_environment_selects_an_inseparable_pair_of_official_urls() -> None:
    prod = api.TrueApiConfig(api.Environment.PRODUCTION)
    assert prod.base_url(3) == "https://markirovka.crpt.ru/api/v3/true-api"
    assert prod.base_url(4) == "https://markirovka.crpt.ru/api/v4/true-api"
    with pytest.raises(ValueError):
        api.TrueApiConfig("invented")


def test_document_from_different_type_cannot_succeed() -> None:
    row = {"type": "LP_SHIP_GOODS"}
    assert api.DocumentInfo(DOC_ID, "CHECKED_OK", {}, None, None, row).outcome == "unknown"


@pytest.mark.asyncio
async def test_atomic_lua_limiter_across_three_clients_with_real_isolated_redis() -> None:
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("redis-server required for distributed limiter integration check")
    # An isolated server with no persistence or TCP listener; never use app Redis.
    with tempfile.TemporaryDirectory(prefix="wms517-redis-", dir="/tmp") as folder:
        socket = str(Path(folder) / "redis.sock")
        process = subprocess.Popen(
            [
                executable,
                "--port",
                "0",
                "--unixsocket",
                socket,
                "--save",
                "",
                "--appendonly",
                "no",
                "--loglevel",
                "warning",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        connections = [Redis(unix_socket_path=socket) for _ in range(3)]
        grants: list[int] = []

        class ObservedRedis:
            def __init__(self, connection: Any) -> None:
                self.connection = connection

            async def eval(self, script: str, numkeys: int, *keys: str) -> int:
                # Return server time alongside the unmodified atomic decision to
                # measure grants without network/scheduler timing noise.
                observed = script.replace("return wait end", "return {wait, now} end")
                observed = observed.replace("return 0", "return {0, now}")
                delay, server_time = await self.connection.eval(observed, numkeys, *keys)
                if delay == 0:
                    grants.append(server_time)
                return int(delay)

        try:
            for _ in range(200):
                try:
                    await connections[0].ping()
                    break
                except RedisConnectionError:
                    await asyncio.sleep(0.01)
            else:
                pytest.fail("Isolated Redis did not start")
            limiters = [api.RedisParticipantLimiter(ObservedRedis(conn)) for conn in connections]
            await asyncio.gather(
                *[limiters[index % 3].acquire(api.Environment.SANDBOX, INN) for index in range(75)]
            )
            times = sorted(grants)
            assert len(times) == 75
            assert all(b - a >= 20001 for a, b in pairwise(times))
            assert all(times[i + 50] - times[i] > 1_000_000 for i in range(25))
            # Retry-After on one client defers another process's same participant.
            await api.RedisParticipantLimiter(connections[0]).defer(
                api.Environment.SANDBOX, INN, 0.1
            )
            started = asyncio.get_running_loop().time()
            await api.RedisParticipantLimiter(connections[1]).acquire(api.Environment.SANDBOX, INN)
            assert asyncio.get_running_loop().time() - started >= 0.1
        finally:
            for connection in connections:
                await connection.aclose()
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [30_000, 30_001])
async def test_actual_document_code_count_boundary(count: int) -> None:
    data = json.loads(EXACT)
    data["products"] = [{"cis": f"{CIS}{i}", "product_cost": 12345} for i in range(count)]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, text=DOC_ID)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        action = client(http).create_document(
            session(),
            pg="lp",
            exact_payload=json.dumps(data).encode(),
            detached_signature=SIGNATURE,
        )
        if count == 30_000:
            assert await action == DOC_ID
            assert len(calls) == 1
        else:
            with pytest.raises(ValueError):
                await action
            assert not calls


@pytest.mark.parametrize(
    "change",
    [
        {"ownerInn": "1111111111"},
        {"productGroup": None},
        {"productGroupId": None},
        {"status": "RETIRED"},
        {"ogvs": ["RSHN"]},
        {"statusEx": "BLOCKED"},
    ],
)
def test_cis_parser_never_discards_facts_required_by_business_preflight(change: Any) -> None:
    row = deepcopy(FIXTURES["cises_info"][0])
    row["cisInfo"].update(requestedCis=CIS, cis=CIS, **change)
    parsed = api.parse_cises([row], [CIS])
    assert parsed.by_cis[CIS].raw == row


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["wrong_id", "wrong_group", "object", "multiple"])
async def test_info_contract_mismatch_is_not_success(mutation: str) -> None:
    rows = deepcopy(FIXTURES["document_info_error"])
    if mutation == "wrong_id":
        rows[0]["number"] = "00000000-0000-0000-0000-000000000000"
    elif mutation == "wrong_group":
        rows[0]["productGroup"] = ["milk"]
    elif mutation == "object":
        rows = rows[0]
    else:
        rows *= 2
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=rows))
    ) as http:
        with pytest.raises(api.TrueApiError) as exc:
            await client(http).document_info(session(), pg="lp", document_id=DOC_ID)
    assert exc.value.reason == "invalid_contract"


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", list(api.Environment))
@pytest.mark.parametrize("method", ["sign_in", "create_document"])
@pytest.mark.parametrize("verified", [False, True])
async def test_production_create_gate_does_not_block_auth_or_sandbox(
    environment: api.Environment,
    method: str,
    verified: bool,
) -> None:
    calls = []
    limiter = RecordingLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if method == "create_document":
            return httpx.Response(201, text=DOC_ID)
        return httpx.Response(
            200,
            json={
                **FIXTURES["auth_uuid"],
                "expireDate": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )

    # Omitting the field must be fail-closed by default, not only explicit False.
    config = (
        api.TrueApiConfig(environment, production_submit_enabled=True)
        if verified
        else api.TrueApiConfig(environment)
    )
    assert config.production_submit_enabled is verified
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        transport = api.TrueApiWithdrawalClient(http, config, limiter, INN)
        if method == "sign_in":
            action = transport.sign_in(
                FIXTURES["auth_key"]["uuid"],
                SIGNATURE,
                certificate_expires_at=datetime.now(UTC) + timedelta(hours=2),
            )
        else:
            action = transport.create_document(
                session(environment=environment),
                pg="lp",
                exact_payload=EXACT,
                detached_signature=SIGNATURE,
            )
        if verified or environment == api.Environment.SANDBOX or method == "sign_in":
            await action
            assert len(calls) == len(limiter.calls) == 1
        else:
            with pytest.raises(ValueError, match="WITHDRAWAL_PRODUCTION_SUBMIT_DISABLED"):
                await action
            assert calls == []
            assert limiter.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        None,
        20260923,
        True,
        "",
        "20260923",
        "2026-9-23",
        "2026-02-30",
        "2026-09-23T00:00:00Z",
        "2026-09-24",
        "2021-09-22",
    ],
)
async def test_invalid_or_missing_action_date_rejected_before_limiter_and_http(
    value: Any,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(api, "_moscow_today", lambda: date(2026, 9, 23))
    data = json.loads(EXACT)
    if value is None:
        del data["action_date"]
    else:
        data["action_date"] = value
    limiter = RecordingLimiter()

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid action_date must not reach HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="action_date"):
            await client(http, limiter).create_document(
                session(),
                pg="lp",
                exact_payload=json.dumps(data).encode(),
                detached_signature=SIGNATURE,
            )
    assert limiter.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "product",
    [
        None,
        [],
        "invalid",
        1,
        {},
        {"cis": CIS},
        {"cis": None, "product_cost": 0},
        {"cis": CIS, "product_cost": None},
        {"cis": CIS, "product_cost": True},
        {"cis": CIS, "product_cost": 12.5},
        {"cis": CIS, "product_cost": "1250"},
        {"cis": CIS, "product_cost": -1},
        {"cis": CIS, "product_cost": 100_000_000_000_000_000},
    ],
)
async def test_malformed_product_rows_or_invalid_cost_rejected_before_http(product: Any) -> None:
    data = json.loads(EXACT)
    data["products"] = [product]
    limiter = RecordingLimiter()

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid product must not reach HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError):
            await client(http, limiter).create_document(
                session(),
                pg="lp",
                exact_payload=json.dumps(data).encode(),
                detached_signature=SIGNATURE,
            )
    assert limiter.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("cost", [0, 99_999_999_999_999_999])
@pytest.mark.parametrize("action_date", ["2021-09-23", "2026-09-23"])
async def test_inclusive_date_and_cost_boundaries_preserve_original_payload_bytes(
    cost: int,
    action_date: str,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(api, "_moscow_today", lambda: date(2026, 9, 23))
    data = json.loads(EXACT)
    data["action_date"] = action_date
    data["products"][0]["product_cost"] = cost
    original = (json.dumps(data, indent=3) + "\n\n").encode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert base64.b64decode(json.loads(request.content)["product_document"]) == original
        return httpx.Response(201, text=DOC_ID)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert (
            await client(http).create_document(
                session(), pg="lp", exact_payload=original, detached_signature=SIGNATURE
            )
            == DOC_ID
        )


def test_five_calendar_year_boundary_on_leap_day(monkeypatch: Any) -> None:
    monkeypatch.setattr(api, "_moscow_today", lambda: date(2024, 2, 29))
    api._validate_action_date("2019-02-28")
    api._validate_action_date("2024-02-29")
    with pytest.raises(ValueError):
        api._validate_action_date("2019-02-27")


def test_action_date_uses_moscow_calendar_at_utc_day_boundary(monkeypatch: Any) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return datetime(2026, 9, 23, 21, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(api, "datetime", FixedDatetime)
    assert api._moscow_today() == date(2026, 9, 24)
    api._validate_action_date("2026-09-24")
    with pytest.raises(ValueError):
        api._validate_action_date("2026-09-25")
