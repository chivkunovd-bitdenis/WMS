from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_delete_draft_line_releases_reservation(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Del Co",
            "slug": f"del-{suffix}",
            "admin_email": f"del-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

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
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/primary-accept", headers=h
    )
    lines = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}",
        headers=h,
    )
    line_id = lines.json()["lines"][0]["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 10},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    ln = await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 8, "storage_location_id": lid},
    )
    assert ln.status_code == 201, ln.text
    line_id = ln.json()["id"]

    bal1 = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal1.json()[0]["reserved"] == 8
    assert bal1.json()[0]["available"] == 2

    o2 = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    oid2 = o2.json()["id"]
    bad = await async_client.post(
        f"{base}/{oid2}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5, "storage_location_id": lid},
    )
    assert bad.status_code == 422

    rm = await async_client.delete(f"{base}/{oid}/lines/{line_id}", headers=h)
    assert rm.status_code == 200, rm.text
    assert rm.json()["status"] == "draft"
    assert rm.json()["lines"] == []

    bal2 = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal2.json()[0]["reserved"] == 0
    assert bal2.json()[0]["available"] == 10

    ok = await async_client.post(
        f"{base}/{oid2}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5, "storage_location_id": lid},
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_delete_line_not_draft_returns_409(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Del2 Co",
            "slug": f"dl2-{suffix}",
            "admin_email": f"dl2-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w2-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "B1"}
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S2-{suffix}",
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
            "expected_qty": 5,
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/primary-accept", headers=h
    )
    inb = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}", headers=h
    )
    line_id = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 5},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    oid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    ln = await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3, "storage_location_id": lid},
    )
    line_id = ln.json()["id"]
    await async_client.post(f"{base}/{oid}/submit", headers=h)

    rm = await async_client.delete(f"{base}/{oid}/lines/{line_id}", headers=h)
    assert rm.status_code == 409
    assert rm.json()["detail"] == "not_draft"
