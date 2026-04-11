from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_sees_only_own_products_and_filtered_inbound(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "RBAC Co",
            "slug": f"rbac-{suffix}",
            "admin_email": f"adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_tok = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {admin_tok}"}

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "A1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post(
        "/sellers", headers=ah, json={"name": "Seller Alpha"}
    )
    s2 = await async_client.post(
        "/sellers", headers=ah, json={"name": "Seller Beta"}
    )
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p_own = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Own",
            "sku_code": f"OWN-{suffix}",
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
            "name": "Other",
            "sku_code": f"OTH-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid_own = p_own.json()["id"]

    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid},
    )
    rid = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=ah,
        json={
            "product_id": pid_own,
            "expected_qty": 5,
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=ah
    )

    seller_email = f"slr-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid1,
            "email": seller_email,
            "password": "password123",
        },
    )
    assert acc.status_code == 201, acc.text

    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await async_client.get("/auth/me", headers=sh)
    assert me.status_code == 200
    assert me.json()["role"] == "fulfillment_seller"
    assert me.json()["seller_id"] == sid1
    assert me.json()["seller_name"] == "Seller Alpha"

    prods = await async_client.get("/products", headers=sh)
    assert prods.status_code == 200
    assert len(prods.json()) == 1
    assert prods.json()[0]["sku_code"] == f"OWN-{suffix}"

    sellers = await async_client.get("/sellers", headers=sh)
    assert sellers.status_code == 200
    assert len(sellers.json()) == 1
    assert sellers.json()[0]["name"] == "Seller Alpha"

    inbound = await async_client.get(
        "/operations/inbound-intake-requests", headers=sh
    )
    assert inbound.status_code == 200
    assert len(inbound.json()) == 1

    wh_read = await async_client.get("/warehouses", headers=sh)
    assert wh_read.status_code == 200
    assert len(wh_read.json()) >= 1

    wh403 = await async_client.post(
        "/warehouses", headers=sh, json={"name": "X", "code": f"x-{suffix}"}
    )
    assert wh403.status_code == 403

    job403 = await async_client.post(
        "/operations/background-jobs",
        headers=sh,
        json={"job_type": "movements_digest"},
    )
    assert job403.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_create_seller_account(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "RBAC2",
            "slug": f"rb2-{suffix}",
            "admin_email": f"a2-{suffix}@example.com",
            "password": "password123",
        },
    )
    admin_tok = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {admin_tok}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S"})
    sid = s.json()["id"]
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"sl2-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert acc.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": f"sl2-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    dup = await async_client.post(
        "/auth/seller-accounts",
        headers=sh,
        json={
            "seller_id": sid,
            "email": f"sl3-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert dup.status_code == 403
