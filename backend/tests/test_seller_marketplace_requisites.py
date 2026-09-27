"""WMS-547 D1: сервис и эндпоинт «сведения о продавце по API площадки».

Внешние площадки — только подставные ответы (httpx.MockTransport для WB,
FakeMarketplaceTransport для Ozon, как в остальном проекте); живых ключей и
запросов к WB/Ozon здесь нет.

C1 — разбор ответа WB (валидный, отсутствующий/null/пустой/с неверной
контрольной суммой ИНН). C2 — то же для Ozon плюс распознавание блокировки
кабинета. C3 — наложение DaData поверх ИНН площадки. C12 — доступ только
своему tenant/админу и отсутствие значений ключей в ответах и логах.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx
import jwt
import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.services import seller_marketplace_requisites_service as svc
from app.services.dadata_party_service import DadataError
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
)
from app.services.wildberries_credentials_service import SKIP, patch_seller_tokens

REQUISITES_PATH = "/billing/profiles/sellers/{seller_id}/marketplace-requisites"

WB_VALID_INN = "500100732259"
WB_BAD_CHECKSUM_INN = "500100732250"
OZON_VALID_INN = "5024002119"


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, options={"verify_signature": False})


async def _register_admin(
    async_client: AsyncClient, label: str
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    suffix = f"{label}-{time.time_ns()}"
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-547 {label}",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    claims = _decode(token)
    return (
        {"Authorization": f"Bearer {token}"},
        uuid.UUID(claims["sub"]),
        uuid.UUID(claims["tenant_id"]),
    )


async def _create_seller(
    async_client: AsyncClient, headers: dict[str, str], name: str = "WMS-547 селлер"
) -> uuid.UUID:
    response = await async_client.post("/sellers", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


async def _seller_login_headers(
    async_client: AsyncClient, admin_headers: dict[str, str], seller_id: uuid.UUID
) -> dict[str, str]:
    suffix = uuid.uuid4().hex
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={
            "seller_id": str(seller_id),
            "email": f"wms547-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert account.status_code == 201, account.text
    login = await async_client.post(
        "/auth/login",
        json={"email": f"wms547-seller-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _set_wb_token(tenant_id: uuid.UUID, seller_id: uuid.UUID, token: str) -> None:
    async with SessionLocal() as session:
        await patch_seller_tokens(
            session,
            tenant_id,
            seller_id,
            content_api_token=token,
            supplies_api_token=SKIP,
        )


async def _set_ozon_account(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    actor_id: uuid.UUID,
    client_id: str,
    api_key: str,
) -> None:
    async with SessionLocal() as session:
        await MarketplaceAccountService(session).save_validated_candidate(
            tenant_id, seller_id, actor_id, client_id, api_key
        )


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _wb_client_factory(handler: Any) -> Any:
    def factory(**_kwargs: object) -> httpx.AsyncClient:
        # Must not call the (possibly monkeypatched) httpx.AsyncClient here —
        # this factory itself replaces that attribute, and calling through the
        # module name again would recurse into itself forever.
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    return factory


def _wb_json_handler(status_code: int, body: object) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=body)

    return handler


def _ozon_provider_with(transport: FakeMarketplaceTransport) -> Any:
    return lambda **_kwargs: OzonMarketplaceProvider(transport=transport)


# ---------------------------------------------------------------------------
# C1 — WB: разбор seller-info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c1_wb_valid_response_keeps_only_inn_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_seller_info", False)
    body = {
        "name": "ИП Тестов Т. Т.",
        "tin": WB_VALID_INN,
        "sid": "sid-value-should-not-leak-anywhere",
        "tradeMark": "Бренд",
    }
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(200, body)))

    result = await svc.fetch_wb_requisites("wb-token")

    assert result == svc.MarketplaceRequisites(
        inn=WB_VALID_INN, legal_name="ИП Тестов Т. Т.", kpp=None
    )
    # sid/tradeMark нигде не сохранены — датакласс несёт только inn/legal_name/kpp.
    assert set(result.__dataclass_fields__) == {"inn", "legal_name", "kpp"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"name": "ИП Тестов"},  # (б) tin отсутствует
        {"name": "ИП Тестов", "tin": None},  # (в) tin: null
        {"name": "ИП Тестов", "tin": ""},  # (г) tin: ""
        {"name": "ИП Тестов", "tin": WB_BAD_CHECKSUM_INN},  # (д) неверная контрольная сумма
    ],
    ids=["missing", "null", "empty", "bad_checksum"],
)
async def test_c1_wb_missing_or_invalid_tin_yields_none_without_exception(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_seller_info", False)
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(200, body)))

    result = await svc.fetch_wb_requisites("wb-token")

    assert result is None


@pytest.mark.asyncio
async def test_c1_wb_e2e_mock_flag_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_seller_info", True)

    def _must_not_be_called(**_kwargs: object) -> httpx.AsyncClient:
        raise AssertionError("e2e mock must not open a real HTTP client")

    monkeypatch.setattr(svc.httpx, "AsyncClient", _must_not_be_called)

    result = await svc.fetch_wb_requisites("wb-token")

    assert result is not None
    assert result.inn == svc._MOCK_WB_SELLER_INFO["tin"]


# ---------------------------------------------------------------------------
# C2 — Ozon: разбор /v1/seller/info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c2_ozon_uses_legal_name_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            svc.OZON_SELLER_INFO_PATH: {
                "company": {
                    "inn": OZON_VALID_INN,
                    "legal_name": "ООО Ромашка",
                    "name": "Ромашка на Ozon",
                }
            }
        }
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    result = await svc.fetch_ozon_requisites(client_id="cid", api_key="key")

    assert result == svc.MarketplaceRequisites(
        inn=OZON_VALID_INN, legal_name="ООО Ромашка", kpp=None
    )


@pytest.mark.asyncio
async def test_c2_ozon_falls_back_to_name_when_legal_name_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            svc.OZON_SELLER_INFO_PATH: {
                "company": {"inn": OZON_VALID_INN, "legal_name": "", "name": "Ромашка на Ozon"}
            }
        }
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    result = await svc.fetch_ozon_requisites(client_id="cid", api_key="key")

    assert result is not None
    assert result.legal_name == "Ромашка на Ozon"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [{}, {"company": None}, {"company": "not-a-dict"}, {"company": {}}],
    ids=["no_company_key", "company_null", "company_not_dict", "company_without_inn"],
)
async def test_c2_ozon_missing_company_or_inn_yields_none_without_exception(
    monkeypatch: pytest.MonkeyPatch, raw: dict[str, object]
) -> None:
    transport = FakeMarketplaceTransport(endpoint_responses={svc.OZON_SELLER_INFO_PATH: raw})
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    result = await svc.fetch_ozon_requisites(client_id="cid", api_key="key")

    assert result is None


@pytest.mark.asyncio
async def test_c2_ozon_account_blocked_is_recognized(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeMarketplaceTransport(
        errors={svc.OZON_SELLER_INFO_PATH: MarketplaceProviderError("ozon", 403, {"code": 7})}
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    with pytest.raises(svc.SellerRequisitesLookupError) as exc_info:
        await svc.fetch_ozon_requisites(client_id="cid", api_key="key")

    assert exc_info.value.code == "ozon_account_blocked"


# ---------------------------------------------------------------------------
# C3 — наложение DaData поверх ИНН площадки
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c3_dadata_overlay_replaces_name_and_fills_kpp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_lookup(inn: str) -> dict[str, Any]:
        assert inn == WB_VALID_INN
        return {"legal_name": "ООО Ромашка (DaData)", "kpp": "770701001", "inn": inn}

    monkeypatch.setattr(svc, "lookup_party_by_inn", fake_lookup)
    requisites = svc.MarketplaceRequisites(inn=WB_VALID_INN, legal_name="Из площадки", kpp=None)

    result = await svc.overlay_dadata(requisites)

    assert result == svc.MarketplaceRequisites(
        inn=WB_VALID_INN, legal_name="ООО Ромашка (DaData)", kpp="770701001"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_code",
    [
        "dadata_not_configured",
        "inn_invalid",
        "dadata_rejected",
        "dadata_unavailable",
        "party_not_found",
    ],
)
async def test_c3_dadata_failure_keeps_marketplace_data_without_kpp(
    monkeypatch: pytest.MonkeyPatch, error_code: str
) -> None:
    async def fake_lookup(inn: str) -> dict[str, Any]:
        raise DadataError(error_code)

    monkeypatch.setattr(svc, "lookup_party_by_inn", fake_lookup)
    requisites = svc.MarketplaceRequisites(inn=WB_VALID_INN, legal_name="Из площадки", kpp=None)

    result = await svc.overlay_dadata(requisites)

    assert result == requisites


# ---------------------------------------------------------------------------
# Сквозная проверка через HTTP-эндпоинт (D1: R1-R4, R11 коды ошибок)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_wb_success_with_dadata_overlay(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    await _set_wb_token(tenant_id, seller_id, "wb-token-value")

    body = {"name": "ИП Тестов Т. Т.", "tin": WB_VALID_INN}
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(200, body)))

    async def fake_lookup(inn: str) -> dict[str, Any]:
        return {"legal_name": "ИП Тестов Т.Т. (DaData)", "kpp": "770701001", "inn": inn}

    monkeypatch.setattr(svc, "lookup_party_by_inn", fake_lookup)

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=owner_headers,
        params={"marketplace": "wb"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "inn": WB_VALID_INN,
        "legal_name": "ИП Тестов Т.Т. (DaData)",
        "kpp": "770701001",
    }


@pytest.mark.asyncio
async def test_endpoint_wb_success_without_dadata_keeps_marketplace_name(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    await _set_wb_token(tenant_id, seller_id, "wb-token-value")

    body = {"name": "ИП Тестов Т. Т.", "tin": WB_VALID_INN}
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(200, body)))

    async def fake_lookup(inn: str) -> dict[str, Any]:
        raise DadataError("dadata_not_configured")

    monkeypatch.setattr(svc, "lookup_party_by_inn", fake_lookup)

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=owner_headers,
        params={"marketplace": "wb"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"inn": WB_VALID_INN, "legal_name": "ИП Тестов Т. Т.", "kpp": None}


@pytest.mark.asyncio
async def test_endpoint_wb_without_usable_inn_is_inn_missing(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    await _set_wb_token(tenant_id, seller_id, "wb-token-value")
    monkeypatch.setattr(
        svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(200, {"name": "ИП Тестов"}))
    )

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=owner_headers,
        params={"marketplace": "wb"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "inn_missing"


@pytest.mark.asyncio
async def test_endpoint_wb_rate_limited(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    await _set_wb_token(tenant_id, seller_id, "wb-token-value")
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_json_handler(429, {})))

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=owner_headers,
        params={"marketplace": "wb"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "marketplace_rate_limited"


@pytest.mark.asyncio
async def test_endpoint_ozon_account_blocked(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    await _set_ozon_account(tenant_id, seller_id, admin_id, "client-id", "api-key")
    transport = FakeMarketplaceTransport(
        errors={svc.OZON_SELLER_INFO_PATH: MarketplaceProviderError("ozon", 403, {"code": 7})}
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=owner_headers,
        params={"marketplace": "ozon"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "ozon_account_blocked"


# ---------------------------------------------------------------------------
# C12 — доступ только своему tenant/админу, без сеанса к площадке без ключа,
# без значений ключей в ответах и логах
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c12_wrong_tenant_and_missing_seller_are_404(async_client: AsyncClient) -> None:
    owner_headers, _admin_id, _tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)

    other_headers, _other_admin_id, _other_tenant_id = await _register_admin(async_client, "other")
    cross_tenant = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=other_headers,
        params={"marketplace": "wb"},
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["detail"] == "seller_not_found"

    missing = await async_client.get(
        REQUISITES_PATH.format(seller_id=uuid.uuid4()),
        headers=owner_headers,
        params={"marketplace": "wb"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "seller_not_found"


@pytest.mark.asyncio
async def test_c12_seller_role_user_is_forbidden(async_client: AsyncClient) -> None:
    owner_headers, _admin_id, _tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)

    response = await async_client.get(
        REQUISITES_PATH.format(seller_id=seller_id),
        headers=seller_headers,
        params={"marketplace": "wb"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_c12_key_not_connected_never_calls_marketplace(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, _tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)

    async def _fail_if_called_wb(token: str) -> dict[str, Any]:
        raise AssertionError("must not call WB when no key is connected")

    async def _fail_if_called_ozon(*, client_id: str, api_key: str) -> dict[str, Any]:
        raise AssertionError("must not call Ozon when no key is connected")

    monkeypatch.setattr(svc, "_call_wb_seller_info", _fail_if_called_wb)
    monkeypatch.setattr(svc, "_call_ozon_seller_info", _fail_if_called_ozon)

    for marketplace in ("wb", "ozon"):
        response = await async_client.get(
            REQUISITES_PATH.format(seller_id=seller_id),
            headers=owner_headers,
            params={"marketplace": marketplace},
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"] == "key_not_connected"


@pytest.mark.asyncio
async def test_c12_no_secret_values_leak_into_response_or_logs(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner_headers, admin_id, tenant_id = await _register_admin(async_client, "owner")
    seller_id = await _create_seller(async_client, owner_headers)

    wb_secret = "WB-SECRET-TOKEN-VALUE-MUST-NOT-LEAK"
    await _set_wb_token(tenant_id, seller_id, wb_secret)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == wb_secret
        return httpx.Response(401, json={"detail": "unauthorized"})

    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(handler))

    with caplog.at_level(logging.WARNING):
        wb_response = await async_client.get(
            REQUISITES_PATH.format(seller_id=seller_id),
            headers=owner_headers,
            params={"marketplace": "wb"},
        )

    assert wb_response.status_code == 502
    assert wb_response.json()["detail"] == "marketplace_rejected_key"
    assert wb_secret not in wb_response.text
    assert all(wb_secret not in record.getMessage() for record in caplog.records)

    other_seller_id = await _create_seller(async_client, owner_headers, "WMS-547 Ozon селлер")
    ozon_client_id = "OZON-CLIENT-ID-MUST-NOT-LEAK"
    ozon_api_key = "OZON-API-KEY-MUST-NOT-LEAK"
    await _set_ozon_account(tenant_id, other_seller_id, admin_id, ozon_client_id, ozon_api_key)
    transport = FakeMarketplaceTransport(
        errors={svc.OZON_SELLER_INFO_PATH: MarketplaceProviderError("ozon", 500, {})}
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        ozon_response = await async_client.get(
            REQUISITES_PATH.format(seller_id=other_seller_id),
            headers=owner_headers,
            params={"marketplace": "ozon"},
        )

    assert ozon_response.status_code == 502
    assert ozon_response.json()["detail"] == "marketplace_unavailable"
    assert ozon_client_id not in ozon_response.text
    assert ozon_api_key not in ozon_response.text
    assert all(
        ozon_client_id not in record.getMessage() and ozon_api_key not in record.getMessage()
        for record in caplog.records
    )
