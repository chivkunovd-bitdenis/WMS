from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_fbs_stock_sync_bulk_does_not_touch_other_seller_products(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FBS Bulk Scope",
            "slug": f"fbs-bulk-{suffix}",
            "admin_email": f"fbs-bulk-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller_a = await async_client.post("/sellers", headers=admin_headers, json={"name": "Seller A"})
    seller_b = await async_client.post("/sellers", headers=admin_headers, json={"name": "Seller B"})
    seller_a_id = seller_a.json()["id"]
    seller_b_id = seller_b.json()["id"]

    product_a = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Product A",
            "sku_code": f"FBS-A-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_a_id,
        },
    )
    product_b = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Product B",
            "sku_code": f"FBS-B-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_b_id,
        },
    )
    product_a_id = product_a.json()["id"]
    product_b_id = product_b.json()["id"]

    seller_email = f"fbs-bulk-seller-{suffix}@example.com"
    created_account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_a_id, "email": seller_email, "password": "password123"},
    )
    assert created_account.status_code in (200, 201)
    seller_login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    seller_headers = {"Authorization": f"Bearer {seller_login.json()['access_token']}"}

    patched = await async_client.patch(
        "/products/fbs-stock-sync/bulk",
        headers=seller_headers,
        json={
            "product_ids": [product_a_id, product_b_id],
            "fbs_stock_sync_enabled": True,
            "fbs_stock_limit": 30,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["updated_count"] == 1

    ff_catalog = await async_client.get("/products/ff-catalog", headers=admin_headers)
    assert ff_catalog.status_code == 200
    rows = ff_catalog.json()
    row_a = next(row for row in rows if row["id"] == product_a_id)
    row_b = next(row for row in rows if row["id"] == product_b_id)

    assert row_a["fbs_stock_sync_enabled"] is True
    assert row_a["fbs_stock_limit"] == 30
    assert row_b["fbs_stock_sync_enabled"] is False
    assert row_b["fbs_stock_limit"] is None


@pytest.mark.asyncio
async def test_fbs_stock_sync_bulk_keeps_per_product_limits(
    async_client: AsyncClient,
) -> None:
    """«Включить всем» не должно стирать лимиты, расставленные поштучно.

    Селлер выставляет лимит на одном товаре, потом жмёт массовое включение без лимита.
    Лимит обязан пережить эту операцию, иначе кнопка молча ломает настройку селлера.
    """
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FBS Bulk Limits",
            "slug": f"fbs-lim-{suffix}",
            "admin_email": f"fbs-lim-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Seller L"})
    seller_id = seller.json()["id"]

    product_ids = []
    for index in (1, 2):
        created = await async_client.post(
            "/products",
            headers=admin_headers,
            json={
                "name": f"Product L{index}",
                "sku_code": f"FBS-L{index}-{suffix}",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "seller_id": seller_id,
            },
        )
        product_ids.append(created.json()["id"])
    limited_id, plain_id = product_ids

    seller_email = f"fbs-lim-seller-{suffix}@example.com"
    created_account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": seller_email, "password": "password123"},
    )
    assert created_account.status_code in (200, 201)
    seller_login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    seller_headers = {"Authorization": f"Bearer {seller_login.json()['access_token']}"}

    limited = await async_client.patch(
        f"/products/{limited_id}/fbs-stock-sync",
        headers=seller_headers,
        json={"fbs_stock_sync_enabled": True, "fbs_stock_limit": 25},
    )
    assert limited.status_code == 200, limited.text

    bulk = await async_client.patch(
        "/products/fbs-stock-sync/bulk",
        headers=seller_headers,
        json={"product_ids": None, "fbs_stock_sync_enabled": True},
    )
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["updated_count"] == 2

    rows = (await async_client.get("/products/ff-catalog", headers=admin_headers)).json()
    limited_row = next(row for row in rows if row["id"] == limited_id)
    plain_row = next(row for row in rows if row["id"] == plain_id)

    assert limited_row["fbs_stock_sync_enabled"] is True
    assert limited_row["fbs_stock_limit"] == 25, "массовое включение стёрло поштучный лимит"
    assert plain_row["fbs_stock_sync_enabled"] is True
    assert plain_row["fbs_stock_limit"] is None

    # Явно переданный лимит по-прежнему применяется ко всем товарам.
    bulk_with_limit = await async_client.patch(
        "/products/fbs-stock-sync/bulk",
        headers=seller_headers,
        json={"product_ids": None, "fbs_stock_sync_enabled": True, "fbs_stock_limit": 7},
    )
    assert bulk_with_limit.status_code == 200, bulk_with_limit.text
    rows = (await async_client.get("/products/ff-catalog", headers=admin_headers)).json()
    assert all(
        row["fbs_stock_limit"] == 7 for row in rows if row["id"] in {limited_id, plain_id}
    )


@pytest.mark.asyncio
async def test_enabling_fbs_sync_publishes_stock_immediately(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Включение галочки должно отправлять остаток в WB сразу, без ожидания сверки.

    По постановке: как только селлер включил синхронизацию, количество на фулфилменте
    уходит в кабинет. Ждать ближайшего движения товара или пятиминутной фоновой сверки
    здесь нельзя: до тех пор WB продаёт по пустому остатку.
    """
    from app.services import fbs_stock_publish_service

    dispatched: list[tuple[str, str]] = []
    monkeypatch.setattr(
        fbs_stock_publish_service,
        "_dispatch",
        lambda tenant_id, seller_id: dispatched.append((str(tenant_id), str(seller_id))),
    )

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FBS Publish On Toggle",
            "slug": f"fbs-pub-{suffix}",
            "admin_email": f"fbs-pub-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller = await async_client.post("/sellers", headers=admin_headers, json={"name": "Seller P"})
    seller_id = seller.json()["id"]
    product = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": "Product P",
            "sku_code": f"FBS-P-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = product.json()["id"]

    seller_email = f"fbs-pub-seller-{suffix}@example.com"
    created_account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": seller_email, "password": "password123"},
    )
    assert created_account.status_code in (200, 201)
    seller_login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    seller_headers = {"Authorization": f"Bearer {seller_login.json()['access_token']}"}

    dispatched.clear()
    toggled = await async_client.patch(
        f"/products/{product_id}/fbs-stock-sync",
        headers=seller_headers,
        json={"fbs_stock_sync_enabled": True},
    )
    assert toggled.status_code == 200, toggled.text
    assert [entry[1] for entry in dispatched] == [seller_id], (
        "включение галочки не поставило публикацию остатка в очередь"
    )

    # Выключение тоже обязано уехать: WB должен получить ноль вместо старой цифры.
    dispatched.clear()
    disabled = await async_client.patch(
        f"/products/{product_id}/fbs-stock-sync",
        headers=seller_headers,
        json={"fbs_stock_sync_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert [entry[1] for entry in dispatched] == [seller_id]

    # Массовое переключение даёт одну публикацию на селлера, не по одной на товар.
    dispatched.clear()
    bulk = await async_client.patch(
        "/products/fbs-stock-sync/bulk",
        headers=seller_headers,
        json={"product_ids": None, "fbs_stock_sync_enabled": True},
    )
    assert bulk.status_code == 200, bulk.text
    assert [entry[1] for entry in dispatched] == [seller_id]
