from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_inbound_distribution_lines_validate_limits_and_lock(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dist Co",
            "slug": f"dist-{suffix}",
            "admin_email": f"dist-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"d-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=ah,
        json={"code": "A-01"},
    )
    assert loc.status_code == 200, loc.text
    lid = loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-D-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": 5},
    )
    assert ln.status_code == 201, ln.text

    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    prim = await async_client.post(f"{base}/{rid}/primary-accept", headers=ah)
    assert prim.status_code == 200, prim.text
    assert prim.json()["status"] == "primary_accepted"

    got = await async_client.get(f"{base}/{rid}", headers=ah)
    assert got.status_code == 200, got.text
    line_id = got.json()["lines"][0]["id"]
    act = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 5},
    )
    assert act.status_code == 200, act.text
    ver = await async_client.post(f"{base}/{rid}/verify", headers=ah)
    assert ver.status_code == 200, ver.text
    assert ver.json()["status"] == "verified"

    too_much = await async_client.put(
        f"{base}/{rid}/distribution-lines",
        headers=ah,
        json=[{"product_id": pid, "storage_location_id": lid, "quantity": 6}],
    )
    assert too_much.status_code == 422, too_much.text
    assert too_much.json()["detail"] == "qty_exceeds_accepted"

    ok = await async_client.put(
        f"{base}/{rid}/distribution-lines",
        headers=ah,
        json=[
            {"product_id": pid, "storage_location_id": lid, "quantity": 2},
            {"product_id": pid, "storage_location_id": lid, "quantity": 3},
        ],
    )
    assert ok.status_code == 200, ok.text
    rows = ok.json()
    assert len(rows) == 2
    assert sum(int(r["quantity"]) for r in rows) == 5

    done = await async_client.post(f"{base}/{rid}/distribution-complete", headers=ah)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "posted"
    assert done.json()["lines"][0]["posted_qty"] == 5

    movements = await async_client.get(f"{base}/{rid}/movements", headers=ah)
    assert movements.status_code == 200, movements.text
    assert sorted(m["quantity_delta"] for m in movements.json()) == [2, 3]

    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
    )
    assert balances.status_code == 200, balances.text
    balance_row = next(r for r in balances.json() if r["product_id"] == pid)
    assert balance_row["quantity"] == 5

    ff_catalog = await async_client.get("/products/ff-catalog", headers=ah)
    assert ff_catalog.status_code == 200, ff_catalog.text
    assert pid in {r["id"] for r in ff_catalog.json()}

    locked = await async_client.put(
        f"{base}/{rid}/distribution-lines",
        headers=ah,
        json=[{"product_id": pid, "storage_location_id": lid, "quantity": 1}],
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"] == "distribution_completed"

