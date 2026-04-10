from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_inbound_intake_flow(async_client: AsyncClient) -> None:
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
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "W1", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"SKU-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(
        base,
        headers=h,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]
    assert cr.json()["status"] == "draft"
    assert cr.json()["lines"] == []

    sub_empty = await async_client.post(f"{base}/{rid}/submit", headers=h)
    assert sub_empty.status_code == 422

    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 5},
    )
    assert ln.status_code == 201, ln.text
    assert ln.json()["expected_qty"] == 5
    assert ln.json()["sku_code"] == f"SKU-{suffix}"

    sub = await async_client.post(f"{base}/{rid}/submit", headers=h)
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"
    assert len(sub.json()["lines"]) == 1

    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=h,
        json={"code": "RCV-01"},
    )
    assert loc.status_code == 200, loc.text
    lid = loc.json()["id"]

    post = await async_client.post(
        f"{base}/{rid}/post",
        headers=h,
        json={"storage_location_id": lid},
    )
    assert post.status_code == 200, post.text
    assert post.json()["status"] == "posted"

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": lid},
    )
    assert bal.status_code == 200, bal.text
    rows = bal.json()
    assert len(rows) == 1
    assert rows[0]["quantity"] == 5
    assert rows[0]["sku_code"] == f"SKU-{suffix}"

    dup_post = await async_client.post(
        f"{base}/{rid}/post",
        headers=h,
        json={"storage_location_id": lid},
    )
    assert dup_post.status_code == 409

    listed = await async_client.get(base, headers=h)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["line_count"] == 1
    assert listed.json()[0]["status"] == "posted"

    closed = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    assert closed.status_code == 409
    assert closed.json()["detail"] == "not_draft"


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


@pytest.mark.asyncio
async def test_inbound_post_wrong_warehouse_location(async_client: AsyncClient) -> None:
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
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    await async_client.post(f"{base}/{rid}/submit", headers=h)
    bad = await async_client.post(
        f"{base}/{rid}/post",
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
