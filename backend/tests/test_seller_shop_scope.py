from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.services.tokens import create_access_token, decode_access_token


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    sku_code: str,
    seller_id: str,
) -> str:
    resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": name,
            "sku_code": sku_code,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["id"])


@pytest.mark.asyncio
async def test_shop_manager_scope_requires_enabled_delegation_for_products(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))

    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Seller Scope Co",
            "slug": f"seller-scope-{suffix}",
            "admin_email": f"scope-admin-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    home = await async_client.post(
        "/sellers/with-account",
        headers=admin_headers,
        json={
            "name": "Seller A Home",
            "email": f"vitalik-home-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert home.status_code == 201, home.text
    seller_a = str(home.json()["seller_id"])

    seller_b_resp = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": "Seller B Delegated"},
    )
    assert seller_b_resp.status_code == 201, seller_b_resp.text
    seller_b = str(seller_b_resp.json()["id"])

    seller_c_resp = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": "Seller C Forbidden"},
    )
    assert seller_c_resp.status_code == 201, seller_c_resp.text
    seller_c = str(seller_c_resp.json()["id"])

    product_a = await _create_product(
        async_client,
        admin_headers,
        name="Product A Own",
        sku_code=f"SCOPE-A-{suffix}",
        seller_id=seller_a,
    )
    product_b = await _create_product(
        async_client,
        admin_headers,
        name="Product B Delegated",
        sku_code=f"SCOPE-B-{suffix}",
        seller_id=seller_b,
    )
    product_c = await _create_product(
        async_client,
        admin_headers,
        name="Product C Forbidden",
        sku_code=f"SCOPE-C-{suffix}",
        seller_id=seller_c,
    )

    login = await async_client.post(
        "/auth/login",
        json={"email": f"vitalik-home-{suffix}@mail.ru", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    home_token = str(login.json()["access_token"])
    seller_headers = {"Authorization": f"Bearer {home_token}"}

    me = await async_client.get("/auth/me", headers=seller_headers)
    assert me.status_code == 200, me.text
    assert me.json()["can_manage_seller_shops"] is True
    assert me.json()["active_seller_id"] == seller_a
    assert {row["id"] for row in me.json()["switchable_shops"]} == {seller_a}

    update = await async_client.put(
        "/auth/seller-shops",
        headers=seller_headers,
        json={"enabled_seller_ids": [seller_b]},
    )
    assert update.status_code == 200, update.text

    switch_b = await async_client.post(
        "/auth/switch-seller",
        headers=seller_headers,
        json={"seller_id": seller_b},
    )
    assert switch_b.status_code == 200, switch_b.text
    seller_b_headers = {"Authorization": f"Bearer {switch_b.json()['access_token']}"}

    me_b = await async_client.get("/auth/me", headers=seller_b_headers)
    assert me_b.status_code == 200, me_b.text
    assert me_b.json()["active_seller_id"] == seller_b
    assert {row["id"] for row in me_b.json()["switchable_shops"]} == {
        seller_a,
        seller_b,
    }

    switch_c = await async_client.post(
        "/auth/switch-seller",
        headers=seller_headers,
        json={"seller_id": seller_c},
    )
    assert switch_c.status_code == 403, switch_c.text

    home_payload = decode_access_token(home_token)
    forged_c_token = create_access_token(
        user_id=uuid.UUID(home_payload["sub"]),
        tenant_id=uuid.UUID(home_payload["tenant_id"]),
        role=home_payload["role"],
        seller_id=uuid.UUID(seller_c),
    )
    forged_c_headers = {"Authorization": f"Bearer {forged_c_token}"}
    forged_me = await async_client.get("/auth/me", headers=forged_c_headers)
    assert forged_me.status_code == 403, forged_me.text
    forged_products = await async_client.get("/products", headers=forged_c_headers)
    assert forged_products.status_code == 403, forged_products.text

    products = await async_client.get("/products", headers=seller_b_headers)
    assert products.status_code == 200, products.text
    product_ids = {row["id"] for row in products.json()}
    assert product_b in product_ids
    assert product_a not in product_ids
    assert product_c not in product_ids

    wb_catalog = await async_client.get("/products/wb-catalog", headers=seller_b_headers)
    assert wb_catalog.status_code == 200, wb_catalog.text
    wb_product_ids = {row["id"] for row in wb_catalog.json()}
    assert product_b in wb_product_ids
    assert product_a not in wb_product_ids
    assert product_c not in wb_product_ids
