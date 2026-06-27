"""TASK-002: conditional cell requirement in collect/pick API (DEC-005)."""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from test_marketplace_unload_and_discrepancy_acts import (
    E2E_BARCODE,
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
            "organization_name": "Addr Storage FF",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _confirmed_unload_with_box(
    async_client: AsyncClient,
    h: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    address_storage_enabled: bool | None = None,
) -> tuple[str, str, str, str, str]:
    suffix = str(int(time.time() * 1000))
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)

    if address_storage_enabled is not None:
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
            "name": "MU Addr",
            "sku_code": f"MU-AS-{suffix}",
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
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=10,
        location_code=f"MU-AS-{suffix}",
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
        json={"product_id": pid, "quantity": 3},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(f"{BASE}/{mid}/submit", headers=h)
    assert sub.status_code == 200, sub.text

    box = await async_client.post(
        f"{BASE}/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    return mid, box.json()["id"], pid, loc_id, wid


@pytest.mark.asyncio
async def test_collect_without_location_when_address_storage_off(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _register_headers(async_client, f"mu-as-off-{int(time.time())}")
    mid, box_id, pid, _loc_id, _wid = await _confirmed_unload_with_box(
        async_client, h, monkeypatch, address_storage_enabled=False
    )

    manual = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "quantity": 2},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["quantity"] == 2

    scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "quantity": 1},
    )
    assert scan.status_code == 200, scan.text


@pytest.mark.asyncio
async def test_collect_requires_location_when_address_storage_on(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = await _register_headers(async_client, f"mu-as-on-{int(time.time())}")
    mid, box_id, pid, loc_id, wid = await _confirmed_unload_with_box(
        async_client, h, monkeypatch, address_storage_enabled=True
    )

    blocked = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "location_required"

    ok = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 1},
    )
    assert ok.status_code == 200, ok.text

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    loc_scan = await async_client.post(
        f"{BASE}/{mid}/pick/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text
    assert loc_scan.json()["kind"] == "location"

    prod_scan = await async_client.post(
        f"{BASE}/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
    )
    assert prod_scan.status_code == 200, prod_scan.text
