from __future__ import annotations

import time
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept

from app.db.session import SessionLocal
from app.models.product import Product


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


async def _mark_product_wb_linked(product_id: str, *, nm_id: int) -> None:
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.wb_nm_id = nm_id
        product.wb_chrt_id = nm_id + 10_000
        await session.commit()


async def _set_planned_boxes(
    async_client: AsyncClient,
    base: str,
    request_id: str,
    headers: dict[str, str],
    count: int = 1,
) -> None:
    res = await async_client.patch(
        f"{base}/{request_id}",
        headers=headers,
        json={"planned_box_count": count},
    )
    assert res.status_code == 200, res.text


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
    sku = pr.json()["sku_code"]

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

    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"

    prim = await post_primary_accept(async_client, base, rid, ah)
    assert prim.status_code == 200, prim.text
    assert prim.json()["status"] == "receiving"
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 5)

    ver = await async_client.post(f"{base}/{rid}/verify", headers=ah)
    assert ver.status_code == 200, ver.text
    assert ver.json()["status"] == "sorting"

    post = await async_client.post(f"{base}/{rid}/post", headers=ah)
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "done"
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
    inbound_to_sorting = [
        m
        for m in mrows
        if m["movement_type"] == "inbound_intake" and m["quantity_delta"] > 0
    ]
    transfer_in = [m for m in mrows if m["movement_type"] == "stock_transfer_in"]
    assert len(inbound_to_sorting) == 1
    assert inbound_to_sorting[0]["quantity_delta"] == 5
    assert inbound_to_sorting[0]["inbound_intake_line_id"] == line_id
    assert sum(m["quantity_delta"] for m in transfer_in) == 5

    dup_post = await async_client.post(f"{base}/{rid}/post", headers=ah)
    assert dup_post.status_code == 409
    assert dup_post.json()["detail"] == "already_posted"

    listed = await async_client.get(base, headers=ah)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["line_count"] == 1
    assert listed.json()[0]["status"] == "done"

    closed = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 1},
    )
    assert closed.status_code == 409
    assert closed.json()["detail"] == "not_draft"


@pytest.mark.asyncio
async def test_ff_created_request_begins_receiving_and_reads_cargo_places(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Direct Co",
            "slug": f"ff-direct-{suffix}",
            "admin_email": f"ff-direct-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers",
        headers=ah,
        json={"name": "FF Direct Seller"},
    )
    assert seller.status_code in (200, 201), seller.text
    sid = seller.json()["id"]
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "FF Direct WH", "code": f"ff-direct-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    product = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Габаритный товар",
            "sku_code": f"FF-DIM-{suffix}",
            "seller_id": sid,
            "length_mm": 100,
            "width_mm": 200,
            "height_mm": 300,
            "weight_g": 1250,
        },
    )
    assert product.status_code == 200, product.text

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(
        base,
        headers=ah,
        json={"warehouse_id": wh.json()["id"]},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    assert cr.json()["status"] == "draft"

    line = await async_client.post(
        f"{base}/{rid}/lines",
        headers=ah,
        json={"product_id": product.json()["id"], "expected_qty": 4},
    )
    assert line.status_code == 201, line.text

    begin = await async_client.post(f"{base}/{rid}/begin-receiving", headers=ah)
    assert begin.status_code == 200, begin.text
    data = begin.json()
    assert data["status"] == "receiving"
    assert data["seller_id"] == sid
    assert data["lines"][0]["weight_g"] == 1250
    assert data["lines"][0]["volume_liters"] == pytest.approx(6.0)

    cargo = await async_client.post(
        f"{base}/{rid}/cargo-places",
        headers=ah,
        json={"quantity": 2},
    )
    assert cargo.status_code == 201, cargo.text
    places = cargo.json()
    assert [p["place_number"] for p in places] == [1, 2]
    assert all(p["internal_barcode"].startswith("ICG-") for p in places)

    printed = await async_client.post(
        f"{base}/{rid}/cargo-places/{places[0]['id']}/mark-label-printed",
        headers=ah,
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["label_printed_at"] is not None

    reloaded = await async_client.get(f"{base}/{rid}", headers=ah)
    assert reloaded.status_code == 200, reloaded.text
    loaded_places = reloaded.json()["cargo_places"]
    assert [p["place_number"] for p in loaded_places] == [1, 2]
    assert loaded_places[0]["label_printed_at"] is not None


@pytest.mark.asyncio
async def test_rec03_seller_created_requires_submit_but_ff_created_receives_directly(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "REC03 Co",
            "slug": f"rec03-{suffix}",
            "admin_email": f"rec03-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="REC03 Seller",
        seller_email=f"rec03-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "REC03 WH", "code": f"rec03-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    product = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "REC03 Product",
            "sku_code": f"REC03-{suffix}",
            "seller_id": sid,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert product.status_code == 200, product.text
    pid = product.json()["id"]
    sku = product.json()["sku_code"]
    base = "/operations/inbound-intake-requests"

    seller_doc = await async_client.post(base, headers=sh, json={"warehouse_id": wid})
    assert seller_doc.status_code == 201, seller_doc.text
    seller_doc_id = seller_doc.json()["id"]
    seller_line = await async_client.post(
        f"{base}/{seller_doc_id}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 2},
    )
    assert seller_line.status_code == 201, seller_line.text

    blocked = await async_client.post(f"{base}/{seller_doc_id}/begin-receiving", headers=ah)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "not_submitted"
    still_draft = await async_client.get(f"{base}/{seller_doc_id}", headers=ah)
    assert still_draft.json()["status"] == "draft"

    await _set_planned_boxes(async_client, base, seller_doc_id, sh)
    submitted = await async_client.post(f"{base}/{seller_doc_id}/submit", headers=sh)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    seller_begin = await async_client.post(f"{base}/{seller_doc_id}/begin-receiving", headers=ah)
    assert seller_begin.status_code == 200, seller_begin.text
    assert seller_begin.json()["status"] == "receiving"

    ff_doc = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    assert ff_doc.status_code == 201, ff_doc.text
    ff_doc_id = ff_doc.json()["id"]
    ff_line = await async_client.post(
        f"{base}/{ff_doc_id}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": 3},
    )
    assert ff_line.status_code == 201, ff_line.text
    ff_begin = await async_client.post(f"{base}/{ff_doc_id}/begin-receiving", headers=ah)
    assert ff_begin.status_code == 200, ff_begin.text
    assert ff_begin.json()["status"] == "receiving"

    await fulfill_inbound_via_box_scans(async_client, ah, ff_doc_id, sku, 3)
    verified = await async_client.post(f"{base}/{ff_doc_id}/complete-receiving", headers=ah)
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "sorting"
    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    assert balances.status_code == 200, balances.text
    row = next(item for item in balances.json() if item["product_id"] == pid)
    assert row["quantity"] == 3
    assert row["quantity_in_sorting"] == 3


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
    sku = pr.json()["sku_code"]
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
    await _set_planned_boxes(async_client, base, rid, sh)
    await async_client.post(f"{base}/{rid}/submit", headers=sh)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 10)
    await async_client.post(f"{base}/{rid}/verify", headers=ah)

    r1 = await async_client.post(
        f"{base}/{rid}/lines/{line_id}/receive",
        headers=ah,
        json={"quantity": 3},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "sorting"
    assert r1.json()["lines"][0]["posted_qty"] == 3

    r2 = await async_client.post(
        f"{base}/{rid}/lines/{line_id}/receive",
        headers=ah,
        json={"quantity": 7},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "done"
    assert r2.json()["lines"][0]["posted_qty"] == 10

    mov = await async_client.get(f"{base}/{rid}/movements", headers=ah)
    assert len(mov.json()) == 5


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
    sku = pr.json()["sku_code"]
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

    await _set_planned_boxes(async_client, base, rid, h)
    await async_client.post(f"{base}/{rid}/submit", headers=h)
    await post_primary_accept(async_client, base, rid, h)
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 2)
    await async_client.post(f"{base}/{rid}/verify", headers=h)
    post = await async_client.post(f"{base}/{rid}/post", headers=h)
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "done"


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
    sku = pr.json()["sku_code"]
    base = "/operations/inbound-intake-requests"
    rid = (
        await async_client.post(base, headers=h, json={"warehouse_id": wid})
    ).json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    await _set_planned_boxes(async_client, base, rid, h)
    await async_client.post(f"{base}/{rid}/submit", headers=h)
    await post_primary_accept(async_client, base, rid, h)
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 1)
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


@pytest.mark.asyncio
async def test_inbound_receiving_scan_accepts_planned_local_product_without_wb_ids(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Receiving Local Planned Co",
            "slug": f"recv-local-plan-{suffix}",
            "admin_email": f"recv-local-plan-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Receiving Local Planned Seller",
        seller_email=f"recv-local-plan-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Receiving Local Planned WH", "code": f"recv-local-plan-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    sku = f"RLP-PLAN-{suffix}"
    planned = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Локальный заявленный товар",
            "sku_code": sku,
            "seller_id": sid,
        },
    )
    assert planned.status_code == 200, planned.text
    async with SessionLocal() as session:
        stored = await session.get(Product, uuid.UUID(planned.json()["id"]))
        assert stored is not None
        assert stored.wb_nm_id is None
        assert stored.wb_chrt_id is None

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=sh, json={"warehouse_id": wh.json()["id"]})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 3},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    first_scan = await async_client.post(
        f"{base}/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": sku},
    )
    assert first_scan.status_code == 200, first_scan.text
    assert first_scan.json()["actual_qty"] == 1

    second_scan = await async_client.post(
        f"{base}/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": sku},
    )
    assert second_scan.status_code == 200, second_scan.text
    scanned = second_scan.json()
    assert scanned["product_id"] == planned.json()["id"]
    assert scanned["expected_qty"] == 3
    assert scanned["actual_qty"] == 2
    assert scanned["effective_actual_qty"] == 2
    assert scanned["added_by_fulfillment"] is False


@pytest.mark.asyncio
async def test_inbound_scan_rejects_catalog_product_not_on_request_until_added(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Regular Mix Co",
            "slug": f"reg-mix-{suffix}",
            "admin_email": f"reg-mix-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Regular Seller",
        seller_email=f"reg-mix-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Regular WH", "code": f"reg-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    planned = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Заявленный товар",
            "sku_code": f"REG-PLAN-{suffix}",
            "seller_id": sid,
        },
    )
    assert planned.status_code == 200, planned.text
    arrived_barcode = f"REG-FACT-{suffix}"
    arrived = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Приехавший товар",
            "sku_code": f"REG-ARR-{suffix}",
            "wb_barcode": arrived_barcode,
            "seller_id": sid,
        },
    )
    assert arrived.status_code == 200, arrived.text

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=sh, json={"warehouse_id": wid})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 2},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    scan = await async_client.post(
        f"{base}/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": arrived_barcode},
    )
    assert scan.status_code == 422, scan.text
    assert scan.json()["detail"] == "product_not_on_request"

    fact = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={"product_id": arrived.json()["id"], "actual_qty": 1},
    )
    assert fact.status_code == 201, fact.text
    data = fact.json()
    assert data["product_id"] == arrived.json()["id"]
    assert data["expected_qty"] == 0
    assert data["actual_qty"] == 1
    assert data["effective_actual_qty"] == 1
    assert data["added_by_fulfillment"] is True


@pytest.mark.asyncio
async def test_inbound_receiving_accepts_seller_catalog_product_as_discrepancy(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Return Mix Co",
            "slug": f"ret-mix-{suffix}",
            "admin_email": f"ret-mix-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Return Seller",
        seller_email=f"ret-mix-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Return WH", "code": f"ret-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    planned = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Заявленный цвет",
            "sku_code": f"RET-PLAN-{suffix}",
            "seller_id": sid,
        },
    )
    assert planned.status_code == 200, planned.text
    arrived_barcode = f"RET-FACT-{suffix}"
    arrived = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Приехавший цвет",
            "sku_code": f"RET-ARR-{suffix}",
            "wb_barcode": arrived_barcode,
            "seller_id": sid,
        },
    )
    assert arrived.status_code == 200, arrived.text

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(
        base,
        headers=sh,
        json={"warehouse_id": wid, "operation_type": "return"},
    )
    assert cr.status_code == 201, cr.text
    assert cr.json()["operation_type"] == "return"
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 1},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    scan = await async_client.post(
        f"{base}/{rid}/receiving/scan",
        headers=ah,
        json={"barcode": arrived_barcode},
    )
    assert scan.status_code == 422, scan.text
    assert scan.json()["detail"] == "product_not_on_request"

    fact = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={"product_id": arrived.json()["id"], "actual_qty": 1},
    )
    assert fact.status_code == 201, fact.text
    assert fact.json()["product_id"] == arrived.json()["id"]
    assert fact.json()["expected_qty"] == 0
    assert fact.json()["actual_qty"] == 1
    assert fact.json()["effective_actual_qty"] == 1
    assert fact.json()["added_by_fulfillment"] is True

    done = await async_client.post(f"{base}/{rid}/complete-receiving", headers=ah)
    assert done.status_code == 200, done.text
    data = done.json()
    assert data["has_discrepancy"] is True
    fact_line = next(ln for ln in data["lines"] if ln["product_id"] == arrived.json()["id"])
    assert fact_line["expected_qty"] == 0
    assert fact_line["actual_qty"] == 1


@pytest.mark.asyncio
async def test_inbound_receiving_lines_accepts_same_seller_catalog_product(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Receiving Linked Co",
            "slug": f"recv-linked-{suffix}",
            "admin_email": f"recv-linked-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Receiving Linked Seller",
        seller_email=f"recv-linked-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Receiving Linked WH", "code": f"recv-linked-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    planned = await async_client.post(
        "/products",
        headers=ah,
        json={"name": "Заявленный WB", "sku_code": f"RL-PLAN-{suffix}", "seller_id": sid},
    )
    assert planned.status_code == 200, planned.text
    arrived = await async_client.post(
        "/products",
        headers=ah,
        json={"name": "Фактический WB", "sku_code": f"RL-FACT-{suffix}", "seller_id": sid},
    )
    assert arrived.status_code == 200, arrived.text

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=sh, json={"warehouse_id": wh.json()["id"]})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 1},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    fact = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={"product_id": arrived.json()["id"], "actual_qty": 2},
    )
    assert fact.status_code == 201, fact.text
    data = fact.json()
    assert data["product_id"] == arrived.json()["id"]
    assert data["expected_qty"] == 0
    assert data["actual_qty"] == 2
    assert data["added_by_fulfillment"] is True


@pytest.mark.asyncio
async def test_inbound_receiving_lines_accepts_local_same_seller_catalog_product(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Receiving Boundary Co",
            "slug": f"recv-boundary-{suffix}",
            "admin_email": f"recv-boundary-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Receiving Boundary Seller",
        seller_email=f"recv-boundary-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Receiving Boundary WH", "code": f"recv-boundary-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    planned = await async_client.post(
        "/products",
        headers=ah,
        json={"name": "Заявленный", "sku_code": f"RB-PLAN-{suffix}", "seller_id": sid},
    )
    assert planned.status_code == 200, planned.text
    arrived = await async_client.post(
        "/products",
        headers=ah,
        json={"name": "Фактический товар", "sku_code": f"RB-FACT-{suffix}", "seller_id": sid},
    )
    assert arrived.status_code == 200, arrived.text
    manual = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Ручной факт",
            "sku_code": f"RB-MANUAL-{suffix}",
            "seller_id": sid,
        },
    )
    assert manual.status_code == 200, manual.text

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=sh, json={"warehouse_id": wh.json()["id"]})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 1},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    accepted = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={"product_id": arrived.json()["id"], "actual_qty": 1},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["product_id"] == arrived.json()["id"]
    assert accepted.json()["expected_qty"] == 0
    assert accepted.json()["actual_qty"] == 1
    assert accepted.json()["added_by_fulfillment"] is True

    emergency = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={
            "product_id": manual.json()["id"],
            "actual_qty": 1,
            "source": "manual_created",
        },
    )
    assert emergency.status_code == 422, emergency.text


@pytest.mark.asyncio
async def test_inbound_receiving_lines_rejects_foreign_seller_product(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Receiving Foreign Co",
            "slug": f"recv-foreign-{suffix}",
            "admin_email": f"recv-foreign-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Receiving Owner Seller",
        seller_email=f"recv-owner-seller-{suffix}@example.com",
    )
    _foreign_headers, foreign_sid = await _create_seller_headers(
        async_client,
        admin_headers=ah,
        seller_name="Receiving Foreign Seller",
        seller_email=f"recv-foreign-seller-{suffix}@example.com",
    )
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "Receiving Foreign WH", "code": f"recv-foreign-wh-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    planned = await async_client.post(
        "/products",
        headers=ah,
        json={"name": "Заявленный", "sku_code": f"RF-PLAN-{suffix}", "seller_id": sid},
    )
    assert planned.status_code == 200, planned.text
    foreign = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Чужой WB",
            "sku_code": f"RF-FOREIGN-{suffix}",
            "seller_id": foreign_sid,
        },
    )
    assert foreign.status_code == 200, foreign.text
    await _mark_product_wb_linked(foreign.json()["id"], nm_id=8_200_001)

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=sh, json={"warehouse_id": wh.json()["id"]})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    add = await async_client.post(
        f"{base}/{rid}/lines",
        headers=sh,
        json={"product_id": planned.json()["id"], "expected_qty": 1},
    )
    assert add.status_code == 201, add.text
    await _set_planned_boxes(async_client, base, rid, sh)
    sub = await async_client.post(f"{base}/{rid}/submit", headers=sh)
    assert sub.status_code == 200, sub.text

    rejected = await async_client.post(
        f"{base}/{rid}/receiving/lines",
        headers=ah,
        json={"product_id": foreign.json()["id"], "actual_qty": 1},
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"] == "product_seller_mismatch"
