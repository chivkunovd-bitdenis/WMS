from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_seller_outbound_draft_create_and_line_own_sku_only(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Out Seller Co",
            "slug": f"out-sel-{suffix}",
            "admin_email": f"out-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "A1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post("/sellers", headers=ah, json={"name": "S1"})
    s2 = await async_client.post("/sellers", headers=ah, json={"name": "S2"})
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p_own = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Mine",
            "sku_code": f"OM-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid1,
        },
    )
    p_other = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Theirs",
            "sku_code": f"OT-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid_own = p_own.json()["id"]
    pid_other = p_other.json()["id"]

    base_in = "/operations/inbound-intake-requests"
    rid_in = (
        await async_client.post(base_in, headers=ah, json={"warehouse_id": wid})
    ).json()["id"]
    await async_client.post(
        f"{base_in}/{rid_in}/lines",
        headers=ah,
        json={
            "product_id": pid_own,
            "expected_qty": 10,
            "storage_location_id": lid,
        },
    )
    await async_client.post(f"{base_in}/{rid_in}/submit", headers=ah)
    await async_client.post(f"{base_in}/{rid_in}/primary-accept", headers=ah)
    inb = await async_client.get(f"{base_in}/{rid_in}", headers=ah)
    line_id = inb.json()["lines"][0]["id"]
    await async_client.patch(
        f"{base_in}/{rid_in}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 10},
    )
    await async_client.post(f"{base_in}/{rid_in}/verify", headers=ah)
    await async_client.post(f"{base_in}/{rid_in}/post", headers=ah)

    seller_email = f"out-sl-{suffix}@example.com"
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid1,
            "email": seller_email,
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    base_out = "/operations/outbound-shipment-requests"
    create = await async_client.post(
        base_out,
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert create.status_code == 201, create.text
    rid = create.json()["id"]

    listed = await async_client.get(base_out, headers=sh)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    bad_line = await async_client.post(
        f"{base_out}/{rid}/lines",
        headers=sh,
        json={
            "product_id": pid_other,
            "quantity": 1,
            "storage_location_id": lid,
        },
    )
    assert bad_line.status_code == 422
    assert bad_line.json()["detail"] == "product_seller_mismatch"

    ok_line = await async_client.post(
        f"{base_out}/{rid}/lines",
        headers=sh,
        json={
            "product_id": pid_own,
            "quantity": 2,
            "storage_location_id": lid,
        },
    )
    assert ok_line.status_code == 201, ok_line.text

    submit403 = await async_client.post(f"{base_out}/{rid}/submit", headers=sh)
    assert submit403.status_code == 403
