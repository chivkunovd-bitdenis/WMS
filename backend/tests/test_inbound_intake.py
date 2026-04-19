from __future__ import annotations

import time
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _create_seller_headers(
    async_client: AsyncClient,
    *,
    admin_headers: dict[str, str],
    seller_name: str,
    seller_email: str,
) -> tuple[dict[str, str], str]:
    s = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": seller_name},
    )
    assert s.status_code in (200, 201), s.text
    sid = s.json()["id"]
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": sid, "email": seller_email, "password": "password123"},
    )
    assert acc.status_code in (200, 201), acc.text
    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, sid


@pytest.mark.asyncio
async def test_inbound_intake_flow_post_all(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Inb Co",
            "slug": f"inb-{suffix}",
            "admin_email": f"inb-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="S",
        seller_email=f"inb-seller-{suffix}@example.com",
    )

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W1", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=ah,
        json={"code": "RCV-01"},
    )
    assert loc.status_code == 200, loc.text
    lid = loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P1",
            "sku_code": f"SKU-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(
        base,
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    sub_empty = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub_empty.status_code == 422

    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={
            "product_id": pid,
            "expected_qty": 5,
            "storage_location_id": lid,
        },
    )
    assert ln.status_code == 201, ln.text
    assert ln.json()["expected_qty"] == 5
    assert ln.json()["posted_qty"] == 0
    assert ln.json()["storage_location_id"] == lid
    line_id = ln.json()["id"]

    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"

    prim = await async_client.post(f"{base}/{rid}/primary-accept", headers=ah)
    assert prim.status_code == 200, prim.text
    assert prim.json()["status"] == "primary_accepted"

    act = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 5},
    )
    assert act.status_code == 200, act.text
    assert act.json()["actual_qty"] == 5

    ver = await async_client.post(f"{base}/{rid}/verify", headers=ah)
    assert ver.status_code == 200, ver.text
    assert ver.json()["status"] == "verified"

    post = await async_client.post(f"{base}/{rid}/post", headers=ah)
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "posted"
    assert post.json()["lines"][0]["posted_qty"] == 5

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=ah,
        params={"storage_location_id": lid},
    )
    assert bal.status_code == 200, bal.text
    rows = bal.json()
    assert len(rows) == 1
    assert rows[0]["quantity"] == 5
    assert rows[0]["sku_code"] == f"SKU-{suffix}"

    mov = await async_client.get(f"{base}/{rid}/movements", headers=ah)
    assert mov.status_code == 200, mov.text
    mrows = mov.json()
    assert len(mrows) == 1
    assert mrows[0]["quantity_delta"] == 5
    assert mrows[0]["inbound_intake_line_id"] == line_id

    dup_post = await async_client.post(f"{base}/{rid}/post", headers=ah)
    assert dup_post.status_code == 409
    assert dup_post.json()["detail"] == "already_posted"

    listed = await async_client.get(base, headers=ah)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["line_count"] == 1
    assert listed.json()[0]["status"] == "posted"

    closed = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 1},
    )
    assert closed.status_code == 409
    assert closed.json()["detail"] == "not_draft"


@pytest.mark.asyncio
async def test_inbound_partial_receive_then_complete(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Part Co",
            "slug": f"part-{suffix}",
            "admin_email": f"part-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="S",
        seller_email=f"part-seller-{suffix}@example.com",
    )

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"p-{suffix}"},
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=ah,
        json={"code": "A-1"},
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SP-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    base = "/operations/inbound-intake-requests"
    rid = (
        await async_client.post(base, headers=sh, json={"warehouse_id": wid})
    ).json()["id"]
    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 10, "storage_location_id": lid},
    )
    line_id = ln.json()["id"]
    await async_client.post(f"{base}/{rid}/submit", headers=sh)
    await async_client.post(f"{base}/{rid}/primary-accept", headers=ah)
    await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 10},
    )
    await async_client.post(f"{base}/{rid}/verify", headers=ah)

    r1 = await async_client.post(
        f"{base}/{rid}/lines/{line_id}/receive",
        headers=ah,
        json={"quantity": 3},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "verified"
    assert r1.json()["lines"][0]["posted_qty"] == 3

    r2 = await async_client.post(
        f"{base}/{rid}/lines/{line_id}/receive",
        headers=ah,
        json={"quantity": 7},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "posted"
    assert r2.json()["lines"][0]["posted_qty"] == 10

    mov = await async_client.get(f"{base}/{rid}/movements", headers=ah)
    assert len(mov.json()) == 2


@pytest.mark.asyncio
async def test_inbound_patch_storage_after_line_create(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Patch Co",
            "slug": f"pat-{suffix}",
            "admin_email": f"pat-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"pt-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=h,
        json={"code": "B-2"},
    )
    lid = loc.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"PT-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    base = "/operations/inbound-intake-requests"
    rid = (
        await async_client.post(base, headers=h, json={"warehouse_id": wid})
    ).json()["id"]
    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 2},
    )
    line_id = ln.json()["id"]
    assert ln.json()["storage_location_id"] is None

    patched = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}",
        headers=h,
        json={"storage_location_id": lid},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["storage_location_id"] == lid

    await async_client.post(f"{base}/{rid}/submit", headers=h)
    await async_client.post(f"{base}/{rid}/primary-accept", headers=h)
    await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 2},
    )
    await async_client.post(f"{base}/{rid}/verify", headers=h)
    post = await async_client.post(f"{base}/{rid}/post", headers=h)
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "posted"


@pytest.mark.asyncio
async def test_inbound_post_missing_storage_on_line(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Miss Co",
            "slug": f"mis-{suffix}",
            "admin_email": f"mis-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"m-{suffix}"}
    )
    wid = wh.json()["id"]
    await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=h,
        json={"code": "X"},
    )
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"MS-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    base = "/operations/inbound-intake-requests"
    rid = (
        await async_client.post(base, headers=h, json={"warehouse_id": wid})
    ).json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    await async_client.post(f"{base}/{rid}/submit", headers=h)
    await async_client.post(f"{base}/{rid}/primary-accept", headers=h)
    inb = await async_client.get(f"{base}/{rid}", headers=h)
    line_id = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/actual",
        headers=h,
        json={"actual_qty": 1},
    )
    await async_client.post(f"{base}/{rid}/verify", headers=h)
    bad = await async_client.post(f"{base}/{rid}/post", headers=h)
    assert bad.status_code == 422
    assert bad.json()["detail"] == "lines_missing_storage"


@pytest.mark.asyncio
async def test_inbound_duplicate_line_while_draft(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "D Co",
            "slug": f"dup-{suffix}",
            "admin_email": f"dup-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"d-{suffix}"}
    )
    wid = wh.json()["id"]
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
    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=h, json={"warehouse_id": wid})
    rid = cr.json()["id"]
    r1 = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    assert r1.status_code == 201
    r2 = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 2},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "duplicate_line"


@pytest.mark.asyncio
async def test_inbound_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get("/operations/inbound-intake-requests")
    assert r.status_code == 401
    r2 = await async_client.post(
        "/operations/inbound-intake-requests",
        json={"warehouse_id": str(uuid.uuid4())},
    )
    assert r2.status_code == 401
    r3 = await async_client.get(
        "/operations/inventory-balances",
        params={"storage_location_id": str(uuid.uuid4())},
    )
    assert r3.status_code == 401
    r3b = await async_client.get("/operations/inventory-balances/summary")
    assert r3b.status_code == 401
    r4 = await async_client.get("/operations/inventory-movements")
    assert r4.status_code == 401
    r5 = await async_client.post(
        "/operations/stock-transfers",
        json={
            "from_storage_location_id": str(uuid.uuid4()),
            "to_storage_location_id": str(uuid.uuid4()),
            "product_id": str(uuid.uuid4()),
            "quantity": 1,
        },
    )
    assert r5.status_code == 401
    r6 = await async_client.get("/operations/outbound-shipment-requests")
    assert r6.status_code == 401
    r6b = await async_client.post(
        f"/operations/outbound-shipment-requests/{uuid.uuid4()}/lines/{uuid.uuid4()}/ship",
        json={"quantity": 1},
    )
    assert r6b.status_code == 401
    r6c = await async_client.delete(
        f"/operations/outbound-shipment-requests/{uuid.uuid4()}/lines/{uuid.uuid4()}",
    )
    assert r6c.status_code == 401
    r7 = await async_client.get("/sellers")
    assert r7.status_code == 401
    r8 = await async_client.post(
        "/operations/background-jobs",
        json={"job_type": "movements_digest"},
    )
    assert r8.status_code == 401
    r9 = await async_client.post(
        "/auth/seller-accounts",
        json={
            "seller_id": str(uuid.uuid4()),
            "email": "x@example.com",
            "password": "password123",
        },
    )
    assert r9.status_code == 401
    r10 = await async_client.get("/products/wb-catalog")
    assert r10.status_code == 401


@pytest.mark.asyncio
async def test_inbound_patch_wrong_warehouse_location(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "L Co",
            "slug": f"loc-{suffix}",
            "admin_email": f"loc-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    w1 = await async_client.post(
        "/warehouses", headers=h, json={"name": "W1", "code": f"a-{suffix}"}
    )
    w2 = await async_client.post(
        "/warehouses", headers=h, json={"name": "W2", "code": f"b-{suffix}"}
    )
    wid1 = w1.json()["id"]
    wid2 = w2.json()["id"]
    loc2 = await async_client.post(
        f"/warehouses/{wid2}/locations",
        headers=h,
        json={"code": "X"},
    )
    lid2 = loc2.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"z-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=h, json={"warehouse_id": wid1})
    rid = cr.json()["id"]
    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    line_id = ln.json()["id"]
    bad = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}",
        headers=h,
        json={"storage_location_id": lid2},
    )
    assert bad.status_code == 404
    assert bad.json()["detail"] == "location_not_found"


@pytest.mark.asyncio
async def test_inbound_create_unknown_warehouse(async_client: AsyncClient) -> None:
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
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    bad = uuid.uuid4()
    r = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": str(bad)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inbound_draft_patch_qty_delete_patch_planned(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Draft Co",
            "slug": f"dr-{suffix}",
            "admin_email": f"dr-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Sdr",
        seller_email=f"dr-sl-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Wdr", "code": f"wdr-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Pdr",
            "sku_code": f"SKU-DR-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]
    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(
        base,
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 3},
    )
    assert ln.status_code == 201, ln.text
    line_id = ln.json()["id"]
    patch = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/expected",
        headers=sh,
        json={"expected_qty": 7},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["expected_qty"] == 7
    d1 = (date.today() + timedelta(days=2)).isoformat()
    ppl = await async_client.patch(
        f"{base}/{rid}",
        headers=sh,
        json={"planned_delivery_date": d1},
    )
    assert ppl.status_code == 200, ppl.text
    assert ppl.json()["planned_delivery_date"] == d1
    dl = await async_client.delete(f"{base}/{rid}/lines/{line_id}", headers=sh)
    assert dl.status_code == 204
    got = await async_client.get(f"{base}/{rid}", headers=sh)
    assert got.status_code == 200, got.text
    assert got.json()["lines"] == []
