"""Pre-development API contract tests for the additive Ozon self-account route."""

from __future__ import annotations

import asyncio

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
    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Ozon seller"}
    )
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
    for method, path in (
        ("get", ACCOUNT),
        ("put", ACCOUNT),
        ("post", f"{ACCOUNT}/test-connection"),
        ("delete", ACCOUNT),
    ):
        response = await async_client.request(
            method.upper(), path, json={} if method == "put" else None
        )
        assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "client_id_required"),
        ({"client_id": None, "api_key": "x"}, "client_id_required"),
        ({"client_id": "   ", "api_key": "x"}, "client_id_required"),
        ({"client_id": "x"}, "api_key_required"),
        ({"client_id": "x", "api_key": None}, "api_key_required"),
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
    response = await async_client.put(
        ACCOUNT, headers=await _seller_headers(async_client), json=payload
    )
    assert response.status_code == 422
    if code is not None:
        assert response.json()["code"] == code
    assert calls == 0


@pytest.mark.asyncio
async def test_tc_s32_ozon_002_put_request_schema_is_strict_and_documented(
    async_client: AsyncClient,
) -> None:
    openapi = (await async_client.get("/openapi.json")).json()
    request_schema = openapi["paths"][ACCOUNT]["put"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    schema = openapi["components"]["schemas"][schema_name]

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["client_id", "api_key"]
    assert schema["properties"]["client_id"]["minLength"] == 1
    assert schema["properties"]["client_id"]["maxLength"] == 255
    assert schema["properties"]["api_key"]["minLength"] == 1
    assert schema["properties"]["api_key"]["maxLength"] == 4096


@pytest.mark.asyncio
async def test_tc_s32_ozon_009_ordinary_validator_path_uses_the_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.ozon_client as ozon_client

    calls: list[tuple[object, str, str]] = []

    async def recorded_adapter(
        *, transport: object, client_id: str, api_key: str
    ) -> OzonValidationResult:
        calls.append((transport, client_id, api_key))
        return OzonValidationResult.success()

    monkeypatch.delenv("E2E_MOCK_OZON_VALIDATION", raising=False)
    monkeypatch.setattr(ozon_client, "validate_seller_info", recorded_adapter)

    result = await ozon_client.validate_ozon_credentials("ordinary-client", "ordinary-key")

    assert result.status_code == 204
    assert len(calls) == 1
    assert calls[0][1:] == ("ordinary-client", "ordinary-key")


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
async def test_tc_s32_ozon_003_invalid_candidate_keeps_disconnected_status(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def invalid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.http(401)

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", invalid_validator)
    headers = await _seller_headers(async_client)
    rejected = await async_client.put(
        ACCOUNT, headers=headers, json={"client_id": "candidate-client", "api_key": "candidate-key"}
    )
    assert rejected.status_code == 422
    current = await async_client.get(ACCOUNT, headers=headers)
    assert current.status_code == 200
    assert current.json()["connected"] is False
    assert "candidate-client" not in current.text
    assert "candidate-key" not in current.text


@pytest.mark.asyncio
async def test_tc_s32_ozon_003_invalid_replacement_preserves_working_public_status(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def valid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.success()

    headers = await _seller_headers(async_client)
    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", valid_validator)
    created = await async_client.put(
        ACCOUNT, headers=headers, json={"client_id": "working-client", "api_key": "working-key"}
    )
    assert created.status_code == 200
    public_before = created.json()

    async def invalid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.http(403)

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", invalid_validator)
    rejected = await async_client.put(
        ACCOUNT, headers=headers, json={"client_id": "candidate-client", "api_key": "candidate-key"}
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "ozon_credentials_invalid"
    current = await async_client.get(ACCOUNT, headers=headers)
    assert current.status_code == 200
    assert current.json() == public_before
    for sensitive in ("working-client", "working-key", "candidate-client", "candidate-key"):
        assert sensitive not in rejected.text
        assert sensitive not in current.text


@pytest.mark.asyncio
async def test_tc_s32_ozon_005_parallel_equal_puts_are_both_successful_and_leave_one_status(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def valid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        await asyncio.sleep(0)
        return OzonValidationResult.success()

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", valid_validator)
    headers = await _seller_headers(async_client)
    first, second = await asyncio.gather(
        async_client.put(
            ACCOUNT,
            headers=headers,
            json={"client_id": "parallel-client", "api_key": "parallel-key"},
        ),
        async_client.put(
            ACCOUNT,
            headers=headers,
            json={"client_id": "parallel-client", "api_key": "parallel-key"},
        ),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    current = await async_client.get(ACCOUNT, headers=headers)
    assert current.status_code == 200
    assert current.json()["connected"] is True
    assert "parallel-client" not in current.text
    assert "parallel-key" not in current.text


@pytest.mark.asyncio
async def test_tc_s32_ozon_010_manual_check_uses_safe_status_only(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def valid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.success()

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", valid_validator)
    headers = await _seller_headers(async_client)
    saved = await async_client.put(
        ACCOUNT, headers=headers, json={"client_id": "private-client", "api_key": "private-key"}
    )
    assert saved.status_code == 200
    checked = await async_client.post(f"{ACCOUNT}/test-connection", headers=headers)
    assert checked.status_code == 200
    assert checked.json()["validation_status"] == "valid"
    assert "private-client" not in checked.text
    assert "private-key" not in checked.text


@pytest.mark.asyncio
async def test_tc_s32_ozon_009_no_body_is_allowed_for_manual_check(
    async_client: AsyncClient,
) -> None:
    headers = await _seller_headers(async_client)
    response = await async_client.post(
        f"{ACCOUNT}/test-connection", headers=headers, json={"extra": True}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tc_s32_ozon_014_public_schema_hides_account_identity_and_future_facts(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(ACCOUNT, headers=await _seller_headers(async_client))
    assert response.status_code == 200
    assert set(response.json()) == {
        "marketplace",
        "connected",
        "live_exchange_enabled",
        "validation_status",
        "last_validated_at",
        "last_validation_error",
        "credentials_updated_at",
        "last_synced_at",
        "last_sync_error",
    }
    openapi = (await async_client.get("/openapi.json")).json()
    account_operations = openapi["paths"][ACCOUNT]
    public_schema_ref = account_operations["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    public_schema_name = public_schema_ref.rsplit("/", 1)[-1]
    public_schema = openapi["components"]["schemas"][public_schema_name]
    public_fields = set(public_schema["properties"])
    assert public_fields == {
        "marketplace",
        "connected",
        "live_exchange_enabled",
        "validation_status",
        "last_validated_at",
        "last_validation_error",
        "credentials_updated_at",
        "last_synced_at",
        "last_sync_error",
    }
    # Only Ozon *public response* schemas belong to this secrecy assertion.  Existing
    # WMS request schemas legitimately use client_id, and this route's PUT input must
    # accept it; neither fact may weaken the Ozon status-output contract.
    for path, method in (
        (ACCOUNT, "get"),
        (ACCOUNT, "put"),
        (f"{ACCOUNT}/test-connection", "post"),
    ):
        response_schema_ref = openapi["paths"][path][method]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        response_schema_name = response_schema_ref.rsplit("/", 1)[-1]
        response_fields = set(openapi["components"]["schemas"][response_schema_name]["properties"])
        assert not response_fields & {
            "id",
            "account_slot",
            "seller_id",
            "tenant_id",
            "external_account_id",
            "client_id",
            "api_key",
            "secret",
            "secret_encrypted",
            "ciphertext",
            "provider_response",
            "expires_at",
            "capabilities",
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_public_status_reports_actual_exchange_setting(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, enabled: bool,
) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "ozon_live_api_enabled", enabled)
    response = await async_client.get(ACCOUNT, headers=await _seller_headers(async_client))
    assert response.status_code == 200
    assert response.json()["live_exchange_enabled"] is enabled
    assert response.json()["connected"] is False
