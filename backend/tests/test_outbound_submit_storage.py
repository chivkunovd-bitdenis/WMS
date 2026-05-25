from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans


@pytest.mark.asyncio
async def test_outbound_submit_warehouse_reserve_without_cell(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Out Stor Co",
            "slug": f"out-st-{suffix}",
            "admin_email": f"out-st-{suffix}@example.com",
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
    sku = pr.json()["sku_code"]

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
        f"/operations/inbound-intake-requests/{rid}/primary-accept",
        headers=h,
        json={"actual_box_count": 1},
    )
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 10)
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
        json={"product_id": pid, "quantity": 5},
    )
    assert ln.status_code == 201, ln.text
    assert ln.json()["storage_location_id"] is None

    ok_submit = await async_client.post(f"{base}/{oid}/submit", headers=h)
    assert ok_submit.status_code == 200, ok_submit.text
    assert ok_submit.json()["status"] == "submitted"

    bal = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=h,
        params={"warehouse_id": wid},
    )
    row = next(x for x in bal.json() if x["product_id"] == pid)
    assert row["reserved"] == 5
    assert row["available"] == 5

    line_id = ln.json()["id"]
    post_bad = await async_client.post(f"{base}/{oid}/post", headers=h)
    assert post_bad.status_code == 422
    assert post_bad.json()["detail"] == "lines_missing_storage"

    patched = await async_client.patch(
        f"{base}/{oid}/lines/{line_id}",
        headers=h,
        json={"storage_location_id": lid},
    )
    assert patched.status_code == 200, patched.text
    post_ok = await async_client.post(f"{base}/{oid}/post", headers=h)
    assert post_ok.status_code == 200, post_ok.text
