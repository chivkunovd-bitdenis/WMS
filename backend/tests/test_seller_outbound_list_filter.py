from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_outbound_list_only_own_seller_requests(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "List Filter Co",
            "slug": f"lst-{suffix}",
            "admin_email": f"lst-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "L1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post("/sellers", headers=ah, json={"name": "SA"})
    s2 = await async_client.post("/sellers", headers=ah, json={"name": "SB"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p1 = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P1",
            "sku_code": f"L1-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid1,
        },
    )
    p2 = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P2",
            "sku_code": f"L2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid1 = p1.json()["id"]
    pid2 = p2.json()["id"]

    base_in = "/operations/inbound-intake-requests"
    for pid, qty in ((pid1, 5), (pid2, 5)):
        rid = (
            await async_client.post(base_in, headers=ah, json={"warehouse_id": wid})
        ).json()["id"]
        await async_client.post(
            f"{base_in}/{rid}/lines",
            headers=ah,
            json={
                "product_id": pid,
                "expected_qty": qty,
                "storage_location_id": lid,
            },
        )
        await async_client.post(f"{base_in}/{rid}/submit", headers=ah)
        await async_client.post(f"{base_in}/{rid}/post", headers=ah)

    base_out = "/operations/outbound-shipment-requests"
    rid_b = (
        await async_client.post(base_out, headers=ah, json={"warehouse_id": wid})
    ).json()["id"]
    await async_client.post(
        f"{base_out}/{rid_b}/lines",
        headers=ah,
        json={
            "product_id": pid2,
            "quantity": 1,
            "storage_location_id": lid,
        },
    )
    rid_a = (
        await async_client.post(base_out, headers=ah, json={"warehouse_id": wid})
    ).json()["id"]
    await async_client.post(
        f"{base_out}/{rid_a}/lines",
        headers=ah,
        json={
            "product_id": pid1,
            "quantity": 1,
            "storage_location_id": lid,
        },
    )

    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid1,
            "email": f"lst-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"lst-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = await async_client.get(base_out, headers=sh)
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["id"] == rid_a

    g_b = await async_client.get(f"{base_out}/{rid_b}", headers=sh)
    assert g_b.status_code == 404
