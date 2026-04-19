from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_outbound_shipment_decrements_stock(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Out Co",
            "slug": f"out-{suffix}",
            "admin_email": f"out-{suffix}@example.com",
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
        f"/warehouses/{wid}/locations", headers=h, json={"code": "PICK"}
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
            "expected_qty": 20,
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/primary-accept", headers=h
    )
    inb = await async_client.get(f"/operations/inbound-intake-requests/{rid}", headers=h)
    line_id = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 20},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    assert (
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/post", headers=h
        )
    ).status_code == 200

    base = "/operations/outbound-shipment-requests"
    orq = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    assert orq.status_code == 201
    oid = orq.json()["id"]
    ln = await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 7, "storage_location_id": lid},
    )
    assert ln.status_code == 201
    await async_client.post(f"{base}/{oid}/submit", headers=h)
    pst = await async_client.post(f"{base}/{oid}/post", headers=h)
    assert pst.status_code == 200, pst.text
    assert pst.json()["status"] == "posted"

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal.json()[0]["quantity"] == 13

    mov = await async_client.get(f"{base}/{oid}/movements", headers=h)
    assert mov.status_code == 200
    assert mov.json()[0]["quantity_delta"] == -7


@pytest.mark.asyncio
async def test_outbound_partial_ship_then_post_rest(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Part Out Co",
            "slug": f"pout-{suffix}",
            "admin_email": f"pout-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-po-{suffix}"}
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
            "sku_code": f"S-po-{suffix}",
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
    inb = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}", headers=h
    )
    line_id = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 10},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    assert (
        await async_client.post(
            f"/operations/inbound-intake-requests/{rid}/post", headers=h
        )
    ).status_code == 200

    base = "/operations/outbound-shipment-requests"
    orq = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    oid = orq.json()["id"]
    ln = await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5, "storage_location_id": lid},
    )
    assert ln.status_code == 201
    line_id = ln.json()["id"]
    assert ln.json()["shipped_qty"] == 0
    await async_client.post(f"{base}/{oid}/submit", headers=h)

    s1 = await async_client.post(
        f"{base}/{oid}/lines/{line_id}/ship",
        headers=h,
        json={"quantity": 2},
    )
    assert s1.status_code == 200, s1.text
    body = s1.json()
    assert body["status"] == "submitted"
    assert body["lines"][0]["shipped_qty"] == 2

    s2 = await async_client.post(f"{base}/{oid}/post", headers=h)
    assert s2.status_code == 200, s2.text
    assert s2.json()["status"] == "posted"
    assert s2.json()["lines"][0]["shipped_qty"] == 5

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal.json()[0]["quantity"] == 5

    mov = await async_client.get(f"{base}/{oid}/movements", headers=h)
    deltas = {m["quantity_delta"] for m in mov.json()}
    assert deltas == {-2, -3}


@pytest.mark.asyncio
async def test_outbound_post_duplicate_after_fully_shipped_returns_409(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dup Post Co",
            "slug": f"epo-{suffix}",
            "admin_email": f"epo-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-epo-{suffix}"}
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
            "sku_code": f"S-epo-{suffix}",
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
            "expected_qty": 4,
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
    line_id_in = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id_in}/actual",
        headers=h,
        json={"actual_qty": 4},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/verify", headers=h
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/post", headers=h
    )

    base = "/operations/outbound-shipment-requests"
    orq = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    oid = orq.json()["id"]
    ln = await async_client.post(
        f"{base}/{oid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3, "storage_location_id": lid},
    )
    line_id = ln.json()["id"]
    await async_client.post(f"{base}/{oid}/submit", headers=h)
    assert (
        await async_client.post(
            f"{base}/{oid}/lines/{line_id}/ship",
            headers=h,
            json={"quantity": 3},
        )
    ).status_code == 200

    dup = await async_client.post(f"{base}/{oid}/post", headers=h)
    assert dup.status_code == 409
    assert dup.json()["detail"] == "already_posted"
