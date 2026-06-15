from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_shop_switch_acts_as_delegated_seller(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))

    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Shop Switch Co",
            "slug": f"shop-sw-{suffix}",
            "admin_email": f"admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses",
        headers=admin_h,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code in (200, 201)

    home = await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "Home Shop",
            "email": f"denmarks-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert home.status_code == 201
    home_seller_id = home.json()["seller_id"]

    other = await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "Other Shop",
            "email": f"other-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert other.status_code == 201
    other_seller_id = other.json()["seller_id"]

    test_seller = await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "Test Shop",
            "email": f"e2e-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert test_seller.status_code == 201

    login = await async_client.post(
        "/auth/login",
        json={
            "email": f"denmarks-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    seller_h = {"Authorization": f"Bearer {token}"}

    me = await async_client.get("/auth/me", headers=seller_h)
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["can_manage_seller_shops"] is True
    delegatable_ids = {row["id"] for row in me_body["delegatable_shops"]}
    assert other_seller_id in delegatable_ids
    assert home_seller_id not in delegatable_ids
    assert test_seller.json()["seller_id"] not in delegatable_ids

    put = await async_client.put(
        "/auth/seller-shops",
        headers=seller_h,
        json={"enabled_seller_ids": [other_seller_id]},
    )
    assert put.status_code == 200

    switch = await async_client.post(
        "/auth/switch-seller",
        headers=seller_h,
        json={"seller_id": other_seller_id},
    )
    assert switch.status_code == 200
    switched_token = switch.json()["access_token"]
    switched_h = {"Authorization": f"Bearer {switched_token}"}

    me2 = await async_client.get("/auth/me", headers=switched_h)
    assert me2.status_code == 200
    assert me2.json()["active_seller_id"] == other_seller_id
    assert me2.json()["seller_id"] == other_seller_id

    wid = wh.json()["id"]
    created = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=switched_h,
        json={"warehouse_id": wid},
    )
    assert created.status_code == 201
    assert created.json()["seller_id"] == other_seller_id
    listed = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=switched_h,
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) >= 1
    assert all(r.get("seller_name") == "Other Shop" for r in rows)


@pytest.mark.asyncio
async def test_seller_cannot_switch_without_delegation(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "No Delegate",
            "slug": f"no-del-{suffix}",
            "admin_email": f"admin2-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "S1",
            "email": f"s1-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    s2 = await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "S2",
            "email": f"s2-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert s2.status_code == 201
    sid2 = s2.json()["seller_id"]

    login = await async_client.post(
        "/auth/login",
        json={"email": f"s1-{suffix}@mail.ru", "password": "password123"},
    )
    seller_h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    switch = await async_client.post(
        "/auth/switch-seller",
        headers=seller_h,
        json={"seller_id": sid2},
    )
    assert switch.status_code == 403


@pytest.mark.asyncio
async def test_regular_seller_cannot_manage_shops(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Regular Co",
            "slug": f"reg-sh-{suffix}",
            "admin_email": f"admin-reg-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers/with-account",
        headers=admin_h,
        json={
            "name": "Regular Shop",
            "email": f"regular-{suffix}@mail.ru",
            "password": "password123",
        },
    )
    assert seller.status_code == 201
    login = await async_client.post(
        "/auth/login",
        json={"email": f"regular-{suffix}@mail.ru", "password": "password123"},
    )
    assert login.status_code == 200
    me = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["can_manage_seller_shops"] is False
