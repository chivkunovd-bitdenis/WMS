from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _register_admin(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Ozon catalog {suffix}",
            "slug": f"ozon-catalog-{suffix}",
            "admin_email": f"ozon-catalog-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    sku_code: str,
    seller_id: str,
    ozon_sku: str | None = None,
    ozon_offer_id: str | None = None,
    wb_vendor_code: str | None = None,
) -> dict[str, object]:
    response = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku_code,
            "seller_id": seller_id,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "ozon_sku": ozon_sku,
            "ozon_offer_id": ozon_offer_id,
            "wb_vendor_code": wb_vendor_code,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_products_search_and_marketplace_filter_include_ozon_links(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller Ozon"})
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    linked = await _create_product(
        async_client,
        headers,
        name="Ozon linked product",
        sku_code=f"LOCAL-{suffix}",
        seller_id=seller_id,
        ozon_sku=f"OZON-SKU-{suffix}",
        ozon_offer_id=f"OZON-OFFER-{suffix}",
        wb_vendor_code=f"WB-{suffix}",
    )
    unlinked = await _create_product(
        async_client,
        headers,
        name="Product without marketplace mapping",
        sku_code=f"UNLINKED-{suffix}",
        seller_id=seller_id,
    )

    by_ozon_sku = await async_client.get(
        f"/products?search=OZON-SKU-{suffix}", headers=headers
    )
    assert by_ozon_sku.status_code == 200, by_ozon_sku.text
    assert [row["id"] for row in by_ozon_sku.json()] == [linked["id"]]
    assert by_ozon_sku.json()[0]["ozon_offer_id"] == f"OZON-OFFER-{suffix}"

    by_ozon_offer = await async_client.get(
        f"/products?search=OZON-OFFER-{suffix}", headers=headers
    )
    assert by_ozon_offer.status_code == 200, by_ozon_offer.text
    assert [row["id"] for row in by_ozon_offer.json()] == [linked["id"]]

    ozon_only = await async_client.get("/products?marketplace=ozon", headers=headers)
    assert ozon_only.status_code == 200, ozon_only.text
    assert {row["id"] for row in ozon_only.json()} == {linked["id"]}

    wb_only = await async_client.get("/products?marketplace=wildberries", headers=headers)
    assert wb_only.status_code == 200, wb_only.text
    assert {row["id"] for row in wb_only.json()} == {linked["id"]}

    all_products = await async_client.get("/products", headers=headers)
    assert all_products.status_code == 200, all_products.text
    unlinked_row = next(row for row in all_products.json() if row["id"] == unlinked["id"])
    assert unlinked_row["ozon_sku"] is None
    assert unlinked_row["ozon_offer_id"] is None


@pytest.mark.asyncio
async def test_ozon_catalog_links_do_not_cross_seller_or_tenant_boundaries(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    owner_headers = await _register_admin(async_client, f"owner-{suffix}")
    seller_a = await async_client.post("/sellers", headers=owner_headers, json={"name": "A"})
    seller_b = await async_client.post("/sellers", headers=owner_headers, json={"name": "B"})
    assert seller_a.status_code == seller_b.status_code == 201
    seller_a_id = seller_a.json()["id"]
    seller_b_id = seller_b.json()["id"]
    product_a = await _create_product(
        async_client,
        owner_headers,
        name="Seller A Ozon",
        sku_code=f"A-{suffix}",
        seller_id=seller_a_id,
        ozon_sku=f"ISOLATED-{suffix}",
    )
    await _create_product(
        async_client,
        owner_headers,
        name="Seller B Ozon",
        sku_code=f"B-{suffix}",
        seller_id=seller_b_id,
        ozon_sku=f"ISOLATED-{suffix}",
    )

    seller_account = await async_client.post(
        "/auth/seller-accounts",
        headers=owner_headers,
        json={
            "seller_id": seller_a_id,
            "email": f"seller-a-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert seller_account.status_code in (200, 201), seller_account.text
    login = await async_client.post(
        "/auth/login",
        json={"email": f"seller-a-{suffix}@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    seller_products = await async_client.get(
        f"/products?search=ISOLATED-{suffix}", headers=seller_headers
    )
    assert seller_products.status_code == 200, seller_products.text
    assert [row["id"] for row in seller_products.json()] == [product_a["id"]]

    other_headers = await _register_admin(async_client, f"other-{suffix}")
    other_products = await async_client.get(
        f"/products?search=ISOLATED-{suffix}", headers=other_headers
    )
    assert other_products.status_code == 200, other_products.text
    assert other_products.json() == []
