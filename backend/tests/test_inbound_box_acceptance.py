from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _seller_headers(
    async_client: AsyncClient,
    *,
    admin_headers: dict[str, str],
    suffix: str,
) -> tuple[dict[str, str], str]:
    s = await async_client.post(
        "/sellers",
        headers=admin_headers,
        json={"name": f"S-{suffix}"},
    )
    assert s.status_code in (200, 201), s.text
    sid = s.json()["id"]
    email = f"box-seller-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": sid, "email": email, "password": "password123"},
    )
    assert acc.status_code in (200, 201), acc.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, sid


@pytest.mark.asyncio
async def test_inbound_box_plan_vs_actual_discrepancy(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Box FF",
            "slug": f"box-{suffix}",
            "admin_email": f"box-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _seller_headers(async_client, admin_headers=ah, suffix=suffix)

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"sku-{suffix}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]

    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    patch = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"planned_box_count": 3},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["planned_box_count"] == 3

    ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 10},
    )
    assert ln.status_code == 201, ln.text

    sub = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=sh,
    )
    assert sub.status_code == 200, sub.text

    base = f"/operations/inbound-intake-requests/{rid}"
    from inbound_box_intake_helpers import post_primary_accept

    prim = await post_primary_accept(
        async_client,
        "/operations/inbound-intake-requests",
        rid,
        ah,
        actual_box_count=0,
        create_boxes=False,
    )
    assert prim.status_code == 200, prim.text
    assert prim.json()["status"] == "receiving"

    box1 = await async_client.post(f"{base}/boxes", headers=ah)
    assert box1.status_code == 201, box1.text
    close1 = await async_client.post(
        f"{base}/boxes/{box1.json()['id']}/close", headers=ah
    )
    assert close1.status_code == 200, close1.text
    box2 = await async_client.post(f"{base}/boxes", headers=ah)
    assert box2.status_code == 201, box2.text

    got = await async_client.get(base, headers=ah)
    assert got.status_code == 200, got.text
    body = got.json()
    assert len(body["boxes"]) == 2
    nums = sorted(b["box_number"] for b in body["boxes"])
    assert nums == [1, 2]
    for b in body["boxes"]:
        assert b["internal_barcode"].startswith("INB-")
        assert b["label_printed_at"] is None


@pytest.mark.asyncio
async def test_on_demand_boxes_and_mark_label(async_client: AsyncClient) -> None:
    """On-demand POST /boxes creates boxes; label can be marked printed."""
    suffix = str(int(time.time() * 1000) + 1)
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Box3",
            "slug": f"box3-{suffix}",
            "admin_email": f"box3-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sh, sid = await _seller_headers(async_client, admin_headers=ah, suffix=suffix)
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w3-{suffix}"},
    )
    wid = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"sku3-{suffix}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={"warehouse_id": wid},
    )
    rid = cr.json()["id"]
    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"planned_box_count": 2},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": 1},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=sh,
    )
    base = f"/operations/inbound-intake-requests/{rid}"
    from inbound_box_intake_helpers import post_primary_accept

    await post_primary_accept(
        async_client,
        "/operations/inbound-intake-requests",
        rid,
        ah,
        actual_box_count=0,
        create_boxes=False,
    )
    b1 = await async_client.post(f"{base}/boxes", headers=ah)
    assert b1.status_code == 201, b1.text
    await async_client.post(f"{base}/boxes/{b1.json()['id']}/close", headers=ah)
    b2 = await async_client.post(f"{base}/boxes", headers=ah)
    assert b2.status_code == 201, b2.text
    got = await async_client.get(base, headers=ah)
    box_ids = [b["id"] for b in got.json()["boxes"]]
    mark = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_ids[0]}/mark-label-printed",
        headers=ah,
    )
    assert mark.status_code == 200, mark.text
    assert mark.json()["label_printed_at"] is not None


@pytest.mark.asyncio
async def test_patch_rejects_invalid_planned_box_count(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Box2",
            "slug": f"box2-{suffix}",
            "admin_email": f"box2-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w2-{suffix}"},
    )
    wid = wh.json()["id"]
    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid},
    )
    rid = cr.json()["id"]
    bad = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=ah,
        json={"planned_box_count": 0},
    )
    assert bad.status_code == 422
