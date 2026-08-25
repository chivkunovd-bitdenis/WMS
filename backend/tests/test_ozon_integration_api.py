"""Pre-development API contract tests for the additive Ozon self-account route."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.ozon_integration import OzonValidationResult


ACCOUNT = "/integrations/ozon/self/account"


async def _seller_headers(async_client: AsyncClient) -> dict[str, str]:
    """Developer must retain this existing auth flow; no provider credentials are used."""
    import uuid

    suffix = uuid.uuid4().hex
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Ozon contract test",
            "slug": f"ozon-contract-{suffix}",
            "admin_email": f"ozon-contract-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200
    admin_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Ozon seller"})
    assert seller.status_code == 201
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={
            "seller_id": seller.json()["id"],
            "email": f"ozon-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert account.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": f"ozon-seller-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_tc_s32_ozon_006_self_account_requires_auth(async_client: AsyncClient) -> None:
    for method, path in (("get", ACCOUNT), ("put", ACCOUNT), ("post", f"{ACCOUNT}/test-connection"), ("delete", ACCOUNT)):
        response = await getattr(async_client, method)(path, json={} if method == "put" else None)
        assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "client_id_required"),
        ({"client_id": "   ", "api_key": "x"}, "client_id_required"),
        ({"client_id": "x", "api_key": "   "}, "api_key_required"),
        ({"client_id": 7, "api_key": "x"}, None),
        ({"client_id": "x", "api_key": 7}, None),
        ({"client_id": "x", "api_key": "y", "seller_id": "foreign"}, None),
    ],
)
async def test_tc_s32_ozon_002_invalid_payload_never_reaches_provider(
    async_client: AsyncClient, payload: object, code: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def forbidden_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        nonlocal calls
        calls += 1
        raise AssertionError("validation must not receive invalid input")

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", forbidden_validator)
    response = await async_client.put(ACCOUNT, headers=await _seller_headers(async_client), json=payload)
    assert response.status_code == 422
    if code is not None:
        assert response.json()["code"] == code
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "expected_status", "expected_code"),
    [
        (OzonValidationResult.success(), 200, None),
        (OzonValidationResult.http(401), 422, "ozon_credentials_invalid"),
        (OzonValidationResult.http(403), 422, "ozon_credentials_invalid"),
        (OzonValidationResult.transport_error(), 503, "ozon_validation_unavailable"),
        (OzonValidationResult.http(429), 503, "ozon_validation_unavailable"),
        (OzonValidationResult.http(500), 503, "ozon_validation_unavailable"),
        (OzonValidationResult.http(418), 502, "ozon_validation_failed"),
    ],
)
async def test_tc_s32_ozon_003_004_provider_failure_contract(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    result: OzonValidationResult,
    expected_status: int,
    expected_code: str | None,
) -> None:
    async def fake_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return result

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", fake_validator)
    response = await async_client.put(
        ACCOUNT,
        headers=await _seller_headers(async_client),
        json={"client_id": "client-handle", "api_key": "key-handle"},
    )
    assert response.status_code == expected_status
    if expected_code is None:
        assert response.json()["connected"] is True
    else:
        assert response.json()["code"] == expected_code
        assert "client-handle" not in response.text
        assert "key-handle" not in response.text


@pytest.mark.asyncio
async def test_tc_s32_ozon_009_no_body_is_allowed_for_manual_check(
    async_client: AsyncClient,
) -> None:
    headers = await _seller_headers(async_client)
    response = await async_client.post(f"{ACCOUNT}/test-connection", headers=headers, json={"extra": True})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tc_s32_ozon_014_public_schema_hides_account_identity_and_future_facts(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(ACCOUNT, headers=await _seller_headers(async_client))
    assert response.status_code == 200
    assert set(response.json()) == {
        "marketplace", "connected", "validation_status", "last_validated_at",
        "last_validation_error", "credentials_updated_at", "last_synced_at", "last_sync_error",
    }
    schema = (await async_client.get("/openapi.json")).text
    for prohibited in ("account_slot", "external_account_id", "client_id", "api_key", "expires_at", "capabilities"):
        assert prohibited not in schema
