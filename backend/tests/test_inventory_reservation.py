from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_second_outbound_line_blocks_when_reserved_exceeds_on_hand(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Res Co",
            "slug": f"res-{suffix}",
            "admin_email": f"res-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A1"}
    )
    lid = loc.json()["id"]
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
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=h
    )
    assert (
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/post", headers=h
        )
    ).status_code == 200

    base = "/operations/outbound-shipment-requests"
    o1 = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    id1 = o1.json()["id"]
    assert (
        await async_client.post(
            f"{base}/{id1}/lines",
            headers=h,
            json={"product_id": pid, "quantity": 6, "storage_location_id": lid},
        )
    ).status_code == 201

    o2 = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    id2 = o2.json()["id"]
    bad = await async_client.post(
        f"{base}/{id2}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 6, "storage_location_id": lid},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "insufficient_available"


@pytest.mark.asyncio
async def test_stock_transfer_blocked_by_outbound_reservation(
    async_client: AsyncClient,
) -> None:
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
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-tr-{suffix}"}
    )
    wid = wh.json()["id"]
    la = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "FROM"}
    )
    lb = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "TO"}
    )
    aid = la.json()["id"]
    bid = lb.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-tr-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]

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
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 8, "storage_location_id": aid},
    )
    await async_client.post(f"{base}/{oid}/submit", headers=h)

    tr = await async_client.post(
        "/operations/stock-transfers",
        headers=h,
        json={
            "from_storage_location_id": aid,
            "to_storage_location_id": bid,
            "product_id": pid,
            "quantity": 3,
        },
    )
    assert tr.status_code == 422
    assert tr.json()["detail"] == "insufficient_stock"


@pytest.mark.asyncio
async def test_inventory_balances_include_reserved_and_available(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Bal Co",
            "slug": f"bal-{suffix}",
            "admin_email": f"bal-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-bal-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "L1"}
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-bal-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]

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
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 7, "storage_location_id": lid},
    )

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal.status_code == 200
    row = bal.json()[0]
    assert row["quantity"] == 10
    assert row["reserved"] == 7
    assert row["available"] == 3
