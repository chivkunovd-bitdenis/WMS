"""WMS-058: box scans preserve the explicit source and never pick packed stock twice."""

from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from test_marketplace_unload_and_discrepancy_acts import (  # type: ignore[import-not-found]
    E2E_BARCODE,
    _link_product_wb_barcode,
    _patch_mp_planned_date,
    _patch_packaging_instructions,
    _post_inventory,
    _seller_wb_mp_warehouse,
)
from test_marketplace_unload_pick_from_container import (  # type: ignore[import-not-found]
    _balances_by_container,
    _loose_balance_id,
)

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import MarketplaceUnloadPickAllocation

BoxFixture = tuple[dict[str, str], str, str, str, str, str, str, str, str, str]


@pytest_asyncio.fixture
async def box_fixture(async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> BoxFixture:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "PickBox Co",
            "slug": f"pickbox-{suffix}",
            "admin_email": f"pickbox-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = str(wh.json()["id"])
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = str(pr.json()["id"])
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )

    # Пять штук приходят россыпью в ячейку.
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="PICK-BOX",
    )

    # Заводим короб, ставим его в ту же ячейку и перекладываем в него три штуки.
    box = await async_client.post(
        f"/warehouses/{wid}/sorting-objects", headers=h, json={"kind": "box"}
    )
    assert box.status_code == 201, box.text
    box_id = str(box.json()["id"])
    box_barcode = str(box.json()["barcode"])

    place = await async_client.post(
        f"/warehouses/{wid}/map/move",
        headers=h,
        json={"kind": "box", "id": box_id, "to_kind": "cell", "to_id": loc_id, "qty": 1},
    )
    assert place.status_code == 200, place.text

    balance_id = await _loose_balance_id(loc_id, pid)

    into_box = await async_client.post(
        f"/warehouses/{wid}/map/move",
        headers=h,
        json={
            "kind": "product",
            "id": balance_id,
            "to_kind": "box",
            "to_id": box_id,
            "qty": 3,
        },
    )
    assert into_box.status_code == 200, into_box.text

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = str(mu.json()["id"])
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=h
    )
    assert sub.status_code == 200, sub.text

    target = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert target.status_code == 201, target.text
    base = f"/operations/marketplace-unload-requests/{mid}"
    scan = f"{base}/boxes/{target.json()['id']}/scan"
    return h, wid, pid, loc_id, box_id, box_barcode, mid, base, scan, target.json()["id"]


async def movement_count(mid: str) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(InventoryMovement)
                .where(InventoryMovement.marketplace_unload_request_id == uuid.UUID(mid))
            )
            or 0
        )


@pytest.mark.asyncio
async def test_box_scan_keeps_container_and_loose_allocations_separate(
    async_client: AsyncClient, box_fixture: BoxFixture
) -> None:
    h, _, pid, loc, source, barcode, mid, _, scan, _ = box_fixture
    selected = await async_client.post(scan, headers=h, json={"barcode": barcode})
    assert selected.status_code == 200, selected.text
    assert selected.json()["kind"] == "container"
    assert selected.json()["container_id"] == source
    assert await movement_count(mid) == 0
    body = {"barcode": E2E_BARCODE, "product_id": pid, "storage_location_id": loc}
    loose = await async_client.post(scan, headers=h, json=body)
    assert loose.status_code == 200, loose.text
    body.update(container_kind="box", container_id=source)
    picked = await async_client.post(scan, headers=h, json=body)
    assert picked.status_code == 200, picked.text
    assert await _balances_by_container(loc, pid) == {None: 1, source: 2}
    async with SessionLocal() as session:
        allocations = (
            await session.scalars(
                select(MarketplaceUnloadPickAllocation).where(
                    MarketplaceUnloadPickAllocation.request_id == uuid.UUID(mid)
                )
            )
        ).all()
        assert {
            (a.container_kind, str(a.container_id) if a.container_id else None, a.quantity)
            for a in allocations
        } == {(None, None, 1), ("box", source, 1)}


@pytest.mark.asyncio
async def test_box_scan_places_previously_picked_without_new_inventory(
    async_client: AsyncClient, box_fixture: BoxFixture
) -> None:
    h, _, pid, loc, source, _, mid, base, scan, _ = box_fixture
    pick = await async_client.post(
        base + "/pick/set",
        headers=h,
        json={
            "product_id": pid,
            "storage_location_id": loc,
            "quantity": 3,
            "container_kind": "box",
            "container_id": source,
        },
    )
    assert pick.status_code == 200, pick.text
    before = await _balances_by_container(loc, pid)
    count = await movement_count(mid)
    for expected in range(1, 4):
        response = await async_client.post(
            scan,
            headers=h,
            json={
                "barcode": E2E_BARCODE,
                "product_id": pid,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["quantity"] == expected
        assert response.json()["picked_qty"] == 3
    assert await _balances_by_container(loc, pid) == before
    assert await movement_count(mid) == count


@pytest.mark.asyncio
async def test_box_scan_rejects_invalid_or_exhausted_source_without_fallback(
    async_client: AsyncClient, box_fixture: BoxFixture
) -> None:
    h, _, pid, loc, source, _, mid, _, scan, _ = box_fixture
    body = {
        "barcode": E2E_BARCODE,
        "product_id": pid,
        "storage_location_id": loc,
        "container_kind": "box",
        "container_id": source,
    }
    bad = await async_client.post(
        scan, headers=h, json={**body, "storage_location_id": str(uuid.uuid4())}
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["detail"] == "invalid_container_reference"
    missing = await async_client.post(
        scan, headers=h, json={**body, "container_id": str(uuid.uuid4())}
    )
    assert missing.status_code == 422, missing.text
    assert await movement_count(mid) == 0
    for _ in range(3):
        response = await async_client.post(scan, headers=h, json=body)
        assert response.status_code == 200, response.text
    before = await _balances_by_container(loc, pid)
    failed = await async_client.post(scan, headers=h, json=body)
    assert failed.status_code == 422, failed.text
    assert failed.json()["detail"] == "insufficient_available"
    assert await _balances_by_container(loc, pid) == before
    assert before[None] == 2


@pytest.mark.asyncio
async def test_mixed_box_scan_failure_does_not_commit_placement(
    async_client: AsyncClient,
    box_fixture: BoxFixture,
) -> None:
    h, _, pid, loc, source, _, mid, base, scan, target = box_fixture
    picked = await async_client.post(
        base + "/pick/set",
        headers=h,
        json={
            "product_id": pid,
            "storage_location_id": loc,
            "quantity": 1,
            "container_kind": "box",
            "container_id": source,
        },
    )
    assert picked.status_code == 200, picked.text
    before = await _balances_by_container(loc, pid)
    movements = await movement_count(mid)
    failed = await async_client.post(
        scan,
        headers=h,
        json={
            "barcode": E2E_BARCODE,
            "product_id": pid,
            "quantity": 4,
            "storage_location_id": loc,
            "container_kind": "box",
            "container_id": source,
        },
    )
    assert failed.status_code == 422, failed.text
    assert failed.json()["detail"] == "insufficient_available"
    detail = await async_client.get(base, headers=h)
    assert detail.status_code == 200, detail.text
    destination = next(box for box in detail.json()["boxes"] if box["id"] == target)
    assert destination["lines"] == []
    assert await _balances_by_container(loc, pid) == before
    assert await movement_count(mid) == movements
    assert sum(row["quantity"] for row in detail.json()["pick_allocations"]) == 1
