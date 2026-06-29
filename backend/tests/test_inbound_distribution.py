from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeRequest


@pytest.mark.asyncio
async def test_inbound_distribution_lines_validate_limits_and_lock(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dist Co",
            "slug": f"dist-{suffix}",
            "admin_email": f"dist-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"d-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=ah,
        json={"code": "A-01"},
    )
    assert loc.status_code == 200, loc.text
    lid = loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-D-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
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
        json={"product_id": pid, "expected_qty": 5},
    )
    assert ln.status_code == 201, ln.text

    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    prim = await post_primary_accept(async_client, base, rid, ah)
    assert prim.status_code == 200, prim.text
    assert prim.json()["status"] == "receiving"

    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 5)
    ver = await async_client.post(f"{base}/{rid}/verify", headers=ah)
    assert ver.status_code == 200, ver.text
    assert ver.json()["status"] == "sorting"

    got = await async_client.get(f"{base}/{rid}", headers=ah)
    assert got.status_code == 200, got.text
    box_id = got.json()["boxes"][0]["id"]

    after_verify_bal = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
    )
    assert after_verify_bal.status_code == 200, after_verify_bal.text
    row_verify = next(r for r in after_verify_bal.json() if r["product_id"] == pid)
    assert row_verify["quantity"] == 5
    assert row_verify["quantity_in_sorting"] == 5
    assert row_verify["quantity_in_storage"] == 0

    too_much = await async_client.put(
        f"{base}/{rid}/distribution-lines",
        headers=ah,
        json=[
            {
                "box_id": box_id,
                "product_id": pid,
                "storage_location_id": lid,
                "quantity": 6,
            }
        ],
    )
    assert too_much.status_code == 422, too_much.text
    assert too_much.json()["detail"] in (
        "qty_exceeds_accepted",
        "qty_exceeds_box_remaining",
    )

    partial = await async_client.post(
        f"{base}/{rid}/boxes/{box_id}/putaway",
        headers={**ah, "Content-Type": "application/json"},
        json={
            "storage_location_id": lid,
            "lines": [{"product_id": pid, "quantity": 2}],
        },
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["lines"][0]["posted_qty"] == 2
    box_after = partial.json()["boxes"][0]
    assert box_after["remaining_qty"] == 3

    rest = await async_client.post(
        f"{base}/{rid}/boxes/{box_id}/putaway",
        headers={**ah, "Content-Type": "application/json"},
        json={"storage_location_id": lid},
    )
    assert rest.status_code == 200, rest.text
    done = rest
    assert done.json()["status"] == "done"
    assert done.json()["lines"][0]["posted_qty"] == 5

    movements = await async_client.get(f"{base}/{rid}/movements", headers=ah)
    assert movements.status_code == 200, movements.text
    deltas = sorted(m["quantity_delta"] for m in movements.json())
    assert deltas.count(5) == 1  # приход в зону сортировки при verify
    assert 2 in deltas and 3 in deltas  # разкладка по ячейке

    balances = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
    )
    assert balances.status_code == 200, balances.text
    balance_row = next(r for r in balances.json() if r["product_id"] == pid)
    assert balance_row["quantity"] == 5
    assert balance_row["quantity_in_sorting"] == 0
    assert balance_row["quantity_in_storage"] == 5

    ff_catalog = await async_client.get("/products/ff-catalog", headers=ah)
    assert ff_catalog.status_code == 200, ff_catalog.text
    assert pid in {r["id"] for r in ff_catalog.json()}

    locked = await async_client.post(
        f"{base}/{rid}/boxes/{box_id}/putaway",
        headers={**ah, "Content-Type": "application/json"},
        json={
            "storage_location_id": lid,
            "lines": [{"product_id": pid, "quantity": 1}],
        },
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"] == "not_distributable"


@pytest.mark.asyncio
async def test_resync_sorting_stock_idempotent(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Resync Co",
            "slug": f"resync-{suffix}",
            "admin_email": f"resync-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"rs-{suffix}"},
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=ah,
        json={"code": "R-01"},
    )
    lid = loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-R-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    cr = await async_client.post(base, headers=ah, json={"warehouse_id": wid})
    rid = cr.json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": 5},
    )
    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 5)
    ver = await async_client.post(f"{base}/{rid}/verify", headers=ah)
    assert ver.status_code == 200, ver.text

    resync = await async_client.post(f"{base}/{rid}/resync-sorting-stock", headers=ah)
    assert resync.status_code == 200, resync.text

    put = await async_client.post(
        f"{base}/{rid}/boxes/{resync.json()['boxes'][0]['id']}/putaway",
        headers={**ah, "Content-Type": "application/json"},
        json={"storage_location_id": lid},
    )
    assert put.status_code == 200, put.text


@pytest.mark.asyncio
async def test_empty_distribution_complete_rejected(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dist Empty Co",
            "slug": f"dist-empty-{suffix}",
            "admin_email": f"dist-empty-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"de-{suffix}"},
    )
    wid = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-DE-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    rid = (await async_client.post(base, headers=ah, json={"warehouse_id": wid})).json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines", headers=ah, json={"product_id": pid, "expected_qty": 3}
    )
    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 3)
    await async_client.post(f"{base}/{rid}/verify", headers=ah)

    done = await async_client.post(f"{base}/{rid}/distribution-complete", headers=ah)
    assert done.status_code == 422, done.text
    assert done.json()["detail"] == "distribution_incomplete"


@pytest.mark.asyncio
async def test_distribution_reopen_after_stuck_lock(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dist Reopen Co",
            "slug": f"dist-reopen-{suffix}",
            "admin_email": f"dist-reopen-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"dr-{suffix}"},
    )
    wid = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"SKU-DR-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    sku = pr.json()["sku_code"]

    base = "/operations/inbound-intake-requests"
    rid = (await async_client.post(base, headers=ah, json={"warehouse_id": wid})).json()["id"]
    await async_client.post(
        f"{base}/{rid}/lines", headers=ah, json={"product_id": pid, "expected_qty": 2}
    )
    await async_client.post(f"{base}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base, rid, ah)
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 2)
    await async_client.post(f"{base}/{rid}/verify", headers=ah)

    async with SessionLocal() as session:
        req = await session.get(InboundIntakeRequest, uuid.UUID(rid))
        assert req is not None
        req.distribution_completed_at = datetime.now(UTC)
        await session.commit()

    reopen = await async_client.post(f"{base}/{rid}/distribution-reopen", headers=ah)
    assert reopen.status_code == 200, reopen.text
    assert reopen.json()["distribution_completed_at"] is None

