from __future__ import annotations

import time
import uuid

import pytest
from fastapi import BackgroundTasks
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.services.tokens import decode_access_token
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_credentials_service import (
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)


async def _create_authenticated_seller(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Token Failure Test",
            "slug": f"wbt-failure-{suffix}",
            "admin_email": f"wbt-failure-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": "Failure test seller"},
    )
    assert seller.status_code == 201
    seller_id = uuid.UUID(seller.json()["id"])
    seller_email = f"wbt-failure-seller-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={
            "seller_id": str(seller_id),
            "email": seller_email,
            "password": "password123",
        },
    )
    assert account.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return seller_headers, tenant_id, seller_id


@pytest.mark.asyncio
async def test_wb_tokens_get_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{uuid.uuid4()}/tokens",
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wb_tokens_forbidden_for_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co",
            "slug": f"wbt-{suffix}",
            "admin_email": f"wbt-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    sid = s.json()["id"]
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"wbt-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"wbt-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await async_client.get(f"/integrations/wildberries/sellers/{sid}/tokens", headers=sh)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wb_tokens_patch_get_roundtrip_and_clear(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co2",
            "slug": f"wbt2-{suffix}",
            "admin_email": f"wbt2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {token}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S2"})
    sid = uuid.UUID(s.json()["id"])

    g0 = await async_client.get(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
    )
    assert g0.status_code == 200
    assert g0.json()["has_content_token"] is False
    assert g0.json()["has_supplies_token"] is False

    p1 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "  secret-content  ", "supplies_api_token": "supp-1"},
    )
    assert p1.status_code == 200
    b1 = p1.json()
    assert b1["has_content_token"] is True
    assert b1["has_supplies_token"] is True
    # marketplace_api_token не был передан в патче, но поле маркетплейс-токена было
    # пустым (первое сохранение) -> один ключ на всё, контентный ключ подставляется
    # и туда.
    assert b1["has_marketplace_token"] is True

    async with SessionLocal() as session:
        pair = await get_decrypted_tokens_for_seller(session, tenant_id, sid)
        marketplace = await get_decrypted_marketplace_token(session, tenant_id, sid)
    assert pair is not None
    c, sup = pair
    assert c == "secret-content"
    assert sup == "supp-1"
    assert marketplace == "secret-content"

    g1 = await async_client.get(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
    )
    assert "secret" not in g1.text

    p2 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": None},
    )
    assert p2.status_code == 200
    assert p2.json()["has_content_token"] is False
    assert p2.json()["has_supplies_token"] is True
    # Маркетплейс-токен уже был установлен (из p1) -> очистка контентного поля его
    # не трогает: SKIP значит "не менять", а не "стереть, если контент стал пустым".
    assert p2.json()["has_marketplace_token"] is True


@pytest.mark.asyncio
async def test_seller_single_wb_key_also_enables_marketplace_token(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [], "cursor": {"total": 0}}

    async def fake_fetch_marketplace_seller_warehouses(
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fake_fetch_marketplace_seller_warehouses,
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Self",
            "slug": f"wbt-self-{suffix}",
            "admin_email": f"wbt-self-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post("/sellers", headers=ah, json={"name": "S self"})
    seller_id = uuid.UUID(seller.json()["id"])
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": str(seller_id),
            "email": f"wbt-self-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"wbt-self-seller-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    save = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=sh,
        json={"content_api_token": "  one-wb-key  "},
    )
    assert save.status_code == 200, save.text

    status = await async_client.get("/integrations/wildberries/self/tokens", headers=sh)
    assert status.status_code == 200
    assert status.json()["has_content_token"] is True
    assert status.json()["has_marketplace_token"] is True

    async with SessionLocal() as session:
        content, _supplies = await get_decrypted_tokens_for_seller(
            session, tenant_id, seller_id
        ) or (None, None)
        marketplace = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    assert content == "one-wb-key"
    assert marketplace == "one-wb-key"


@pytest.mark.asyncio
async def test_self_content_token_does_not_enable_marketplace_without_scope(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [{"nmID": 301}], "cursor": {"total": 1}}

    async def fail_fetch_marketplace_seller_warehouses(
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        raise WildberriesClientError("upstream_error", status_code=401)

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fail_fetch_marketplace_seller_warehouses,
    )
    headers, tenant_id, seller_id = await _create_authenticated_seller(async_client)

    response = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "content-only-wb-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_ok"] is False
    assert body["validation_error"] == "missing_marketplace_scope"
    assert body["cards_received"] == 1
    async with SessionLocal() as session:
        content, supplies = await get_decrypted_tokens_for_seller(
            session, tenant_id, seller_id
        ) or (None, None)
        marketplace = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    assert content == "content-only-wb-key"
    assert supplies is None
    assert marketplace is None


@pytest.mark.asyncio
async def test_self_content_token_keeps_200_when_marketplace_validation_unavailable(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [{"nmID": 302}], "cursor": {"total": 1}}

    async def fail_fetch_marketplace_seller_warehouses(
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        raise WildberriesClientError("upstream_error", status_code=502)

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fail_fetch_marketplace_seller_warehouses,
    )
    headers, _tenant_id, _seller_id = await _create_authenticated_seller(async_client)

    response = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "temporarily-unchecked-wb-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_ok"] is False
    assert body["validation_error"] == "marketplace_upstream_error_502"


@pytest.mark.asyncio
async def test_self_content_token_returns_traced_error_when_task_registration_fails(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "cards": [{"nmID": 101}, {"nmID": 102}],
            "cursor": {"total": 2},
        }

    async def fake_fetch_marketplace_seller_warehouses(
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        return []

    def fail_add_task(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("background task registration failed")

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fake_fetch_marketplace_seller_warehouses,
    )
    monkeypatch.setattr(BackgroundTasks, "add_task", fail_add_task)
    caplog.set_level("ERROR", logger="app.api.wildberries_integration")
    headers, tenant_id, seller_id = await _create_authenticated_seller(async_client)

    response = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "one-wb-key"},
    )

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"code", "message", "ref"}
    assert body["code"] == "token_save_failed"
    assert "Wildberries" in body["message"]
    assert len(body["ref"]) == 12
    int(body["ref"], 16)
    log_text = caplog.text
    assert f"ref={body['ref']}" in log_text
    assert f"tenant_id={tenant_id}" in log_text
    assert f"seller_id={seller_id}" in log_text
    assert "cards_count=2" in log_text
    assert "exception_type=RuntimeError" in log_text
    assert "one-wb-key" not in log_text


@pytest.mark.asyncio
async def test_self_content_token_returns_product_conflict_for_integrity_error(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [{"nmID": 201}], "cursor": {"total": 1}}

    async def fake_fetch_marketplace_seller_warehouses(
        *_args: object,
        **_kwargs: object,
    ) -> list[dict[str, object]]:
        return []

    async def fail_product_upsert(*_args: object, **_kwargs: object) -> dict[str, int]:
        raise IntegrityError("INSERT INTO products", {}, RuntimeError("duplicate article"))

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fake_fetch_marketplace_seller_warehouses,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.upsert_products_from_wb_cards",
        fail_product_upsert,
    )
    caplog.set_level("ERROR", logger="app.api.wildberries_integration")
    headers, tenant_id, seller_id = await _create_authenticated_seller(async_client)

    response = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "conflict-wb-key"},
    )

    assert response.status_code == 409
    body = response.json()
    assert set(body) == {"code", "message", "ref"}
    assert body["code"] == "product_conflict"
    assert "конфликт артикулов" in body["message"]
    assert len(body["ref"]) == 12
    int(body["ref"], 16)
    log_text = caplog.text
    assert f"ref={body['ref']}" in log_text
    assert f"tenant_id={tenant_id}" in log_text
    assert f"seller_id={seller_id}" in log_text
    assert "cards_count=1" in log_text
    assert "exception_type=IntegrityError" in log_text
    assert "conflict-wb-key" not in log_text


@pytest.mark.asyncio
async def test_self_content_token_maps_invalid_wb_json_to_bad_gateway(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise WildberriesClientError("invalid_json")

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fail_fetch_cards_list,
    )
    headers, _tenant_id, _seller_id = await _create_authenticated_seller(async_client)

    response = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "invalid-json-wb-key"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "invalid_json"


@pytest.mark.asyncio
async def test_wb_tokens_patch_validation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co3",
            "slug": f"wbt3-{suffix}",
            "admin_email": f"wbt3-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S3"})
    sid = s.json()["id"]

    r = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={},
    )
    assert r.status_code == 422

    r2 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "   "},
    )
    assert r2.status_code == 422
    assert r2.json()["detail"] == "token_empty"

    r3 = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "ok", "extra": 1},
    )
    assert r3.status_code == 422


@pytest.mark.asyncio
async def test_wb_tokens_seller_not_found(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Tok Co4",
            "slug": f"wbt4-{suffix}",
            "admin_email": f"wbt4-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    missing = uuid.UUID("00000000-0000-4000-8000-000000000099")
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{missing}/tokens",
        headers=ah,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_self_content_token_failed_marketplace_check_preserves_existing_marketplace_token(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: неудачная проверка доступа к Marketplace API не должна стирать уже
    рабочий маркетплейс-токен. До фикса `patch_seller_tokens` вызывался с
    `marketplace_api_token=None` при провале проверки, что безусловно стирало любой ранее
    сохранённый маркетплейс-ключ — даже полностью рабочий."""

    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [], "cursor": {"total": 0}}

    async def ok_fetch_marketplace_seller_warehouses(
        *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        return []

    async def fail_fetch_marketplace_seller_warehouses(
        *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        raise WildberriesClientError("upstream_error", status_code=401)

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )

    headers, tenant_id, seller_id = await _create_authenticated_seller(async_client)

    # Шаг 1: селлер сохраняет ключ с областью "Маркетплейс" -> маркетплейс-токен сохраняется.
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        ok_fetch_marketplace_seller_warehouses,
    )
    first = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "working-marketplace-key"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["validation_ok"] is True

    async with SessionLocal() as session:
        marketplace_before = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    assert marketplace_before == "working-marketplace-key"

    # Шаг 2: селлер пересохраняет только контентный ключ; проверка доступа к Marketplace API
    # падает (например, WB отдал таймаут или у ключа нет нужной области). Ранее сохранённый
    # рабочий маркетплейс-токен обязан выжить нетронутым.
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fail_fetch_marketplace_seller_warehouses,
    )
    second = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "new-content-only-key"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["validation_ok"] is False
    assert second.json()["validation_error"] == "missing_marketplace_scope"

    async with SessionLocal() as session:
        content_after, _supplies_after = await get_decrypted_tokens_for_seller(
            session, tenant_id, seller_id
        ) or (None, None)
        marketplace_after = await get_decrypted_marketplace_token(session, tenant_id, seller_id)

    assert content_after == "new-content-only-key"
    assert marketplace_after == "working-marketplace-key"


@pytest.mark.asyncio
async def test_legacy_content_only_credentials_still_serve_marketplace_calls(
    async_client: AsyncClient,
) -> None:
    """Старая запись с одним контентным ключом обязана работать на приём заказов.

    Автоопрос берёт селлера в работу, если есть любой из двух ключей, а заказы
    грузились только по маркетплейс-ключу. У записей, заведённых до правила
    «один ключ на всё», это поле пустое — и заказы FBS молча не приезжали.
    """
    from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
    from app.services.wildberries_credentials_service import (
        encrypt_secret,
        get_decrypted_marketplace_token,
    )

    _headers, tenant_id, seller_id = await _create_authenticated_seller(async_client)
    async with SessionLocal() as session:
        row = await session.get(SellerWildberriesCredentials, seller_id)
        if row is None:
            row = SellerWildberriesCredentials(seller_id=seller_id)
            session.add(row)
        row.content_token_encrypted = encrypt_secret("legacy-content-key")
        row.marketplace_token_encrypted = None
        row.marketplace_scope_ok = None
        await session.commit()

    async with SessionLocal() as session:
        token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    assert token == "legacy-content-key"
