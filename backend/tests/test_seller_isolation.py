from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_inbound_rejects_second_line_from_different_seller(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Iso Co",
            "slug": f"iso-{suffix}",
            "admin_email": f"iso-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post("/sellers", headers=h, json={"name": "S1"})
    s2 = await async_client.post("/sellers", headers=h, json={"name": "S2"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p1 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"P1-{suffix}",
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
            "sku_code": f"P2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid1 = p1.json()["id"]
    pid2 = p2.json()["id"]

    base = "/operations/inbound-intake-requests"
    rid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    ok = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid1, "expected_qty": 1, "storage_location_id": lid},
    )
    assert ok.status_code == 201
    bad = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid2, "expected_qty": 1, "storage_location_id": lid},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "mixed_seller_lines"


@pytest.mark.asyncio
async def test_outbound_rejects_second_line_from_different_seller(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Iso Out",
            "slug": f"iso-o-{suffix}",
            "admin_email": f"iso-o-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"wo-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "A1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post("/sellers", headers=h, json={"name": "S1"})
    s2 = await async_client.post("/sellers", headers=h, json={"name": "S2"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p1 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"OP1-{suffix}",
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
            "sku_code": f"OP2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid1 = p1.json()["id"]
    pid2 = p2.json()["id"]

    ir = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    in_id = ir.json()["id"]
    await async_client.post(
        f"/operations/inbound-intake-requests/{in_id}/lines",
        headers=h,
        json={
            "product_id": pid1,
            "expected_qty": 10,
            "storage_location_id": lid,
        },
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{in_id}/submit", headers=h
    )
    assert (
        await async_client.post(
            f"/operations/inbound-intake-requests/{in_id}/post", headers=h
        )
    ).status_code == 200

    base = "/operations/outbound-shipment-requests"
    rid = (
        await async_client.post(base, headers=h, json={"warehouse_id": wid})
    ).json()["id"]
    ok = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid1, "quantity": 1, "storage_location_id": lid},
    )
    assert ok.status_code == 201
    bad = await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid2, "quantity": 1, "storage_location_id": lid},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "mixed_seller_lines"


@pytest.mark.asyncio
async def test_seller_does_not_see_inbound_with_other_seller_lines(
    async_client: AsyncClient,
) -> None:
    """If admin somehow had only other seller's lines, seller list is empty."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Vis Co",
            "slug": f"vis-{suffix}",
            "admin_email": f"vis-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"vw-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=h, json={"code": "L1"}
    )
    lid = loc.json()["id"]
    s1 = await async_client.post("/sellers", headers=h, json={"name": "A"})
    s2 = await async_client.post("/sellers", headers=h, json={"name": "B"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]
    p2 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "PB",
            "sku_code": f"VB-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid2 = p2.json()["id"]
    base = "/operations/inbound-intake-requests"
    rid = (await async_client.post(base, headers=h, json={"warehouse_id": wid})).json()[
        "id"
    ]
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=h,
        json={"product_id": pid2, "expected_qty": 2, "storage_location_id": lid},
    )
    await async_client.post(
        "/auth/seller-accounts",
        headers=h,
        json={
            "seller_id": sid1,
            "email": f"vis-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"vis-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    listed = await async_client.get(base, headers=sh)
    assert listed.status_code == 200
    assert listed.json() == []
    g = await async_client.get(f"{base}/{rid}", headers=sh)
    assert g.status_code == 404
