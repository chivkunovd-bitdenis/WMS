"""TASK-018 / REQ-014: TSD scan API contract smoke tests."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from test_marketplace_unload_and_discrepancy_acts import (
    E2E_BARCODE,
    _finish_unload_packaging,
    _inventory_in_sorting_zone,
    _link_product_wb_barcode,
    _patch_mp_planned_date,
    _patch_packaging_instructions,
    _post_inventory,
    _seller_wb_mp_warehouse,
)

BASE = "/operations/marketplace-unload-requests"


async def _register_headers(async_client: AsyncClient, slug: str) -> dict[str, str]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "TSD Contract FF",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _confirmed_unload_with_open_box(
    async_client: AsyncClient,
    h: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    address_storage_enabled: bool = True,
    plan_qty: int = 3,
) -> tuple[str, str, str, str, str]:
    suffix = str(int(time.time() * 1000))
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-tsd-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)

    patch = await async_client.patch(
        "/tenant/settings",
        headers=h,
        json={"address_storage_enabled": address_storage_enabled},
    )
    assert patch.status_code == 200, patch.text

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "TSD MU",
            "sku_code": f"MU-TSD-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=10,
        location_code=f"MU-TSD-{suffix}",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=10
    )

    mu = await async_client.post(
        BASE,
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"{BASE}/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": plan_qty},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    await async_client.post(f"{BASE}/{mid}/submit", headers=h)
    await _finish_unload_packaging(async_client, h, mid)

    box = await async_client.post(
        f"{BASE}/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    return mid, box.json()["id"], pid, loc_id, wid


@pytest.mark.asyncio
async def test_tsd_box_scan_location_then_product_sequence(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-MP-009: box scan location then product — kind sequence."""
    h = await _register_headers(async_client, f"tsd-seq-{int(time.time())}")
    mid, box_id, _pid, loc_id, wid = await _confirmed_unload_with_open_box(
        async_client, h, monkeypatch, address_storage_enabled=True
    )

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    loc_scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text
    loc_body = loc_scan.json()
    assert loc_body["kind"] == "location"
    assert loc_body["storage_location_id"] == loc_id

    prod_scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
    )
    assert prod_scan.status_code == 200, prod_scan.text
    prod_body = prod_scan.json()
    assert prod_body["kind"] == "product"
    assert prod_body["quantity"] == 1
    assert prod_body["picked_qty"] == 1


@pytest.mark.asyncio
async def test_tsd_box_scan_error_codes_contract(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-MP-009: Negative — location_required, plan_limit_exceeded, packaging_not_done."""
    h = await _register_headers(async_client, f"tsd-err-{int(time.time())}")
    mid, box_id, _pid, loc_id, _wid = await _confirmed_unload_with_open_box(
        async_client, h, monkeypatch, plan_qty=1
    )

    blocked_loc = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE},
    )
    assert blocked_loc.status_code == 422
    assert blocked_loc.json()["detail"] == "location_required"

    ok = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
    )
    assert ok.status_code == 200, ok.text

    over = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id, "quantity": 1},
    )
    assert over.status_code == 422
    assert over.json()["detail"] == "plan_limit_exceeded"


@pytest.mark.asyncio
async def test_tsd_box_scan_packaging_not_done(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-NEW-MP-009: Negative — packaging_not_done blocks box create."""
    h = await _register_headers(async_client, f"tsd-pkg-{int(time.time())}")
    suffix = str(int(time.time() * 1000))
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-pkg-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pkg gate",
            "sku_code": f"PKG-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    assert pr.status_code in (200, 201), pr.text
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code=f"PKG-LOC-{suffix}",
    )
    mu = await async_client.post(
        BASE,
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"{BASE}/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(f"{BASE}/{mid}/submit", headers=h)
    assert sub.status_code == 200, sub.text

    pkg_blocked = await async_client.post(
        f"{BASE}/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert pkg_blocked.status_code == 422
    assert pkg_blocked.json()["detail"] == "packaging_not_done"


@pytest.mark.asyncio
async def test_pick_scan_deprecated_still_works(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backward compat: legacy pick/scan location step remains available."""
    h = await _register_headers(async_client, f"tsd-legacy-{int(time.time())}")
    mid, _box_id, _pid, loc_id, wid = await _confirmed_unload_with_open_box(
        async_client, h, monkeypatch
    )
    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    legacy = await async_client.post(
        f"{BASE}/{mid}/pick/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["kind"] == "location"
