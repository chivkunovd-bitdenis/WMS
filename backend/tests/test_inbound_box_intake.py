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
    email = f"intake-seller-{suffix}@example.com"
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


async def _submitted_inbound_with_boxes(
    async_client: AsyncClient,
    *,
    suffix: str,
    expected_qty: int = 5,
    box_count: int = 2,
) -> tuple[dict[str, str], str, str, str, list[dict[str, object]]]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Box Intake FF",
            "slug": f"bin-{suffix}",
            "admin_email": f"bin-{suffix}@example.com",
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
    sku = pr.json()["sku_code"]

    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"planned_box_count": box_count},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=sh,
        json={"product_id": pid, "expected_qty": expected_qty},
    )
    await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=sh,
    )
    prim = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/primary-accept",
        headers=ah,
        json={"actual_box_count": box_count},
    )
    assert prim.status_code == 200, prim.text
    boxes = prim.json()["boxes"]
    return ah, rid, pid, sku, boxes


@pytest.mark.asyncio
async def test_inbound_box_intake_scan_and_verify(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    ah, rid, _pid, sku, boxes = await _submitted_inbound_with_boxes(
        async_client, suffix=suffix, expected_qty=5, box_count=2
    )
    base = f"/operations/inbound-intake-requests/{rid}"
    b1 = boxes[0]
    b2 = boxes[1]
    inb1 = str(b1["internal_barcode"])
    inb2 = str(b2["internal_barcode"])

    open1 = await async_client.post(
        f"{base}/boxes/open",
        headers=ah,
        json={"barcode": inb1},
    )
    assert open1.status_code == 200, open1.text
    assert open1.json()["is_open"] is True

    for _ in range(3):
        scan = await async_client.post(
            f"{base}/boxes/{b1['id']}/scan",
            headers=ah,
            json={"barcode": sku},
        )
        assert scan.status_code == 200, scan.text

    close1 = await async_client.post(
        f"{base}/boxes/{b1['id']}/close",
        headers=ah,
    )
    assert close1.status_code == 200, close1.text
    assert close1.json()["intake_closed_at"] is not None

    open2 = await async_client.post(
        f"{base}/boxes/open",
        headers=ah,
        json={"barcode": inb2},
    )
    assert open2.status_code == 200, open2.text

    for _ in range(2):
        scan2 = await async_client.post(
            f"{base}/boxes/{b2['id']}/scan",
            headers=ah,
            json={"barcode": sku},
        )
        assert scan2.status_code == 200, scan2.text

    await async_client.post(f"{base}/boxes/{b2['id']}/close", headers=ah)

    got = await async_client.get(base, headers=ah)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "verifying"
    assert body["lines"][0]["actual_qty"] == 5

    verify = await async_client.post(f"{base}/verify", headers=ah)
    assert verify.status_code == 200, verify.text
    assert verify.json()["status"] == "verified"


@pytest.mark.asyncio
async def test_inbound_product_scan_without_open_box(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 1)
    ah, rid, _pid, sku, boxes = await _submitted_inbound_with_boxes(
        async_client, suffix=suffix, expected_qty=3, box_count=1
    )
    base = f"/operations/inbound-intake-requests/{rid}"
    box_id = boxes[0]["id"]
    scan = await async_client.post(
        f"{base}/boxes/{box_id}/scan",
        headers=ah,
        json={"barcode": sku},
    )
    assert scan.status_code == 409
    assert scan.json()["detail"] == "no_open_box"


@pytest.mark.asyncio
async def test_inbound_manual_actual_blocked_when_boxes_exist(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 2)
    ah, rid, _pid, _sku, boxes = await _submitted_inbound_with_boxes(
        async_client, suffix=suffix, expected_qty=2, box_count=1
    )
    got = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}",
        headers=ah,
    )
    line_id = got.json()["lines"][0]["id"]
    patch = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 2},
    )
    assert patch.status_code == 409
    assert patch.json()["detail"] == "use_box_scan"
    assert boxes


@pytest.mark.asyncio
async def test_inbound_unknown_inb_barcode(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 3)
    ah, rid, *_rest = await _submitted_inbound_with_boxes(
        async_client, suffix=suffix, expected_qty=1, box_count=1
    )
    open_res = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/boxes/open",
        headers=ah,
        json={"barcode": "INB-DEADBEEF0000"},
    )
    assert open_res.status_code == 404
    assert open_res.json()["detail"] == "box_not_found"
