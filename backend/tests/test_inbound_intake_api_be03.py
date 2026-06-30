"""IN-BE-03: inbound intake API — new receiving flow without primary-accept."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _admin_headers(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"INBE03 FF {suffix}",
            "slug": f"inbe03-{suffix}",
            "admin_email": f"inbe03-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _submitted_request(
    async_client: AsyncClient,
    ah: dict[str, str],
    suffix: str,
    *,
    expected_qty: int = 5,
) -> tuple[str, str, str]:
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
        },
    )
    assert pr.status_code == 200, pr.text
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    assert cr.status_code == 201, cr.text
    rid = cr.json()["id"]

    ln = await async_client.post(
        f"{base}/{rid}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": expected_qty},
    )
    assert ln.status_code == 201, ln.text

    sub = await async_client.post(f"{base}/{rid}/submit", headers=ah)
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "submitted"

    return rid, pid, sku


@pytest.mark.asyncio
async def test_primary_accept_endpoint_removed(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: legacy primary-accept route is gone."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix)
    res = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/primary-accept",
        headers=ah,
        json={"actual_box_count": 0},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_loose_scan_increments_actual(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: receiving/scan +1 to loose intake, not the last box."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)
    base = f"/operations/inbound-intake-requests/{rid}"

    first_box = await async_client.post(f"{base}/boxes", headers=ah)
    assert first_box.status_code == 201, first_box.text
    second_box = await async_client.post(f"{base}/boxes", headers=ah)
    assert second_box.status_code == 201, second_box.text

    for i in range(3):
        scan = await async_client.post(
            f"{base}/receiving/scan",
            headers=ah,
            json={"barcode": sku},
        )
        assert scan.status_code == 200, scan.text
        assert scan.json()["actual_qty"] == i + 1

    got = await async_client.get(base, headers=ah)
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "receiving"
    assert body["lines"][0]["actual_qty"] == 3
    last_box = next(b for b in body["boxes"] if b["id"] == second_box.json()["id"])
    assert last_box["lines"] == []


@pytest.mark.asyncio
async def test_loose_scan_unknown_barcode_422(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: foreign barcode → product_not_on_request."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix)
    base = f"/operations/inbound-intake-requests/{rid}"

    bad = await async_client.post(
        f"{base}/receiving/scan",
        headers=ah,
        json={"barcode": "UNKNOWN-BARCODE-999"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "product_not_on_request"


@pytest.mark.asyncio
async def test_manual_actual_qty_absolute(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: PATCH line actual sets absolute quantity."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=10)
    base = f"/operations/inbound-intake-requests/{rid}"

    await async_client.post(
        f"{base}/receiving/scan",
        headers=ah,
        json={"barcode": sku},
    )

    got = await async_client.get(base, headers=ah)
    line_id = got.json()["lines"][0]["id"]

    patch = await async_client.patch(
        f"{base}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 7},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["actual_qty"] == 7


@pytest.mark.asyncio
async def test_create_box_and_scan_into_box(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: on-demand boxes stay independent and completion does not require close."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=4)
    base = f"/operations/inbound-intake-requests/{rid}"

    box1 = await async_client.post(f"{base}/boxes", headers=ah)
    assert box1.status_code == 201, box1.text
    box2 = await async_client.post(f"{base}/boxes", headers=ah)
    assert box2.status_code == 201, box2.text
    box3 = await async_client.post(f"{base}/boxes", headers=ah)
    assert box3.status_code == 201, box3.text
    assert [
        box1.json()["box_number"],
        box2.json()["box_number"],
        box3.json()["box_number"],
    ] == [1, 2, 3]

    box2_id = box2.json()["id"]
    for _ in range(4):
        scan = await async_client.post(
            f"{base}/boxes/{box2_id}/scan",
            headers=ah,
            json={"barcode": sku},
        )
        assert scan.status_code == 200, scan.text

    done = await async_client.post(f"{base}/complete-receiving", headers=ah)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "sorting"
    assert [b["box_number"] for b in body["boxes"]] == [1, 2, 3]
    box2_body = next(b for b in body["boxes"] if b["box_number"] == 2)
    assert box2_body["lines"][0]["quantity"] == 4


@pytest.mark.asyncio
async def test_complete_receiving_with_discrepancy(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: complete-receiving sets has_discrepancy when fact ≠ plan."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=5)
    base = f"/operations/inbound-intake-requests/{rid}"

    for _ in range(3):
        await async_client.post(
            f"{base}/receiving/scan",
            headers=ah,
            json={"barcode": sku},
        )

    done = await async_client.post(f"{base}/complete-receiving", headers=ah)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "sorting"
    assert body["has_discrepancy"] is True
    assert body["lines"][0]["actual_qty"] == 3


@pytest.mark.asyncio
async def test_complete_receiving_mixed_box_then_loose_api(
    async_client: AsyncClient,
) -> None:
    """REV-IN-BE-01: API box scan + loose manual + complete-receiving → total=10."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=10)
    base = f"/operations/inbound-intake-requests/{rid}"

    box = await async_client.post(f"{base}/boxes", headers=ah)
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    for _ in range(6):
        scan = await async_client.post(
            f"{base}/boxes/{box_id}/scan",
            headers=ah,
            json={"barcode": sku},
        )
        assert scan.status_code == 200, scan.text

    close = await async_client.post(f"{base}/boxes/{box_id}/close", headers=ah)
    assert close.status_code == 200, close.text

    got = await async_client.get(base, headers=ah)
    line_id = got.json()["lines"][0]["id"]
    assert got.json()["lines"][0]["actual_qty"] in (None, 0)

    patch = await async_client.patch(
        f"{base}/lines/{line_id}/actual",
        headers=ah,
        json={"actual_qty": 4},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["actual_qty"] == 4

    done = await async_client.post(f"{base}/complete-receiving", headers=ah)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "sorting"
    assert body["lines"][0]["actual_qty"] == 10
    assert body["has_discrepancy"] is False


@pytest.mark.asyncio
async def test_complete_receiving_no_discrepancy(async_client: AsyncClient) -> None:
    """TC-NEW-IN-BE-03: complete-receiving clean when fact matches plan."""
    suffix = str(int(time.time() * 1000))
    ah = await _admin_headers(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=2)
    base = f"/operations/inbound-intake-requests/{rid}"

    for _ in range(2):
        await async_client.post(
            f"{base}/receiving/scan",
            headers=ah,
            json={"barcode": sku},
        )

    done = await async_client.post(f"{base}/complete-receiving", headers=ah)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["has_discrepancy"] is False
    assert body["status"] == "sorting"
