from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_stock_transfer_moves_balance_and_journal(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Tr Co",
            "slug": f"tr-{suffix}",
            "admin_email": f"tr-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    a = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A"}
    )
    b = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "B"}
    )
    aid = a.json()["id"]
    bid = b.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]

    # stock через приёмку
    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    rid = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=h,
        json={
            "product_id": pid,
            "expected_qty": 10,
            "storage_location_id": aid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=h
    )
    post = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )
    assert post.status_code == 200

    tr = await async_client.post(
        "/operations/stock-transfers",
        headers=h,
        json={
            "from_storage_location_id": aid,
            "to_storage_location_id": bid,
            "product_id": pid,
            "quantity": 4,
        },
    )
    assert tr.status_code == 200, tr.text

    ba = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": aid},
    )
    bb = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": bid},
    )
    assert ba.json()[0]["quantity"] == 6
    assert bb.json()[0]["quantity"] == 4

    mov = await async_client.get(
        "/operations/inventory-movements",
        headers=h,
        params={"limit": 20},
    )
    assert mov.status_code == 200
    types = {m["movement_type"] for m in mov.json()}
    assert "stock_transfer_out" in types
    assert "stock_transfer_in" in types


@pytest.mark.asyncio
async def test_stock_transfer_insufficient(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "X",
            "slug": f"x-{suffix}",
            "admin_email": f"x-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    a = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A"}
    )
    b = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "B"}
    )
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    tr = await async_client.post(
        "/operations/stock-transfers",
        headers=h,
        json={
            "from_storage_location_id": a.json()["id"],
            "to_storage_location_id": b.json()["id"],
            "product_id": pid,
            "quantity": 1,
        },
    )
    assert tr.status_code == 422
    assert tr.json()["detail"] == "insufficient_stock"
