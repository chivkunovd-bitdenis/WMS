from __future__ import annotations

import copy
import json
from typing import Any

import httpx
import pytest

from app.services import public_marking_check as check

# Sanitized semantic fields from the 08.09 Claude tool stdout, line 1303 in
# c00aad3b-56f1-4fb8-808c-5a3d18b0bbb8.jsonl. It logged these fields, not full JSON.
# No real scanned code, product, company or invented provider fields are included.
APPLIED = {
    "outerStatus": "APPLIED", "checkResult": False, "status": "wrong", "warning": "ok",
    "codeResolveData": {"verified": True},
}
INTRODUCED = {
    "outerStatus": "INTRODUCED", "checkResult": True, "status": "ok", "warning": "ok",
    "codeResolveData": {"verified": True},
}
FULL_QA_CODE = "010460123456789021SYNTHETIC\x1d91KEY1\x1d92QA+/="


@pytest.mark.parametrize("payload,expected", [(APPLIED, "problem"), (INTRODUCED, "introduced")])
def test_recorded_semantic_response_fields(payload: dict[str, Any], expected: str) -> None:
    result = check.interpret_check(payload)
    assert result["status"] == expected
    assert result["raw_response"] == payload
    assert result["outer_status"] == payload["outerStatus"]


@pytest.mark.parametrize("field,value", [
    ("checkResult", "true"), ("checkResult", 1), ("checkResult", None),
    ("checkResult", False), ("outerStatus", []), ("outerStatus", "UNKNOWN"),
    ("codeFounded", "true"), ("status", "wrong"), ("warning", "not_verified"),
])
def test_malformed_or_nonpositive_result_never_turns_green(field: str, value: Any) -> None:
    payload = copy.deepcopy(INTRODUCED)
    payload[field] = value
    assert check.interpret_check(payload)["status"] == "unavailable"


@pytest.mark.parametrize("field,value", [
    ("verified", "true"), ("verified", 1), ("verified", None),
    ("isBlocked", "false"), ("isBlocked", 0), ("isBlocked", None),
])
def test_malformed_resolved_flags_are_unknown(field: str, value: Any) -> None:
    payload = copy.deepcopy(INTRODUCED)
    payload["codeResolveData"][field] = value
    assert check.interpret_check(payload)["status"] == "unavailable"


@pytest.mark.parametrize("payload", [None, [], "bad", {}, {"codeResolveData": []},
                                       {"outerStatus": "INTRODUCED", "checkResult": True}])
def test_missing_evidence_is_unknown(payload: Any) -> None:
    assert check.interpret_check(payload)["status"] == "unavailable"


@pytest.mark.parametrize("kind,reason", [
    ("not_found", "не найден"), ("unverified", "Криптоподпись"), ("blocked", "заблокирован"),
])
def test_explicit_negative_results(kind: str, reason: str) -> None:
    payload = copy.deepcopy(INTRODUCED)
    if kind == "not_found":
        payload["codeFounded"] = False
    else:
        payload["codeResolveData"]["verified" if kind == "unverified" else "isBlocked"] = (
            kind == "blocked"
        )
    result = check.interpret_check(payload)
    assert result["status"] == "problem" and reason in result["reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,expected", [
    (200, json.dumps(INTRODUCED), "introduced"),
    (200, "not-json", "unavailable"),
    (451, "", "unavailable"),
    (401, "denied", "unavailable"),
    (429, "rate limit", "unavailable"),
    (503, json.dumps(INTRODUCED), "unavailable"),
])
async def test_no_token_full_gs_request_and_raw_response(
    monkeypatch: pytest.MonkeyPatch, status: int, body: str, expected: str,
) -> None:
    monkeypatch.setattr(check._PACING, "remaining_seconds", lambda _: 0.0)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST" and str(request.url) == check.CHECK_URL
        assert json.loads(request.content) == {"code": FULL_QA_CODE}
        assert "authorization" not in request.headers and "x-api-key" not in request.headers
        return httpx.Response(status, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await check.check_code(client, FULL_QA_CODE)
    assert len(calls) == 1 and result["status"] == expected
    assert result["http_status"] == status
    assert result["raw_response"] == (json.loads(body) if body.startswith("{") else body)
    assert "токен" not in result["reason"].lower()


@pytest.mark.asyncio
async def test_pause_before_next_single_code_query(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the existing backoff mechanism with a controlled clock, without waiting.
    waits = []
    remaining = iter([1.25, 0.0])
    monkeypatch.setattr(check._PACING, "remaining_seconds", lambda _: next(remaining))

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(check.asyncio, "sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=APPLIED)
    )) as client:
        result = await check.check_code(client, FULL_QA_CODE)
    assert waits == [1.25] and result["status"] == "problem"
