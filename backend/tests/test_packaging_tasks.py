from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept
from test_marketplace_unload_and_discrepancy_acts import _seller_wb_mp_warehouse

from app.models.packaging_task import STATUS_DONE


async def _register_admin(async_client: AsyncClient) -> dict[str, str]:
    email = f"pkg-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pkg FF",
            "slug": f"pkg-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _inventory_at_location(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    warehouse_id: str,
    product_id: str,
    qty: int,
    location_code: str,
) -> str:
    loc = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=h,
        json={"code": location_code},
    )
    assert loc.status_code == 200, loc.text
    location_id = str(loc.json()["id"])
    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=h, json={"warehouse_id": warehouse_id})
    assert inbound.status_code == 201, inbound.text
    rid = inbound.json()["id"]
    line = await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=h,
        json={
            "product_id": product_id,
            "expected_qty": qty,
            "storage_location_id": location_id,
        },
    )
    assert line.status_code == 201, line.text
    await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    await post_primary_accept(async_client, base_in, rid, h)
    sku = line.json()["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, qty)
    verify = await async_client.post(f"{base_in}/{rid}/verify", headers=h)
    assert verify.status_code == 200, verify.text
    post = await async_client.post(f"{base_in}/{rid}/post", headers=h)
    assert post.status_code == 200, post.text
    return location_id


@pytest.mark.asyncio
async def test_packaging_task_manual_convert(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-pkg"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pkg Product",
            "sku_code": f"pkg-sku-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert pr.status_code in (200, 201), pr.text
    product_id = pr.json()["id"]
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=10,
        location_code="PKG-A1",
    )

    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {
                    "product_id": product_id,
                    "storage_location_id": loc_id,
                    "quantity": 6,
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    task = create.json()
    task_id = task["id"]
    line_id = task["lines"][0]["id"]
    assert task["lines"][0]["qty_suggested_packed"] == 0

    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 4},
    )
    assert pack.status_code == 200, pack.text
    assert pack.json()["lines"][0]["qty_packed_in_task"] == 4

    bal = await async_client.get(
        "/operations/inventory-balances",
        headers=h,
        params={"storage_location_id": loc_id},
    )
    assert bal.status_code == 200
    row = next(r for r in bal.json() if r["product_id"] == product_id)
    assert row["quantity"] == 10
    assert row["quantity_unpacked"] == 6
    assert row["quantity_packed"] == 4


@pytest.mark.asyncio
async def test_packaging_blocks_mp_ship_until_done(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-mpkg"})
    wh_id = wh.json()["id"]
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "MP Pkg",
            "sku_code": f"mp-pkg-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"packaging_instructions": "Упаковать в пакет"},
    )
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="MP-PKG-1",
    )

    mp = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wh_id, "seller_id": seller_id, "wb_mp_warehouse_id": wb_wh_id},
    )
    mid = mp.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": product_id, "quantity": 3},
    )
    await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=h,
        json={"planned_shipment_date": "2026-06-15"},
    )
    confirm = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/confirm",
        headers=h,
        json={"planned_shipment_date": "2026-06-15"},
    )
    assert confirm.status_code == 200, confirm.text

    pkg_get = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}",
        headers=h,
    )
    assert pkg_get.status_code == 200, pkg_get.text

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    pick = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/add",
        headers=h,
        json={
            "storage_location_id": loc_id,
            "product_id": product_id,
            "quantity": 3,
        },
    )
    assert pick.status_code == 200, pick.text

    task = (
        await async_client.get(f"/operations/packaging-tasks/by-unload/{mid}", headers=h)
    ).json()
    if not task["lines"]:
        task = (
            await async_client.get(f"/operations/packaging-tasks/{task['id']}", headers=h)
        ).json()
    assert len(task["lines"]) >= 1, task
    line_id = task["lines"][0]["id"]

    ship_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
        json={"acknowledge_discrepancy": True},
    )
    assert ship_blocked.status_code == 422
    assert ship_blocked.json()["detail"] == "packaging_not_done"

    await async_client.post(
        f"/operations/packaging-tasks/{task['id']}/lines/{line_id}/confirm-packed",
        headers=h,
        json={},
    )
    await async_client.post(
        f"/operations/packaging-tasks/{task['id']}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": task["lines"][0]["qty_need_pack"]},
    )
    done_task = await async_client.get(
        f"/operations/packaging-tasks/{task['id']}",
        headers=h,
    )
    assert done_task.json()["status"] == STATUS_DONE

    ship_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
        json={"acknowledge_discrepancy": True},
    )
    assert ship_ok.status_code == 200, ship_ok.text


@pytest.mark.asyncio
async def test_mp_unload_detail_includes_packaging_progress(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-prog"})
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Prog",
            "sku_code": f"prog-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"packaging_instructions": "Pack it"},
    )
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="PROG-1",
    )
    mp = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wh_id, "seller_id": seller_id, "wb_mp_warehouse_id": wb_wh_id},
    )
    mid = mp.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": product_id, "quantity": 2},
    )
    await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=h,
        json={"planned_shipment_date": "2026-06-15"},
    )
    confirm = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/confirm",
        headers=h,
        json={"planned_shipment_date": "2026-06-15"},
    )
    assert confirm.status_code == 200, confirm.text
    pkg_after_confirm = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}",
        headers=h,
    )
    assert pkg_after_confirm.status_code == 200, pkg_after_confirm.text
    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    pick = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/add",
        headers=h,
        json={
            "storage_location_id": loc_id,
            "product_id": product_id,
            "quantity": 2,
        },
    )
    assert pick.status_code == 200, pick.text
    detail = await async_client.get(f"/operations/marketplace-unload-requests/{mid}", headers=h)
    assert detail.status_code == 200, detail.text
    linked = detail.json()["linked_packaging_task"]
    assert linked is not None
    assert linked["qty_total"] == 2
    assert linked["qty_done"] == 0
    assert linked["is_complete"] is False

    task = linked
    line_id = (
        await async_client.get(f"/operations/packaging-tasks/{task['task_id']}", headers=h)
    ).json()["lines"][0]["id"]
    await async_client.post(
        f"/operations/packaging-tasks/{task['task_id']}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 2},
    )
    detail2 = await async_client.get(f"/operations/marketplace-unload-requests/{mid}", headers=h)
    linked2 = detail2.json()["linked_packaging_task"]
    assert linked2["qty_done"] == 2
    assert linked2["is_complete"] is True
