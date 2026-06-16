from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_wb_catalog_only_own_seller_products(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Catalog Iso Co",
            "slug": f"cat-iso-{suffix}",
            "admin_email": f"cat-iso-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    s1 = await async_client.post("/sellers", headers=ah, json={"name": "Shop Alpha"})
    s2 = await async_client.post("/sellers", headers=ah, json={"name": "Shop Beta"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    own_sku = f"OWN-CAT-{suffix}"
    other_sku = f"OTH-CAT-{suffix}"
    await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Own Product",
            "sku_code": own_sku,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid1,
        },
    )
    await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Other Product",
            "sku_code": other_sku,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )

    seller_email = f"cat-iso-sl-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={"seller_id": sid1, "email": seller_email, "password": "password123"},
    )
    assert acc.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    cat = await async_client.get("/products/wb-catalog", headers=sh)
    assert cat.status_code == 200
    skus = {row["sku_code"] for row in cat.json()}
    assert own_sku in skus
    assert other_sku not in skus

    bal = await async_client.get("/operations/inventory-balances/summary", headers=sh)
    assert bal.status_code == 200
    bal_skus = {row["sku_code"] for row in bal.json()}
    assert own_sku in bal_skus or len(bal_skus) == 0
    assert other_sku not in bal_skus


@pytest.mark.asyncio
async def test_regular_seller_ignores_jwt_seller_override(
    async_client: AsyncClient,
) -> None:
    """Non-manager must not act as another seller via forged JWT seller_id."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "JWT Iso",
            "slug": f"jwt-iso-{suffix}",
            "admin_email": f"jwt-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    s1 = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    s2 = await async_client.post("/sellers", headers=ah, json={"name": "S2"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    other_sku = f"SECRET-{suffix}"
    await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Secret",
            "sku_code": other_sku,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )

    seller_email = f"jwt-sl-{suffix}@mail.ru"
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={"seller_id": sid1, "email": seller_email, "password": "password123"},
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    token = login.json()["access_token"]
    me_res = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    me_body = me_res.json()

    from app.services.tokens import create_access_token

    forged = create_access_token(
        user_id=uuid.UUID(me_body["id"]),
        tenant_id=uuid.UUID(me_body["tenant_id"]),
        role="fulfillment_seller",
        seller_id=uuid.UUID(sid2),
    )
    forged_h = {"Authorization": f"Bearer {forged}"}

    cat = await async_client.get("/products/wb-catalog", headers=forged_h)
    assert cat.status_code == 200
    skus = {row["sku_code"] for row in cat.json()}
    assert other_sku not in skus
