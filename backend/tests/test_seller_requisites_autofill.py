"""WMS-547 D2: автозаполнение реквизитов селлера при подключении ключа.

Проверки C4-C8 из документа требований. Использует HTTP-клиентом реальные
ручки сохранения ключа (WB self-service, WB admin PATCH, Ozon self-service) и
подставные ответы площадок — живых ключей и запросов здесь нет. Хелперы
регистрации/логина переиспользованы из test_seller_marketplace_requisites.py
(тот же приём, что и в остальном проекте — см. cross-file импорты в
tests/test_billing_invoice_cross_format_duplicates.py).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.ozon_integration import OzonValidationResult
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.billing import BillingProfile
from app.models.document_event import DOCUMENT_TYPE_BILLING_PROFILE, DocumentEvent
from app.services import seller_marketplace_requisites_service as svc
from app.services.marketplace_provider import FakeMarketplaceTransport, MarketplaceProviderError
from app.services.wildberries_credentials_service import (
    SKIP,
    get_public_token_status,
    patch_seller_tokens,
)
from tests.test_seller_marketplace_requisites import (
    OZON_VALID_INN,
    WB_VALID_INN,
    _create_seller,
    _ozon_provider_with,
    _register_admin,
    _seller_login_headers,
    _wb_client_factory,
    _wb_json_handler,
)


def _stub_wb_card_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карточки, проверка Marketplace-области и фоновая синхронизация складов
    WB — не предмет этих тестов. Все три используют собственные e2e-флаги
    подставных ответов (как остальной проект), поэтому не трогают httpx вообще
    и не пересекаются с моком seller-info, который ставится через
    ``svc.httpx.AsyncClient`` в каждом тесте отдельно.
    """
    monkeypatch.setattr(settings, "e2e_mock_wb_cards", True)
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_warehouses", True)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)


async def _profile_or_none(tenant_id: Any, seller_id: Any) -> BillingProfile | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(BillingProfile).where(
                BillingProfile.tenant_id == tenant_id, BillingProfile.seller_id == seller_id
            )
        )


# ---------------------------------------------------------------------------
# C4 — WB self-service: создание, один запрос, событие в журнале, повтор без
# новых запросов
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c4_wb_self_service_creates_requisites_with_single_call_and_journal_event(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "c4-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 А")
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)
    _stub_wb_card_import(monkeypatch)

    seller_info_calls = 0
    taxonomy_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seller_info_calls
        assert request.headers["Authorization"] == "wms547-a-wb-key"
        if request.url.path == "/api/v1/seller-info":
            seller_info_calls += 1
            return httpx.Response(200, json={"name": "ИП Тестов А", "tin": WB_VALID_INN})
        if request.url.path == "/content/v2/object/parent/all":
            assert request.method == "GET"
            taxonomy_requests.append(request)
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/content/v2/object/all":
            assert request.method == "GET"
            assert dict(request.url.params) == {"limit": "1000", "offset": "0"}
            taxonomy_requests.append(request)
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected WB request: {request.method} {request.url}")

    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(handler))

    saved = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=seller_headers,
        json={"content_api_token": "wms547-a-wb-key"},
    )
    assert saved.status_code == 200, saved.text
    assert seller_info_calls == 1
    assert [request.url.path for request in taxonomy_requests] == [
        "/content/v2/object/parent/all",
        "/content/v2/object/all",
    ]

    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is not None
    assert profile.inn == WB_VALID_INN
    assert profile.legal_name == "ИП Тестов А"
    assert profile.kpp is None

    async with SessionLocal() as session:
        events = (
            await session.scalars(
                select(DocumentEvent).where(
                    DocumentEvent.tenant_id == tenant_id,
                    DocumentEvent.document_type == DOCUMENT_TYPE_BILLING_PROFILE,
                    DocumentEvent.document_id == profile.id,
                )
            )
        ).all()
        assert len(events) == 1

    # "Открыть карточку" (существующая ручка чтения профиля) несколько раз —
    # она читает только БД и никогда не обращалась к площадке (WMS-547 R13).
    for _ in range(3):
        got = await async_client.get(
            f"/billing/profiles/sellers/{seller_id}", headers=owner_headers
        )
        assert got.status_code == 200, got.text
        assert got.json()["inn"] == WB_VALID_INN
    assert seller_info_calls == 1


# ---------------------------------------------------------------------------
# C5 — admin PATCH (WB) и self-service PUT (Ozon) тоже создают реквизиты
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_c5_admin_patch_wb_token_creates_requisites(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "c5-wb-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 А2")

    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        _wb_client_factory(_wb_json_handler(200, {"name": "ИП Тестов А2", "tin": WB_VALID_INN})),
    )

    patched = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=owner_headers,
        json={"content_api_token": "wms547-a2-wb-key"},
    )
    assert patched.status_code == 200, patched.text

    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is not None
    assert profile.inn == WB_VALID_INN
    assert profile.legal_name == "ИП Тестов А2"


@pytest.mark.asyncio
async def test_c5_ozon_self_service_creates_requisites(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "c5-ozon-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 Ozon")
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)

    async def valid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.success()

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", valid_validator)
    transport = FakeMarketplaceTransport(
        endpoint_responses={
            svc.OZON_SELLER_INFO_PATH: {
                "company": {"inn": OZON_VALID_INN, "legal_name": "ООО Озон Тест"}
            }
        }
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    saved = await async_client.put(
        "/integrations/ozon/self/account",
        headers=seller_headers,
        json={"client_id": "wms547-ozon-client", "api_key": "wms547-ozon-key"},
    )
    assert saved.status_code == 200, saved.text

    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is not None
    assert profile.inn == OZON_VALID_INN
    assert profile.legal_name == "ООО Озон Тест"


# ---------------------------------------------------------------------------
# C6 — уже есть запись реквизитов (введена руками) — ни одно поле не меняется
# ---------------------------------------------------------------------------


_MANUAL_PROFILE_FULL: dict[str, str] = {
    "legal_name": "ООО Ручное",
    "inn": "7707083893",
    "kpp": "770701001",
    "bank_name": "Банк",
    "bik": "044525225",
    "settlement_account": "40702810000000000001",
    "correspondent_account": "30101810400000000225",
}


async def _assert_manual_profile_untouched_by_wb_key(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    label: str,
    manual_profile: dict[str, str | None],
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, label)
    seller_id = await _create_seller(async_client, owner_headers, f"WMS-547 {label}")

    put_manual = await async_client.put(
        f"/billing/profiles/sellers/{seller_id}", headers=owner_headers, json=manual_profile
    )
    assert put_manual.status_code == 200, put_manual.text

    async with SessionLocal() as session:
        events_before = len(
            (
                await session.scalars(
                    select(DocumentEvent).where(
                        DocumentEvent.tenant_id == tenant_id,
                        DocumentEvent.document_type == DOCUMENT_TYPE_BILLING_PROFILE,
                    )
                )
            ).all()
        )

    # WB отдаёт другое наименование (и, возможно, другой ИНН) — не должно
    # попасть ни в одно поле уже существующей записи.
    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        _wb_client_factory(
            _wb_json_handler(200, {"name": "Другое наименование с площадки", "tin": WB_VALID_INN})
        ),
    )
    patched = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=owner_headers,
        json={"content_api_token": f"wms547-{label}-wb-key"},
    )
    assert patched.status_code == 200, patched.text

    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is not None
    for field, expected in manual_profile.items():
        assert getattr(profile, field) == (expected or None)

    async with SessionLocal() as session:
        events_after = (
            await session.scalars(
                select(DocumentEvent).where(
                    DocumentEvent.tenant_id == tenant_id,
                    DocumentEvent.document_type == DOCUMENT_TYPE_BILLING_PROFILE,
                )
            )
        ).all()
        assert len(events_after) == events_before


@pytest.mark.asyncio
async def test_c6_full_manual_profile_untouched_by_wb_key(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _assert_manual_profile_untouched_by_wb_key(
        async_client, monkeypatch, label="c6-full", manual_profile=dict(_MANUAL_PROFILE_FULL)
    )


@pytest.mark.asyncio
async def test_c6_manual_profile_with_matching_inn_and_empty_kpp_untouched(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    manual_profile = dict(_MANUAL_PROFILE_FULL)
    manual_profile["inn"] = WB_VALID_INN  # тот же ИНН, что вернёт площадка
    manual_profile["kpp"] = ""
    await _assert_manual_profile_untouched_by_wb_key(
        async_client, monkeypatch, label="c6-samekpp", manual_profile=manual_profile
    )


# ---------------------------------------------------------------------------
# C7 — отказ площадки не влияет на сохранение ключа; кнопка потом работает
# ---------------------------------------------------------------------------


_EXPECTED_MOCK_CARDS_SAVE_RESPONSE: dict[str, Any] = {
    "ok": True,
    "validation_ok": True,
    "validation_error": None,
    # WMS-615: saving the key queues a durable catalog import. The response
    # reports zero imported cards; the job endpoint reports the completed import.
    "cards_received": 0,
    "cards_saved": 0,
    "products_created": 0,
    "products_updated": 0,
    "products_skipped": 0,
    # WMS-535: диагностика хранения всех ШК размера WB — на этом мок-снимке
    # конфликтов и пропусков нет, все счётчики нулевые.
    "sizes_missing_chrt_id": 0,
    "duplicate_chrt_id": 0,
    "barcode_conflicts": 0,
    "barcode_conflict_details": [],
}


def _wb_failure_handler(kind: str) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        if kind == "401":
            return httpx.Response(401, json={"detail": "unauthorized"})
        if kind == "429":
            return httpx.Response(429, json={})
        if kind == "500":
            return httpx.Response(500, json={})
        if kind == "bad_json":
            return httpx.Response(200, content=b"not-json-at-all")
        if kind == "timeout":
            raise httpx.ConnectTimeout("boom")
        raise AssertionError(f"unexpected kind {kind}")

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["401", "429", "500", "bad_json", "timeout"])
async def test_c7_wb_seller_info_failure_does_not_affect_key_save_response(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    label = f"c7-{kind}".replace("_", "-")
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, label)
    seller_id = await _create_seller(async_client, owner_headers, f"WMS-547 C7 {kind}")
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)
    _stub_wb_card_import(monkeypatch)
    monkeypatch.setattr(svc.httpx, "AsyncClient", _wb_client_factory(_wb_failure_handler(kind)))

    saved = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=seller_headers,
        json={"content_api_token": f"wms547-c7-{kind}-key"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    catalog_job = body.pop("catalog_job")
    assert body == _EXPECTED_MOCK_CARDS_SAVE_RESPONSE
    assert catalog_job["state"] == "queued"
    assert catalog_job["marketplace"] == "wildberries"
    job = await async_client.get(
        f"/operations/background-jobs/{catalog_job['id']}", headers=seller_headers
    )
    assert job.status_code == 200, job.text
    assert job.json()["state"] == "succeeded"
    assert job.json()["result_json"]["cards_received"] == 1
    assert job.json()["result_json"]["cards_saved"] == 1
    async with SessionLocal() as session:
        token_status = await get_public_token_status(session, tenant_id, seller_id)
        assert token_status is not None
        assert token_status[0] is True


    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is None

    # После отказа кнопка «Заполнить из WB» всё ещё работает с нормальным ответом
    # (повтор безопасен — вызов только читает).
    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        _wb_client_factory(_wb_json_handler(200, {"name": "ИП После отказа", "tin": WB_VALID_INN})),
    )
    button = await async_client.get(
        f"/billing/profiles/sellers/{seller_id}/marketplace-requisites",
        headers=owner_headers,
        params={"marketplace": "wb"},
    )
    assert button.status_code == 200, button.text
    assert button.json()["inn"] == WB_VALID_INN


@pytest.mark.asyncio
async def test_c7_ozon_account_blocked_does_not_affect_key_save_response(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "c7-ozon-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 C7 Ozon")
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)

    async def valid_validator(*_args: object, **_kwargs: object) -> OzonValidationResult:
        return OzonValidationResult.success()

    monkeypatch.setattr("app.api.ozon_integration.validate_ozon_credentials", valid_validator)
    transport = FakeMarketplaceTransport(
        errors={svc.OZON_SELLER_INFO_PATH: MarketplaceProviderError("ozon", 403, {"code": 7})}
    )
    monkeypatch.setattr(svc, "build_ozon_provider", _ozon_provider_with(transport))

    saved = await async_client.put(
        "/integrations/ozon/self/account",
        headers=seller_headers,
        json={"client_id": "wms547-c7-ozon-client", "api_key": "wms547-c7-ozon-key"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["connected"] is True

    profile = await _profile_or_none(tenant_id, seller_id)
    assert profile is None


# ---------------------------------------------------------------------------
# C8 — гонка: ручное сохранение побеждает, автозаполнение не создаёт вторую
# запись и не падает
# ---------------------------------------------------------------------------


async def _all_profiles(tenant_id: Any, seller_id: Any) -> list[BillingProfile]:
    async with SessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(BillingProfile).where(
                        BillingProfile.tenant_id == tenant_id,
                        BillingProfile.seller_id == seller_id,
                    )
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_c8_manual_save_via_http_wins_when_committed_before_autofill(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Очерёдность 1: ручное сохранение коммитится раньше автозаполнения.

    По замечанию ревью F1 ручное сохранение идёт настоящим HTTP PUT с токеном
    админа (не прямым вызовом save_profile) — так действительно проверяется
    обработчик `PUT /billing/profiles/sellers/{id}`, а не только сервис.
    """
    owner_headers, _admin_id, tenant_id = await _register_admin(async_client, "c8a-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 C8a")
    seller_headers = await _seller_login_headers(async_client, owner_headers, seller_id)
    _stub_wb_card_import(monkeypatch)

    manual_legal_name = "ООО Успели Раньше"
    manual_inn = "7707083893"

    monkeypatch.setattr(settings, "e2e_mock_wb_seller_info", False)
    original_call_wb_seller_info = svc._call_wb_seller_info

    async def racing_call_wb_seller_info(token: str) -> dict[str, Any]:
        # Пока «идёт» запрос к WB, кто-то успевает сохранить реквизиты руками
        # через настоящий HTTP PUT — до того как автозаполнение дойдёт до
        # своей записи.
        put_response = await async_client.put(
            f"/billing/profiles/sellers/{seller_id}",
            headers=owner_headers,
            json={"legal_name": manual_legal_name, "inn": manual_inn},
        )
        assert put_response.status_code == 200, put_response.text
        return await original_call_wb_seller_info(token)

    monkeypatch.setattr(svc, "_call_wb_seller_info", racing_call_wb_seller_info)
    monkeypatch.setattr(
        svc.httpx,
        "AsyncClient",
        _wb_client_factory(_wb_json_handler(200, {"name": "Автозаполнение", "tin": WB_VALID_INN})),
    )

    saved = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=seller_headers,
        json={"content_api_token": "wms547-c8a-wb-key"},
    )
    assert saved.status_code == 200, saved.text

    profiles = await _all_profiles(tenant_id, seller_id)
    assert len(profiles) == 1
    assert profiles[0].legal_name == manual_legal_name
    assert profiles[0].inn == manual_inn


@pytest.mark.asyncio
async def test_f1_manual_save_via_http_wins_even_when_autofill_inserts_first(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Очерёдность 2 (независимое ревью WMS-547, F1): ручной PUT уже прочитал
    «записи нет», но до его собственной вставки автозаполнение успевает
    создать запись и закоммититься первым.

    До исправления это давало ручному PUT необработанный 500 (save_profile
    сама ловила IntegrityError на вставке, а обработчик её не перехватывал).
    Теперь save_profile перечитывает конфликтную запись и обновляет её
    ручными значениями — человек побеждает, а не отдаёт 500.

    Реальная интерливинг-гонка воспроизведена через monkeypatch на
    AsyncSession.scalar: как только он видит «запись реквизитов ещё не
    найдена» (это и есть чтение внутри save_profile), запускается и
    завершается автозаполнение по WB-ключу в отдельной сессии — то есть
    ровно в щели между чтением и вставкой ручного сохранения.
    """
    owner_headers, admin_id, tenant_id = await _register_admin(async_client, "f1-owner")
    seller_id = await _create_seller(async_client, owner_headers, "WMS-547 F1")
    _ = admin_id

    manual_legal_name = "ООО Ручное Победило"
    manual_inn = "7707083893"

    async with SessionLocal() as session:
        await patch_seller_tokens(
            session,
            tenant_id,
            seller_id,
            content_api_token="wms547-f1-wb-key",
            supplies_api_token=SKIP,
        )

    monkeypatch.setattr(settings, "e2e_mock_wb_seller_info", True)

    triggered = False
    original_scalar = AsyncSession.scalar

    async def patched_scalar(
        self: AsyncSession, statement: Any, *args: object, **kwargs: object
    ) -> Any:
        nonlocal triggered
        result = await original_scalar(self, statement, *args, **kwargs)
        if not triggered and result is None and "billing_profiles" in str(statement):
            triggered = True
            await svc.autofill_requisites_after_key_saved(
                tenant_id, seller_id, marketplace="wb"
            )
        return result

    monkeypatch.setattr(AsyncSession, "scalar", patched_scalar)

    put_response = await async_client.put(
        f"/billing/profiles/sellers/{seller_id}",
        headers=owner_headers,
        json={"legal_name": manual_legal_name, "inn": manual_inn},
    )
    assert put_response.status_code == 200, put_response.text
    assert put_response.json()["legal_name"] == manual_legal_name
    assert put_response.json()["inn"] == manual_inn
    assert triggered  # гонка действительно сработала, а не тест-заглушка

    profiles = await _all_profiles(tenant_id, seller_id)
    assert len(profiles) == 1
    assert profiles[0].legal_name == manual_legal_name
    assert profiles[0].inn == manual_inn
