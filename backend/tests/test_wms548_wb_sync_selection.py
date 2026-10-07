"""WMS-548 D1: сохранение WB-ключа и синхронизация не заводят невыбранные товары.

R4 — сохранение ключа (self/content-token) обновляет снимок карточек, но не
создаёт ни одного товара WMS для карточек, которых ещё нет на фулфилменте.
R5 — синхронизация (self/sync-products и почасовой проход) обновляет и заводит
новые размеры только у уже выбранных карточек; невыбранные и новые карточки
товарами не становятся, но снимок по ним обновляется.
А3 — второго независимого флага выбора нет: карточка выбрана тогда и только
тогда, когда у товаров этого селлера уже есть Product с её nmID.
"""

from __future__ import annotations

import uuid
from functools import partial

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.tenant import Tenant
from app.services import wildberries_product_sync_service as sync_module
from app.services.integration_fernet import encrypt_secret
from app.services.tokens import decode_access_token


async def _create_authenticated_seller(
    async_client: AsyncClient,
) -> tuple[dict[str, str], dict[str, str], uuid.UUID, uuid.UUID]:
    """Регистрирует тенант с админом и одним селлером с собственным входом."""
    suffix = uuid.uuid4().hex
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WMS548 D1",
            "slug": f"wms548-d1-{suffix}",
            "admin_email": f"wms548-d1-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": f"WMS548 seller {suffix}"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(seller.json()["id"])
    seller_email = f"wms548-d1-seller-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": str(seller_id), "email": seller_email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    login = await async_client.post(
        "/auth/login", json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return seller_headers, admin_headers, tenant_id, seller_id


async def _seller_with_token(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, token: str,
) -> Seller:
    seller = Seller(tenant_id=tenant_id, name=name)
    session.add(seller)
    await session.flush()
    session.add(SellerWildberriesCredentials(
        seller_id=seller.id,
        content_token_encrypted=encrypt_secret(token),
        marketplace_scope_ok=False,
    ))
    await session.commit()
    return seller


async def _product_count(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID,
) -> int:
    return int(
        await session.scalar(
            select(func.count(Product.id)).where(
                Product.tenant_id == tenant_id, Product.seller_id == seller_id,
            )
        )
        or 0
    )


@pytest.mark.asyncio
async def test_self_content_token_save_records_snapshot_without_creating_products(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "cards": [
                {
                    "nmID": 501, "vendorCode": "WMS548-501", "title": "Товар 501",
                    "sizes": [{"chrtID": 1, "techSize": "0", "skus": ["5010000000001"]}],
                },
                {
                    "nmID": 502, "vendorCode": "WMS548-502", "title": "Товар 502",
                    "sizes": [
                        {"chrtID": 2, "techSize": "S", "skus": ["5020000000001"]},
                        {"chrtID": 3, "techSize": "M", "skus": ["5020000000002"]},
                    ],
                },
            ],
            "cursor": {"total": 2},
        }

    async def fake_fetch_marketplace_seller_warehouses(
        *_args: object, **_kwargs: object,
    ) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_cards_list", fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_marketplace_seller_warehouses",
        fake_fetch_marketplace_seller_warehouses,
    )

    headers, admin_headers, tenant_id, seller_id = await _create_authenticated_seller(
        async_client,
    )

    save = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=headers,
        json={"content_api_token": "wms548-fresh-key"},
    )
    assert save.status_code == 200, save.text
    body = save.json()
    assert body["validation_ok"] is True
    assert body["cards_received"] == 0
    assert body["cards_saved"] == 0
    assert body["products_created"] == 0
    assert body["products_updated"] == 0
    assert body["products_skipped"] == 0
    assert body["catalog_job"]["state"] == "queued"
    job = await async_client.get(
        f"/operations/background-jobs/{body['catalog_job']['id']}", headers=headers
    )
    assert job.status_code == 200
    assert job.json()["state"] == "succeeded"
    assert job.json()["result_json"]["cards_received"] == 2
    assert job.json()["result_json"]["cards_saved"] == 2

    async with SessionLocal() as session:
        assert await _product_count(session, tenant_id, seller_id) == 0

    imported = await async_client.get(
        f"/integrations/wildberries/sellers/{seller_id}/imported-cards",
        headers=admin_headers,
    )
    assert imported.status_code == 200
    assert {c["nm_id"] for c in imported.json()} == {501, 502}

    catalog = await async_client.get("/products/wb-catalog", headers=headers)
    assert catalog.status_code == 200
    assert catalog.json() == []


@pytest.mark.asyncio
async def test_sync_updates_only_selected_card_adds_new_size_leaves_others_untouched(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, admin_headers, tenant_id, seller_id = await _create_authenticated_seller(
        async_client,
    )

    # Карточка 601 уже "на фулфилменте": у неё есть Product с этим nmID —
    # второго независимого флага выбора нет (WMS-548 А3).
    async with SessionLocal() as session:
        await sync_module.upsert_products_from_wb_cards(session, tenant_id, seller_id, [{
            "nmID": 601, "vendorCode": "WMS548-601", "title": "Товар 601 (старое имя)",
            "sizes": [{"chrtID": 11, "techSize": "S", "skus": ["6010000000001"]}],
        }])

    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "cards": [
                # Карточка 601: переименована и получила новый размер M.
                {
                    "nmID": 601, "vendorCode": "WMS548-601",
                    "title": "Товар 601 (новое имя)",
                    "sizes": [
                        {"chrtID": 11, "techSize": "S", "skus": ["6010000000001"]},
                        {"chrtID": 12, "techSize": "M", "skus": ["6010000000002"]},
                    ],
                },
                # Карточка 602: никогда не выбиралась, но WB её тоже переименовал.
                {
                    "nmID": 602, "vendorCode": "WMS548-602",
                    "title": "Товар 602 (новое имя)",
                    "sizes": [{"chrtID": 13, "techSize": "0", "skus": ["6020000000001"]}],
                },
                # Карточка 603: появилась на WB уже после сохранения ключа.
                {
                    "nmID": 603, "vendorCode": "WMS548-603", "title": "Товар 603",
                    "sizes": [{"chrtID": 14, "techSize": "0", "skus": ["6030000000001"]}],
                },
            ],
            "cursor": {"total": 3},
        }

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_cards_list", fake_fetch_cards_list,
    )

    # Обычное сохранение токена фулфилментом карточки не тянет.
    await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=admin_headers,
        json={"content_api_token": "wms548-sync-key"},
    )

    sync = await async_client.post(
        "/integrations/wildberries/self/sync-products", headers=headers,
    )
    assert sync.status_code == 202, sync.text
    job = await async_client.get(
        f"/operations/background-jobs/{sync.json()['id']}", headers=headers
    )
    assert job.status_code == 200
    body = job.json()["result_json"]
    assert job.json()["state"] == "succeeded"
    assert body["cards_received"] == 3
    assert body["cards_saved"] == 3
    assert body["products_created"] == 1  # новый размер M у выбранной карточки
    assert body["products_updated"] == 1  # переименованный размер S
    assert body["products_skipped"] == 0

    async with SessionLocal() as session:
        products = list(
            (
                await session.scalars(
                    select(Product).where(
                        Product.tenant_id == tenant_id, Product.seller_id == seller_id,
                    )
                )
            ).all()
        )
    assert {p.wb_nm_id for p in products} == {601}
    assert {p.name for p in products} == {"Товар 601 (новое имя)"}
    assert {p.wb_size for p in products} == {"S", "M"}

    # Снимок обновился по всем трём карточкам — селлер видит актуальные данные
    # даже по невыбранным и новым, просто без товаров WMS за ними.
    imported = await async_client.get(
        f"/integrations/wildberries/sellers/{seller_id}/imported-cards",
        headers=admin_headers,
    )
    assert imported.status_code == 200
    titles = {c["nm_id"]: c["title"] for c in imported.json()}
    assert titles == {
        601: "Товар 601 (новое имя)",
        602: "Товар 602 (новое имя)",
        603: "Товар 603",
    }


@pytest.mark.asyncio
async def test_hourly_sync_selection_is_isolated_per_seller_and_tenant(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Один и тот же nmID выбран только у одного селлера одного тенанта —
    выбор селлера A не заводит товар ни у селлера B того же тенанта, ни у
    селлера C другого тенанта (WMS-548 R5, R14)."""
    tenant1 = Tenant(name="WMS548 T1", slug="wms548-d1-t1")
    tenant2 = Tenant(name="WMS548 T2", slug="wms548-d1-t2")
    db_session.add_all([tenant1, tenant2])
    await db_session.commit()

    seller_a = await _seller_with_token(db_session, tenant1.id, "A selected", "tokA")
    seller_b = await _seller_with_token(db_session, tenant1.id, "B not selected", "tokB")
    seller_c = await _seller_with_token(db_session, tenant2.id, "C other tenant", "tokC")

    # Только у A уже есть Product с этим nmID — только A "выбрал" карточку 900.
    await sync_module.upsert_products_from_wb_cards(db_session, tenant1.id, seller_a.id, [{
        "nmID": 900, "vendorCode": "WMS548-900", "title": "Совпадающий артикул",
        "sizes": [{"chrtID": 90, "techSize": "0", "skus": ["9000000000001"]}],
    }])
    await db_session.commit()

    calls: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/content/v2/get/cards/list":
            return httpx.Response(200, json={"cards": [{
                "nmID": 900, "vendorCode": "WMS548-900",
                "title": "Совпадающий артикул (обновлён)",
                "sizes": [{"chrtID": 90, "techSize": "0", "skus": ["9000000000001"]}],
            }]})
        if request.url.path == "/content/v2/object/parent/all":
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/content/v2/object/all":
            assert request.url.params == {"limit": "1000", "offset": "0"}
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected WB request: {request.method} {request.url}")

    monkeypatch.setattr(sync_module.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync_module.run_wb_products_sync_all_sellers()
    assert summary["sellers_ok"] == 3
    card_calls = [
        request for request in calls if request.url.path == "/content/v2/get/cards/list"
    ]
    parent_calls = [
        request for request in calls if request.url.path == "/content/v2/object/parent/all"
    ]
    subject_calls = [
        request for request in calls if request.url.path == "/content/v2/object/all"
    ]
    # Category requests use the same seller credentials as their card list;
    # no tenant may borrow another seller's WB token to classify its cards.
    assert sorted(request.headers["Authorization"] for request in card_calls) == [
        "tokA", "tokB", "tokC"
    ]
    assert sorted(request.headers["Authorization"] for request in parent_calls) == [
        "tokA", "tokB", "tokC"
    ]
    assert sorted(request.headers["Authorization"] for request in subject_calls) == [
        "tokA", "tokB", "tokC"
    ]

    assert await _product_count(db_session, tenant1.id, seller_a.id) == 1
    assert await _product_count(db_session, tenant1.id, seller_b.id) == 0
    assert await _product_count(db_session, tenant2.id, seller_c.id) == 0

    updated = await db_session.scalar(select(Product).where(
        Product.tenant_id == tenant1.id, Product.seller_id == seller_a.id,
    ))
    assert updated is not None
    assert updated.name == "Совпадающий артикул (обновлён)"


@pytest.mark.asyncio
async def test_hourly_sync_fully_selected_seller_matches_pre_wms548_result(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """У селлера, подключённого до выкладки задачи, весь каталог уже выбран
    (все карточки уже стали товарами) — почасовой проход должен обновлять их
    так же, как до задачи, ничего не пропуская как "невыбранное" (WMS-548 R10)."""
    tenant = Tenant(name="WMS548 full", slug="wms548-d1-full")
    db_session.add(tenant)
    await db_session.commit()
    seller = await _seller_with_token(db_session, tenant.id, "Full catalog", "tokFull")

    await sync_module.upsert_products_from_wb_cards(db_session, tenant.id, seller.id, [
        {
            "nmID": 950, "vendorCode": "WMS548-950", "title": "Товар 950",
            "sizes": [{"chrtID": 95, "techSize": "0", "skus": ["9500000000001"]}],
        },
        {
            "nmID": 951, "vendorCode": "WMS548-951", "title": "Товар 951",
            "sizes": [{"chrtID": 96, "techSize": "0", "skus": ["9510000000001"]}],
        },
    ])
    await db_session.commit()
    assert await _product_count(db_session, tenant.id, seller.id) == 2

    def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"cards": [
            {
                "nmID": 950, "vendorCode": "WMS548-950", "title": "Товар 950 (обновлён)",
                "sizes": [{"chrtID": 95, "techSize": "0", "skus": ["9500000000001"]}],
            },
            {
                "nmID": 951, "vendorCode": "WMS548-951", "title": "Товар 951",
                "sizes": [{"chrtID": 96, "techSize": "0", "skus": ["9510000000001"]}],
            },
        ]})

    monkeypatch.setattr(sync_module.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync_module.run_wb_products_sync_all_sellers()
    assert summary["sellers_ok"] == 1
    result = summary["ok"][0]
    # Ни одна карточка не исключена — весь каталог селлера уже выбран, поэтому
    # результат такой же, как до задачи: обе карточки уже были товарами, значит
    # обе идут по ветке обновления (upsert_products_from_wb_cards считает
    # «обновлено» для каждой найденной карточки, даже если поля не менялись).
    assert result["products_created"] == 0
    assert result["products_updated"] == 2
    assert result["products_skipped"] == 0

    assert await _product_count(db_session, tenant.id, seller.id) == 2
    updated = await db_session.scalar(select(Product).where(
        Product.tenant_id == tenant.id, Product.seller_id == seller.id,
        Product.wb_nm_id == 950,
    ))
    assert updated is not None and updated.name == "Товар 950 (обновлён)"
