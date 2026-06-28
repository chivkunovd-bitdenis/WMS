from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept
from test_marketplace_unload_and_discrepancy_acts import _seller_wb_mp_warehouse

from app.models.packaging_task import STATUS_DONE, STATUS_IN_PROGRESS


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


async def _inventory_in_sorting_zone(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    warehouse_id: str,
    product_id: str,
    qty: int,
) -> None:
    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=h, json={"warehouse_id": warehouse_id})
    assert inbound.status_code == 201, inbound.text
    rid = inbound.json()["id"]
    line = await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=h,
        json={"product_id": product_id, "expected_qty": qty},
    )
    assert line.status_code == 201, line.text
    await async_client.post(f"{base_in}/{rid}/submit", headers=h)
    await post_primary_accept(async_client, base_in, rid, h)
    sku = line.json()["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, h, rid, sku, qty)
    verify = await async_client.post(f"{base_in}/{rid}/verify", headers=h)
    assert verify.status_code == 200, verify.text


async def _finish_unload_packaging(
    async_client: AsyncClient,
    h: dict[str, str],
    unload_id: str,
) -> None:
    pkg = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{unload_id}",
        headers=h,
    )
    assert pkg.status_code == 200, pkg.text
    task = pkg.json()
    if not task["lines"]:
        task = (
            await async_client.get(f"/operations/packaging-tasks/{task['id']}", headers=h)
        ).json()
    line_id = task["lines"][0]["id"]
    need = task["lines"][0]["qty_need_pack"]
    if need > 0:
        pack = await async_client.post(
            f"/operations/packaging-tasks/{task['id']}/lines/{line_id}/pack",
            headers=h,
            json={"quantity": need},
        )
        assert pack.status_code == 200, pack.text
    complete = await async_client.post(
        f"/operations/packaging-tasks/{task['id']}/complete",
        headers=h,
        json={"acknowledge_all_packed": False},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == STATUS_DONE


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
    assert task.get("document_number", "").startswith("УПАК-")
    assert task["document_number"].endswith("-1")
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
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5
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

    box_before_pack = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box_before_pack.status_code == 201, box_before_pack.text
    box_id = box_before_pack.json()["id"]

    pkg_get = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}",
        headers=h,
    )
    assert pkg_get.status_code == 200, pkg_get.text

    await _finish_unload_packaging(async_client, h, mid)

    manual = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={
            "storage_location_id": loc_id,
            "product_id": product_id,
            "quantity": 3,
        },
    )
    assert manual.status_code == 200, manual.text

    ship_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
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
    await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="PROG-1",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5
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


@pytest.mark.asyncio
async def test_cancel_manual_packaging_task(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-cancel"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Cancel Product",
            "sku_code": f"cncl-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    product_id = pr.json()["id"]
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=3,
        location_code="CNCL-1",
    )
    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 2}],
        },
    )
    assert create.status_code == 201, create.text
    task_id = create.json()["id"]
    cancel = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/cancel",
        headers=h,
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    open_list = await async_client.get("/operations/packaging-tasks", headers=h)
    assert task_id not in {t["id"] for t in open_list.json()}


@pytest.mark.asyncio
async def test_cancel_linked_packaging_task_rejected(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-lnk"})
    wh_id = wh.json()["id"]
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Linked",
            "sku_code": f"lnk-{uuid.uuid4().hex[:6]}",
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
        json={"packaging_instructions": "TZ"},
    )
    await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5, location_code="LNK-1"
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
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/confirm",
        headers=h,
        json={"planned_shipment_date": "2026-06-15"},
    )
    pkg = await async_client.get(f"/operations/packaging-tasks/by-unload/{mid}", headers=h)
    task_id = pkg.json()["id"]
    cancel = await async_client.post(f"/operations/packaging-tasks/{task_id}/cancel", headers=h)
    assert cancel.status_code == 422, cancel.text
    assert cancel.json()["detail"] == "linked_unload"


@pytest.mark.asyncio
async def test_packaging_reopens_when_unload_plan_changes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-reopen"})
    wh_id = wh.json()["id"]
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Reopen",
            "sku_code": f"ro-{uuid.uuid4().hex[:6]}",
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
        json={"packaging_instructions": "TZ"},
    )
    await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=10, location_code="RO-1"
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=10
    )
    mp = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wh_id, "seller_id": seller_id, "wb_mp_warehouse_id": wb_wh_id},
    )
    mid = mp.json()["id"]
    ln = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": product_id, "quantity": 2},
    )
    assert ln.status_code == 201, ln.text
    line_id = ln.json()["id"]
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
    await _finish_unload_packaging(async_client, h, mid)
    task_before = (
        await async_client.get(f"/operations/packaging-tasks/by-unload/{mid}", headers=h)
    ).json()
    assert task_before["status"] == STATUS_DONE

    deleted = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/lines/{line_id}",
        headers=h,
    )
    assert deleted.status_code == 204, deleted.text
    added = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": product_id, "quantity": 4},
    )
    assert added.status_code == 201, added.text
    task_after = (
        await async_client.get(f"/operations/packaging-tasks/by-unload/{mid}", headers=h)
    ).json()
    assert task_after["status"] != STATUS_DONE
    assert task_after["lines"][0]["qty_total"] == 4


@pytest.mark.asyncio
async def test_complete_packaging_explicit(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-cmp"})
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Complete Pkg",
            "sku_code": f"cmp-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    product_id = pr.json()["id"]
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5, location_code="CMP-1"
    )
    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 2}],
        },
    )
    task_id = create.json()["id"]
    line_id = create.json()["lines"][0]["id"]
    incomplete = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=h,
        json={"acknowledge_all_packed": False},
    )
    assert incomplete.status_code == 422
    assert incomplete.json()["detail"] == "packaging_incomplete"

    pack_resp = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 2},
    )
    assert pack_resp.status_code == 200, pack_resp.text
    # REV-FIX-001 / S04: full pack must not auto-complete — only explicit POST /complete.
    after_pack = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=h)
    assert after_pack.status_code == 200, after_pack.text
    assert after_pack.json()["status"] == STATUS_IN_PROGRESS
    assert after_pack.json()["status"] != STATUS_DONE

    done = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=h,
        json={"acknowledge_all_packed": True},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == STATUS_DONE

    pack_blocked = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 1},
    )
    assert pack_blocked.status_code == 422
    assert pack_blocked.json()["detail"] == "bad_status"


@pytest.mark.asyncio
async def test_complete_packaging_marking_not_done(async_client: AsyncClient) -> None:
    """REV-FIX-005 / DEC-014: marked line packed but codes not printed → complete 422."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Mark Gate", "email": f"mg-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-mg"})
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Marked Pkg",
            "sku_code": f"mg-{uuid.uuid4().hex[:6]}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    patch = await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True, "packaging_instructions": "ЧЗ"},
    )
    assert patch.status_code == 200, patch.text
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=3, location_code="MG-1"
    )
    create = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 2}],
        },
    )
    task_id = create.json()["id"]
    line_id = create.json()["lines"][0]["id"]
    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 2},
    )
    assert pack.status_code == 200, pack.text

    blocked = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=h,
        json={"acknowledge_all_packed": True},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "marking_not_done"


@pytest.mark.asyncio
async def test_box_create_allowed_before_packaging_done(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MP-005: boxes available while packaging task is in progress."""
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-box-g"})
    wh_id = wh.json()["id"]
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Box Gate",
            "sku_code": f"bxg-{uuid.uuid4().hex[:6]}",
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
        json={"packaging_instructions": "Pack"},
    )
    await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5, location_code="BOX-G-1"
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5
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
    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text

    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert detail.json()["status"] == "collecting"

    await _finish_unload_packaging(async_client, h, mid)

    box2 = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=h,
        json={"count": 1, "box_preset": "60_40_40"},
    )
    assert box2.status_code == 201, box2.text


@pytest.mark.asyncio
async def test_mp_unload_pack_counter_without_inventory(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MP-004: MP-linked packaging increments qty_packed without inventory convert."""
    from app.core.settings import settings

    h = await _register_admin(async_client)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-mpcnt"})
    wh_id = wh.json()["id"]
    seller_id, wb_wh_id = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Counter Pack",
            "sku_code": f"mpcnt-{uuid.uuid4().hex[:6]}",
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
        json={"packaging_instructions": "Pack"},
    )
    await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=5,
        location_code="MPCNT-1",
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
    pkg = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}",
        headers=h,
    )
    task_id = pkg.json()["id"]
    line_id = pkg.json()["lines"][0]["id"]
    pack = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 2},
    )
    assert pack.status_code == 200, pack.text
    assert pack.json()["lines"][0]["qty_packed_in_task"] == 2
    assert pack.json()["lines"][0]["qty_done"] == 2
