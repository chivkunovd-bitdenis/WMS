from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept


@pytest.mark.asyncio
async def test_locations_by_product_returns_cells_with_stock(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Hint Co",
            "slug": f"hint-{suffix}",
            "admin_email": f"hint-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-h-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "A-01"}
    )
    lid = loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-H-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    rid = cr.json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines", headers=ah, json={"product_id": pid, "expected_qty": 4}
    )
    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 4)
    await async_client.post(f"{base}/{rid}/verify", headers=ah)
    got = await async_client.get(f"{base}/{rid}", headers=ah)
    assert got.status_code == 200, got.text
    box_id = got.json()["boxes"][0]["id"]
    put = await async_client.put(
        f"{base}/{rid}/distribution-lines",
        headers=ah,
        json=[
            {
                "box_id": box_id,
                "product_id": pid,
                "storage_location_id": lid,
                "quantity": 4,
            }
        ],
    )
    assert put.status_code == 200, put.text
    done = await async_client.post(f"{base}/{rid}/distribution-complete", headers=ah)
    assert done.status_code == 200, done.text

    hints = await async_client.get(
        "/operations/inventory-balances/locations-by-product",
        headers=ah,
        params={"product_id": pid, "warehouse_id": wid},
    )
    assert hints.status_code == 200, hints.text
    body = hints.json()
    assert len(body) == 1
    assert body[0]["storage_location_code"] == "A-01"
    assert body[0]["quantity"] == 4
    assert body[0]["available"] == 4

    empty = await async_client.get(
        "/operations/inventory-balances/locations-by-product",
        headers=ah,
        params={"product_id": pid, "warehouse_id": str(wid)},
    )
    assert empty.status_code == 200
