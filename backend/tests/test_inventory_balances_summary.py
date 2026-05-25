from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept


@pytest.mark.asyncio
async def test_inventory_balances_summary_seller_scope(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Inv Sum Co",
            "slug": f"inv-sum-{suffix}",
            "admin_email": f"inv-sum-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    s1 = await async_client.post("/sellers", headers=h, json={"name": "Brand A"})
    s2 = await async_client.post("/sellers", headers=h, json={"name": "Brand B"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc1 = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A1"}
    )
    loc2 = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A2"}
    )
    lid1 = loc1.json()["id"]
    lid2 = loc2.json()["id"]

    p1 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"S-A-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid1,
        },
    )
    p2 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P2",
            "sku_code": f"S-B-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid1 = p1.json()["id"]
    sku1 = p1.json()["sku_code"]
    pid2 = p2.json()["id"]
    sku2 = p2.json()["sku_code"]

    async def _inbound_post(
        product_id: str, product_sku: str, storage_location_id: str, qty: int
    ) -> None:
        base = "/operations/inbound-intake-requests"
        ir = await async_client.post(base, headers=h, json={"warehouse_id": wid})
        rid = ir.json()["id"]
        await async_client.post(
            f"{base}/{rid}/lines",
            headers=h,
            json={
                "product_id": product_id,
                "expected_qty": qty,
                "storage_location_id": storage_location_id,
            },
        )
        await async_client.post(f"{base}/{rid}/submit", headers=h)
        await post_primary_accept(async_client, base, rid, h)
        await fulfill_inbound_via_box_scans(async_client, h, rid, product_sku, qty)
        await async_client.post(f"{base}/{rid}/verify", headers=h)
        await async_client.post(f"{base}/{rid}/post", headers=h)

    await _inbound_post(pid1, sku1, lid1, 3)
    await _inbound_post(pid1, sku1, lid2, 2)
    await _inbound_post(pid2, sku2, lid1, 7)

    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=h,
        json={
            "seller_id": sid1,
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

    rows = (await async_client.get("/operations/inventory-balances/summary", headers=sh)).json()
    assert len(rows) == 1
    assert rows[0]["product_id"] == pid1
    assert rows[0]["quantity"] == 5

