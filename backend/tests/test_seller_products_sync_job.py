from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_can_start_wb_cards_sync_self(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Seller Sync Co",
            "slug": f"seller-sync-{suffix}",
            "admin_email": f"seller-sync-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    s = await async_client.post("/sellers", headers=h, json={"name": "Brand A"})
    seller_id = s.json()["id"]
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=h,
        json={
            "seller_id": seller_id,
            "email": f"seller-a-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert acc.status_code in (200, 201)

    login = await async_client.post(
        "/auth/login",
        json={"email": f"seller-a-{suffix}@example.com", "password": "password123"},
    )
    st = str(login.json()["access_token"])
    sh = {"Authorization": f"Bearer {st}"}

    r = await async_client.post(
        "/operations/background-jobs/wildberries-cards-sync-self",
        headers=sh,
    )
    assert r.status_code == 202
    assert "id" in r.json()

