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


@pytest.mark.asyncio
async def test_available_matches_mp_reserve_only_after_putaway(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_marketplace_unload_and_discrepancy_acts import _seller_wb_mp_warehouse
    from test_seller_marketplace_unload import _seller_headers

    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Avail Sort Co",
            "slug": f"avail-sort-{suffix}",
            "admin_email": f"avail-sort-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    sh = await _seller_headers(async_client, ah, sid)

    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "CELL-1"}
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    ir = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    rid = ir.json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=ah,
        json={
            "product_id": pid,
            "expected_qty": 10,
            "storage_location_id": lid,
        },
    )
    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 10)
    await async_client.post(f"{base}/{rid}/verify", headers=ah)

    after_verify = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=sh,
        params={"warehouse_id": wid},
    )
    row_v = next(x for x in after_verify.json() if x["product_id"] == pid)
    assert row_v["quantity"] == 10
    assert row_v["quantity_in_sorting"] == 10
    assert row_v["available"] == 0

    mp = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=sh,
        json={"warehouse_id": wid},
    )
    mid = mp.json()["id"]
    blocked = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 4}]},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "insufficient_available"

    post = await async_client.post(f"{base}/{rid}/post", headers=ah)
    assert post.status_code == 200, post.text

    after_plan_setup = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=sh,
        params={"warehouse_id": wid},
    )
    row_p = next(x for x in after_plan_setup.json() if x["product_id"] == pid)
    assert row_p["quantity_in_storage"] == 10
    assert row_p["available"] == 10

    ok_lines = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 4}]},
    )
    assert ok_lines.status_code == 200, ok_lines.text
    await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=sh,
        json={"wb_mp_warehouse_id": wb_wid, "planned_shipment_date": "2026-06-15"},
    )
    plan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan.status_code == 200, plan.text

    after_plan = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=sh,
        params={"warehouse_id": wid},
    )
    row_r = next(x for x in after_plan.json() if x["product_id"] == pid)
    assert row_r["reserved"] == 4
    assert row_r["available"] == 6
    assert row_r["quantity"] - row_r["reserved"] == 6

