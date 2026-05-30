"""TC-NEW-PKG-02 — packaging instructions on product and MP unload plan/confirm block."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from test_marketplace_unload_and_discrepancy_acts import (
    _link_product_wb_barcode,
    _post_inventory,
    _seller_wb_mp_warehouse,
)


async def _seller_headers(
    async_client: AsyncClient,
    admin_h: dict[str, str],
    seller_id: str,
) -> dict[str, str]:
    email = f"pkg-sl-{time.time()}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_h,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert acc.status_code == 201, acc.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_seller_patches_packaging_instructions(async_client: AsyncClient) -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pkg Instr",
            "slug": f"pkg-i-{suffix}",
            "admin_email": f"pkg-i-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    sel = await async_client.post("/sellers", headers=ah, json={"name": "Brand"})
    seller_id = sel.json()["id"]
    sh = await _seller_headers(async_client, ah, seller_id)

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"PKG-I-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": seller_id,
        },
    )
    pid = pr.json()["id"]

    blocked = await async_client.patch(
        f"/products/{pid}/packaging-instructions",
        headers=sh,
        json={"packaging_instructions": "  "},
    )
    assert blocked.status_code == 200
    assert blocked.json()["packaging_instructions"] is None

    ok = await async_client.patch(
        f"/products/{pid}/packaging-instructions",
        headers=sh,
        json={"packaging_instructions": "Пакет + стикер WB"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["packaging_instructions"] == "Пакет + стикер WB"

    catalog = await async_client.get("/products/wb-catalog", headers=sh)
    assert catalog.status_code == 200
    row = next(x for x in catalog.json() if x["id"] == pid)
    assert row["has_packaging_instructions"] is True


@pytest.mark.asyncio
async def test_mp_plan_blocked_without_packaging_instructions(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pkg Block",
            "slug": f"pkg-b-{suffix}",
            "admin_email": f"pkg-b-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    sh = await _seller_headers(async_client, ah, sid)

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, ah, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    await _post_inventory(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=5, location_code="PB-A"
    )

    create = await async_client.post(
        "/operations/marketplace-unload-requests/seller",
        headers=sh,
        json={"warehouse_id": wid},
    )
    mid = create.json()["id"]
    await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=sh,
        json={"lines": [{"product_id": pid, "quantity": 2}]},
    )
    await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=sh,
        json={"wb_mp_warehouse_id": wb_wid, "planned_shipment_date": "2026-06-01"},
    )

    plan_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan_blocked.status_code == 422
    assert plan_blocked.json()["detail"] == "packaging_instructions_required"

    await async_client.patch(
        f"/products/{pid}/packaging-instructions",
        headers=sh,
        json={"packaging_instructions": "Маркировка"},
    )

    plan_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/plan",
        headers=sh,
    )
    assert plan_ok.status_code == 200, plan_ok.text


@pytest.mark.asyncio
async def test_packaging_task_defaults_to_sorting_location(
    async_client: AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pkg Sort",
            "slug": f"pkg-s-{suffix}",
            "admin_email": f"pkg-s-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wh_id = wh.json()["id"]
    sort_loc = await async_client.get(f"/warehouses/{wh_id}/sorting-location", headers=h)
    assert sort_loc.status_code == 200, sort_loc.text
    sort_id = sort_loc.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Sort P",
            "sku_code": f"sort-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    product_id = pr.json()["id"]

    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=h, json={"warehouse_id": wh_id})
    rid = inbound.json()["id"]
    await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=h,
        json={"product_id": product_id, "expected_qty": 3},
    )
    await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept

    await post_primary_accept(async_client, base_in, rid, h)
    sku = pr.json()["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 3)
    await async_client.post(f"{base_in}/{rid}/verify", headers=h)
    await async_client.post(f"{base_in}/{rid}/post", headers=h)

    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "inbound_intake_request_id": rid,
            "lines": [{"product_id": product_id, "quantity": 2}],
        },
    )
    assert create.status_code == 201, create.text
    task = create.json()
    assert task["lines"][0]["storage_location_id"] == sort_id
    assert task["inbound_intake_request_id"] == rid


@pytest.mark.asyncio
async def test_ff_catalog_includes_packaging_instructions(async_client: AsyncClient) -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Cat",
            "slug": f"ff-cat-{suffix}",
            "admin_email": f"ff-cat-{suffix}@example.com",
            "password": "password123",
        },
    )
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-ffc"})
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "FF Cat",
            "sku_code": f"ffc-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=h, json={"warehouse_id": wh_id})
    rid = inbound.json()["id"]
    await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=h,
        json={"product_id": pid, "expected_qty": 1},
    )
    await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept

    await post_primary_accept(async_client, base_in, rid, h)
    sku = pr.json()["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, 1)
    await async_client.post(f"{base_in}/{rid}/verify", headers=h)
    await async_client.post(f"{base_in}/{rid}/post", headers=h)

    await async_client.patch(
        f"/products/{pid}/packaging-instructions",
        headers=h,
        json={"packaging_instructions": "FF TZ text"},
    )
    cat = await async_client.get("/products/ff-catalog", headers=h)
    assert cat.status_code == 200, cat.text
    row = next(r for r in cat.json() if r["id"] == pid)
    assert row["packaging_instructions"] == "FF TZ text"
    assert row["has_packaging_instructions"] is True
