"""TC-NEW-MP-* — seller marketplace unload flow."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from test_marketplace_unload_and_discrepancy_acts import (
    E2E_BARCODE,
    _link_product_wb_barcode,
    _post_inventory,
    _seller_wb_mp_warehouse,
)


async def _seller_headers(
    async_client: AsyncClient,
    admin_h: dict[str, str],
    seller_id: str,
) -> dict[str, str]:
    email = f"mp-sl-{time.time()}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_h,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert acc.status_code == 201, acc.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_seller_mp_unload_plan_reserves_and_ff_confirms(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TC-NEW-MP-02, TC-NEW-MP-03, TC-NEW-MP-06, TC-NEW-MP-07, TC-NEW-MP-09, TC-NEW-MP-17
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Seller MP Co",
            "slug": f"sel-mp-{suffix}",
            "admin_email": f"sel-mp-{suffix}@example.com",
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
    await _link_product_wb_barcode(
        async_client, ah, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=10, location_code="MP-A"
    )

    stock = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=sh,
        params={"warehouse_id": wid},
    )
    assert stock.status_code == 200
    row = next(x for x in stock.json() if x["product_id"] == pid)
    assert row["available"] == 10

    create = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert create.status_code == 201, create.text
    mid = create.json()["id"]

    listed = await async_client.get("/operations/marketplace-unload-requests", headers=sh)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    bad = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 12}]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "insufficient_available"

    ok_lines = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 4}]},
    )
    assert ok_lines.status_code == 200, ok_lines.text

    plan_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan_blocked.status_code == 409
    assert plan_blocked.json()["detail"] == "wb_mp_warehouse_required"

    patch_wh = await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=sh,
        json={"wb_mp_warehouse_id": wb_wid},
    )
    assert patch_wh.status_code == 200, patch_wh.text

    plan_no_date = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan_no_date.status_code == 409
    assert plan_no_date.json()["detail"] == "planned_shipment_date_required"

    patch_date = await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=sh,
        json={"planned_shipment_date": "2026-06-01"},
    )
    assert patch_date.status_code == 200, patch_date.text

    plan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["status"] == "submitted"

    stock2 = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=sh,
        params={"warehouse_id": wid},
    )
    row2 = next(x for x in stock2.json() if x["product_id"] == pid)
    assert row2["available"] == 6

    edit_blocked = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 3}]},
    )
    assert edit_blocked.status_code == 409

    ff_list = await async_client.get("/operations/marketplace-unload-requests", headers=ah)
    assert any(x["id"] == mid and x["status"] == "submitted" for x in ff_list.json())

    box_in_draft = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box_in_draft.status_code == 409

    confirm = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/confirm",
        headers=ah,
        json={"planned_shipment_date": "2026-06-01"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "confirmed"
    assert confirm.json()["planned_shipment_date"] == "2026-06-01"

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=ah)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    loc_scan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=ah,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text

    for _ in range(4):
        scan = await async_client.post(
            f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/scan",
            headers=ah,
            json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
        )
        assert scan.status_code == 200, scan.text

    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=ah,
    )
    assert detail.status_code == 200
    line = detail.json()["lines"][0]
    assert line["picked_qty"] == 4

    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/close",
        headers=ah,
    )

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=ah,
    )
    assert ship.status_code == 200, ship.text
    assert ship.json()["status"] == "shipped"


@pytest.mark.asyncio
async def test_seller_cannot_see_other_seller_mp_unload(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TC-NEW-MP-17
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Iso MP",
            "slug": f"iso-mp-{suffix}",
            "admin_email": f"iso-mp-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    s1 = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    s2 = await async_client.post("/sellers", headers=ah, json={"name": "S2"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]
    _sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    sh1 = await _seller_headers(async_client, ah, sid1)

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid2, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]

    listed = await async_client.get("/operations/marketplace-unload-requests", headers=sh1)
    assert all(x["id"] != mid for x in listed.json())

    get_other = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=sh1,
    )
    assert get_other.status_code == 404


@pytest.mark.asyncio
async def test_seller_can_read_wb_mp_warehouses(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TC-NEW-MP-15
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB WH Co",
            "slug": f"wbwh-{suffix}",
            "admin_email": f"wbwh-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sid, _ = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    sh = await _seller_headers(async_client, ah, sid)
    whs = await async_client.get("/operations/wb-mp-warehouses", headers=sh)
    assert whs.status_code == 200
    assert len(whs.json()) >= 1
