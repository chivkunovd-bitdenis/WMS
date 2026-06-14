"""WB import: one Product per size barcode."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


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
