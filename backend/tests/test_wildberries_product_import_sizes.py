"""WB import: one Product per size barcode."""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi import BackgroundTasks
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.tokens import decode_access_token


@pytest.mark.asyncio
async def test_self_sync_creates_product_per_size(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Sizes Co",
            "slug": f"sizes-{suffix}",
            "admin_email": f"sizes-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sid = (await async_client.post("/sellers", headers=ah, json={"name": "Leggings IP"})).json()[
        "id"
    ]

    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"sizes-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert acc.status_code in (200, 201)
    login = await async_client.post(
        "/auth/login",
        json={"email": f"sizes-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    card = {
        "nmID": 900100,
        "vendorCode": "LEG-STRIP",
        "title": "Лосины",
        "sizes": [
            {"chrtID": 1, "techSize": "S", "skus": ["1110000000001"]},
            {"chrtID": 2, "techSize": "M", "skus": ["1110000000002"]},
            {"chrtID": 3, "techSize": "L", "skus": ["1110000000003"]},
        ],
    }

    async def fake_fetch(*args: object, **kwargs: object) -> dict[str, object]:
        return {"cards": [card], "cursor": {"total": 1}}

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch,
    )

    await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=ah,
        json={"content_api_token": "wb-content-test"},
    )

    sync = await async_client.post("/integrations/wildberries/self/sync-products", headers=sh)
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["products_created"] == 3

    cat = await async_client.get("/products/wb-catalog", headers=sh)
    assert cat.status_code == 200
    rows = cat.json()
    assert len(rows) == 3
    by_size = {r["wb_size"]: r for r in rows}
    assert set(by_size) == {"S", "M", "L"}
    assert by_size["S"]["wb_primary_barcode"] == "1110000000001"
    assert by_size["M"]["wb_barcodes"] == ["1110000000002"]
    assert by_size["L"]["sku_code"] == "LEG-STRIP/L"

    plist = await async_client.get("/products", headers=ah)
    seller_products = [p for p in plist.json() if p.get("seller_id") == sid]
    assert len(seller_products) == 3


@pytest.mark.asyncio
async def test_self_content_token_skips_packhub_duplicate_sku_conflict_idempotently(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "ПакХаб",
            "slug": f"packhub-{suffix}",
            "admin_email": f"packhub-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {token}"}
    seller = await async_client.post("/sellers", headers=ah, json={"name": "ПакХаб"})
    assert seller.status_code == 201
    seller_id = uuid.UUID(seller.json()["id"])

    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": str(seller_id),
            "email": f"packhub-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={
            "email": f"packhub-seller-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert login.status_code == 200
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    nm_id = 1_276_652_376
    chrt_id = 1_880_410_906
    size_first = "L (\u041e\u042276-\u041e\u0411100)"
    size_second = "L (\u041e\u042276-\u041e\u0411102)"
    sku_first = f"Trous_BluVelvet/{size_first}"
    sku_second = f"Trous_BluVelvet/{size_second}"
    barcode_first = "4680641920712"
    barcode_second = "2053555590289"
    async with SessionLocal() as session:
        session.add_all(
            [
                Product(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    name="Trous Blu Velvet first",
                    sku_code=sku_first,
                    wb_nm_id=nm_id,
                    wb_vendor_code="Trous_BluVelvet",
                    wb_chrt_id=chrt_id,
                    wb_barcode=barcode_first,
                    wb_size=size_first,
                    length_mm=10,
                    width_mm=10,
                    height_mm=10,
                ),
                Product(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    name="Trous Blu Velvet second",
                    sku_code=sku_second,
                    wb_nm_id=nm_id,
                    wb_vendor_code="Trous_BluVelvet",
                    wb_chrt_id=chrt_id,
                    wb_barcode=barcode_second,
                    wb_size=size_second,
                    length_mm=10,
                    width_mm=10,
                    height_mm=10,
                ),
            ]
        )
        await session.commit()

    card = {
        "nmID": nm_id,
        "vendorCode": "Trous_BluVelvet",
        "title": "Trous Blu Velvet",
        "sizes": [
            {
                "chrtID": chrt_id,
                "techSize": size_second,
                "skus": [barcode_first],
            },
            {
                "chrtID": chrt_id,
                "techSize": size_second,
                "skus": [barcode_second],
            },
        ],
    }

    async def fake_fetch_cards_list(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"cards": [card], "cursor": {"total": 1}}

    async def noop_sync_task(*_args: object, **_kwargs: object) -> None:
        return None

    def noop_add_task(self: BackgroundTasks, *args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "app.api.wildberries_integration.fetch_cards_list",
        fake_fetch_cards_list,
    )
    monkeypatch.setattr(
        "app.services.wb_mp_warehouse_service.run_wb_mp_warehouses_sync_task",
        noop_sync_task,
    )
    monkeypatch.setattr(BackgroundTasks, "add_task", noop_add_task)

    first = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=sh,
        json={"content_api_token": "packhub-wb-key"},
    )
    second = await async_client.post(
        "/integrations/wildberries/self/content-token",
        headers=sh,
        json={"content_api_token": "packhub-wb-key"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    expected = {
        "ok": True,
        "validation_ok": True,
        "validation_error": None,
        "cards_received": 1,
        "cards_saved": 1,
        "products_created": 0,
        "products_updated": 1,
        "products_skipped": 1,
    }
    assert first.json() == expected
    assert second.json() == expected

    imported = await async_client.get(
        f"/integrations/wildberries/sellers/{seller_id}/imported-cards",
        headers=ah,
    )
    assert imported.status_code == 200
    assert imported.json()[0]["nm_id"] == nm_id
