from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import (
    complete_inbound_to_storage,
    fulfill_inbound_via_box_scans,
    post_primary_accept,
)

from app.services.background_job_service import JOB_TYPE_WILDBERRIES_CARDS_SYNC

E2E_BARCODE = "2045526738950"


async def _link_product_wb_barcode(
    async_client: AsyncClient,
    h: dict[str, str],
    *,
    seller_id: str,
    product_id: str,
    monkeypatch: pytest.MonkeyPatch,
    barcode: str = E2E_BARCODE,
) -> None:
    async def fake_cards(
        client: object,
        *,
        api_token: str,
        content_api_base: str | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        return {
            "cards": [
                {
                    "nmID": 555001,
                    "vendorCode": "VC-MU",
                    "sizes": [{"skus": [barcode]}],
                }
            ],
            "cursor": {},
        }

    monkeypatch.setattr(
        "app.services.wildberries_sync_service.fetch_cards_list",
        fake_cards,
    )
    await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=h,
        json={"content_api_token": "wb-content-test"},
    )
    start = await async_client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": JOB_TYPE_WILDBERRIES_CARDS_SYNC, "seller_id": seller_id},
    )
    jid = start.json()["id"]
    for _ in range(40):
        await asyncio.sleep(0.12)
        jr = await async_client.get(f"/operations/background-jobs/{jid}", headers=h)
        if jr.json()["status"] == "done":
            break
    link = await async_client.post(
        f"/integrations/wildberries/sellers/{seller_id}/link-product",
        headers=h,
        json={"product_id": product_id, "nm_id": 555001},
    )
    assert link.status_code == 200, link.text


async def _seller_wb_mp_warehouse(
    async_client: AsyncClient,
    h: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, int]:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", True)
    sel = await async_client.post("/sellers", headers=h, json={"name": "WB Seller"})
    assert sel.status_code == 201, sel.text
    sid = sel.json()["id"]
    tok = await async_client.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        headers=h,
        json={"supplies_api_token": "wb-supplies-test-token"},
    )
    assert tok.status_code == 200, tok.text
    whs = await async_client.get("/operations/wb-mp-warehouses", headers=h)
    assert whs.status_code == 200, whs.text
    rows = whs.json()
    assert len(rows) >= 1
    return sid, int(rows[0]["wb_warehouse_id"])


async def _post_inventory(
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
    assert complete.json()["status"] == "done"


async def _patch_mp_planned_date(
    async_client: AsyncClient,
    h: dict[str, str],
    mid: str,
    planned_date: str = "2026-06-01",
) -> None:
    patch = await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=h,
        json={"planned_shipment_date": planned_date},
    )
    assert patch.status_code == 200, patch.text


async def _patch_packaging_instructions(
    async_client: AsyncClient,
    h: dict[str, str],
    product_id: str,
    *,
    instructions: str = "E2E packaging instructions",
) -> None:
    patch = await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"packaging_instructions": instructions},
    )
    assert patch.status_code == 200, patch.text


@pytest.mark.asyncio
async def test_marketplace_unload_and_discrepancy_act_crud_smoke(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Unload Co",
            "slug": f"unload-{suffix}",
            "admin_email": f"unload-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    assert wh.status_code == 200
    wid = wh.json()["id"]

    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)

    mu_empty = await async_client.get("/operations/marketplace-unload-requests", headers=h)
    assert mu_empty.status_code == 200
    assert mu_empty.json() == []

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    assert mu.status_code == 201, mu.text
    mbody = mu.json()
    assert mbody["status"] == "draft"
    assert mbody["warehouse_id"] == wid
    assert mbody["line_count"] == 0

    mu_list = await async_client.get("/operations/marketplace-unload-requests", headers=h)
    assert mu_list.status_code == 200
    assert len(mu_list.json()) == 1

    da = await async_client.post(
        "/operations/discrepancy-acts",
        headers=h,
        json={},
    )
    assert da.status_code == 201, da.text
    assert da.json()["status"] == "draft"

    da_list = await async_client.get("/operations/discrepancy-acts", headers=h)
    assert da_list.status_code == 200
    assert len(da_list.json()) == 1


@pytest.mark.asyncio
async def test_marketplace_unload_unknown_warehouse(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "BadWh Co",
            "slug": f"badwh-{suffix}",
            "admin_email": f"badwh-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    assert wh.status_code == 200
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)

    bad = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={
            "warehouse_id": str(uuid.uuid4()),
            "seller_id": sid,
            "wb_mp_warehouse_id": wb_wid,
        },
    )
    assert bad.status_code == 404
    assert bad.json()["detail"] == "warehouse_not_found"


@pytest.mark.asyncio
async def test_discrepancy_act_bad_inbound(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Div Co",
            "slug": f"div-{suffix}",
            "admin_email": f"div-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    bad = await async_client.post(
        "/operations/discrepancy-acts",
        headers=h,
        json={"inbound_intake_request_id": str(uuid.uuid4())},
    )
    assert bad.status_code == 404
    assert bad.json()["detail"] == "inbound_not_found"


@pytest.mark.asyncio
async def test_marketplace_unload_add_line_and_detail(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Line Co",
            "slug": f"line-{suffix}",
            "admin_email": f"line-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    pr_no_stock = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "No stock",
            "sku_code": f"NS-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid_no_stock = pr_no_stock.json()["id"]
    await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-L1",
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    assert mu.json()["line_count"] == 0

    det0 = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det0.status_code == 200
    assert det0.json()["lines"] == []

    no_stock_ln = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid_no_stock, "quantity": 1},
    )
    assert no_stock_ln.status_code == 422
    assert no_stock_ln.json()["detail"] == "insufficient_available"

    ln = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3},
    )
    assert ln.status_code == 201, ln.text

    det = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det.status_code == 200
    assert len(det.json()["lines"]) == 1
    assert det.json()["lines"][0]["quantity"] == 3

    lst = await async_client.get("/operations/marketplace-unload-requests", headers=h)
    assert lst.json()[0]["line_count"] == 1

    dup = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_discrepancy_act_add_line(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "DivLine Co",
            "slug": f"divl-{suffix}",
            "admin_email": f"divl-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P2",
            "sku_code": f"S2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid = pr.json()["id"]
    da = await async_client.post("/operations/discrepancy-acts", headers=h, json={})
    aid = da.json()["id"]
    ln = await async_client.post(
        f"/operations/discrepancy-acts/{aid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 2},
    )
    assert ln.status_code == 201
    det = await async_client.get(f"/operations/discrepancy-acts/{aid}", headers=h)
    assert len(det.json()["lines"]) == 1


@pytest.mark.asyncio
async def test_marketplace_unload_submit_delete_and_blocks(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuFin Co",
            "slug": f"mufin-{suffix}",
            "admin_email": f"mufin-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-BLOCK",
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    ln = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 2},
    )
    line_id = ln.json()["id"]
    bad_del = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/lines/{uuid.uuid4()}",
        headers=h,
    )
    assert bad_del.status_code == 404
    assert bad_del.json()["detail"] == "line_not_found"

    await _patch_packaging_instructions(async_client, h, pid)
    await _patch_mp_planned_date(async_client, h, mid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit",
        headers=h,
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "confirmed"

    dup_sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit",
        headers=h,
    )
    assert dup_sub.status_code == 409
    assert dup_sub.json()["detail"] == "bad_status"

    add_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    assert add_blocked.status_code == 409
    assert add_blocked.json()["detail"] == "duplicate_line"

    del_confirmed = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/lines/{line_id}",
        headers=h,
    )
    assert del_confirmed.status_code == 204

    mu2 = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid2 = mu2.json()["id"]
    ln2 = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid2}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    lid2 = ln2.json()["id"]
    ok_del = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid2}/lines/{lid2}",
        headers=h,
    )
    assert ok_del.status_code == 204
    det2 = await async_client.get(f"/operations/marketplace-unload-requests/{mid2}", headers=h)
    assert det2.json()["lines"] == []


@pytest.mark.asyncio
async def test_marketplace_unload_allows_draft_without_wb_warehouse_and_requires_it_on_submit(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuNoWb Co",
            "slug": f"munowb-{suffix}",
            "admin_email": f"munowb-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    assert wh.status_code == 200
    wid = wh.json()["id"]

    # Create seller without WB warehouses cached.
    sel = await async_client.post("/sellers", headers=h, json={"name": "Seller"})
    assert sel.status_code == 201
    sid = sel.json()["id"]

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": None},
    )
    assert mu.status_code == 201, mu.text
    mid = mu.json()["id"]

    det0 = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det0.status_code == 200
    assert det0.json()["status"] == "draft"
    assert det0.json()["wb_mp_warehouse_id"] is None

    # Submit is blocked until WB MP warehouse is selected.
    sub_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=h
    )
    assert sub_blocked.status_code == 409
    assert sub_blocked.json()["detail"] == "wb_mp_warehouse_required"

    # When WB warehouses appear, we can set it and then submit.
    _sid2, wb_wid = await _seller_wb_mp_warehouse(async_client, h, monkeypatch)
    patch = await async_client.patch(
        f"/operations/marketplace-unload-requests/{mid}",
        headers=h,
        json={"wb_mp_warehouse_id": wb_wid},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["wb_mp_warehouse_id"] == wb_wid

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
    pid = pr.json()["id"]
    await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=2,
        location_code="MU-NOWB",
    )
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )

    sub_no_date = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=h
    )
    assert sub_no_date.status_code == 409
    assert sub_no_date.json()["detail"] == "planned_shipment_date_required"

    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=h
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_discrepancy_act_submit_and_inbound_line_rules(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "DaFin Co",
            "slug": f"dafin-{suffix}",
            "admin_email": f"dafin-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w2-{suffix}"}
    )
    wid = wh.json()["id"]
    p1 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P1",
            "sku_code": f"S1-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    p2 = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "P2",
            "sku_code": f"S2-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    pid1 = p1.json()["id"]
    pid2 = p2.json()["id"]

    inbound = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wid},
    )
    assert inbound.status_code == 201, inbound.text
    rid = inbound.json()["id"]
    in_ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=h,
        json={"product_id": pid1, "expected_qty": 3},
    )
    assert in_ln.status_code == 201, in_ln.text
    inbound_line_id = in_ln.json()["id"]

    da_free = await async_client.post("/operations/discrepancy-acts", headers=h, json={})
    aid_free = da_free.json()["id"]
    need_inbound = await async_client.post(
        f"/operations/discrepancy-acts/{aid_free}/lines",
        headers=h,
        json={
            "product_id": pid1,
            "quantity": 1,
            "inbound_intake_line_id": inbound_line_id,
        },
    )
    assert need_inbound.status_code == 422
    assert need_inbound.json()["detail"] == "inbound_link_required"

    da = await async_client.post(
        "/operations/discrepancy-acts",
        headers=h,
        json={"inbound_intake_request_id": rid},
    )
    assert da.status_code == 201, da.text
    aid = da.json()["id"]

    wrong_ln = await async_client.post(
        f"/operations/discrepancy-acts/{aid}/lines",
        headers=h,
        json={
            "product_id": pid1,
            "quantity": 1,
            "inbound_intake_line_id": str(uuid.uuid4()),
        },
    )
    assert wrong_ln.status_code == 404
    assert wrong_ln.json()["detail"] == "inbound_line_not_found"

    mismatch = await async_client.post(
        f"/operations/discrepancy-acts/{aid}/lines",
        headers=h,
        json={
            "product_id": pid2,
            "quantity": 1,
            "inbound_intake_line_id": inbound_line_id,
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"] == "product_mismatch"

    ok_ln = await async_client.post(
        f"/operations/discrepancy-acts/{aid}/lines",
        headers=h,
        json={
            "product_id": pid1,
            "quantity": 2,
            "inbound_intake_line_id": inbound_line_id,
        },
    )
    assert ok_ln.status_code == 201, ok_ln.text
    assert ok_ln.json()["inbound_intake_line_id"] == inbound_line_id

    sub = await async_client.post(f"/operations/discrepancy-acts/{aid}/submit", headers=h)
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "confirmed"

    add_after = await async_client.post(
        f"/operations/discrepancy-acts/{aid}/lines",
        headers=h,
        json={"product_id": pid1, "quantity": 1},
    )
    assert add_after.status_code == 409
    assert add_after.json()["detail"] == "not_editable"


@pytest.mark.asyncio
async def test_marketplace_unload_ship_deducts_stock_by_pick_and_scan(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuShip Co",
            "slug": f"muship-{suffix}",
            "admin_email": f"muship-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-SHIP",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=5
    )

    bal_before = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=h,
        params={"warehouse_id": wid},
    )
    assert bal_before.status_code == 200
    row_before = next(x for x in bal_before.json() if x["product_id"] == pid)
    assert row_before["quantity"] == 10

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3},
    )

    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit",
        headers=h,
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "confirmed"

    ship_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship_blocked.status_code == 422
    assert ship_blocked.json()["detail"] == "packaging_not_done"

    await _finish_unload_packaging(async_client, h, mid)

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    loc_scan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text
    assert loc_scan.json()["kind"] == "location"

    for _ in range(3):
        prod_scan = await async_client.post(
            f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/scan",
            headers=h,
            json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
        )
        assert prod_scan.status_code == 200, prod_scan.text

    detail = await async_client.get(f"/operations/marketplace-unload-requests/{mid}", headers=h)
    assert detail.json()["lines"][0]["picked_qty"] == 3

    bal_after_collect = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=h,
        params={"warehouse_id": wid},
    )
    row_collect = next(x for x in bal_after_collect.json() if x["product_id"] == pid)
    assert row_collect["quantity"] == 7

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship.status_code == 200, ship.text
    assert ship.json()["status"] == "shipped"

    bal_after = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=h,
        params={"warehouse_id": wid},
    )
    row_after = next(x for x in bal_after.json() if x["product_id"] == pid)
    assert row_after["quantity"] == 7

    ship_again = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship_again.status_code == 409
    assert ship_again.json()["detail"] == "bad_status"


@pytest.mark.asyncio
async def test_marketplace_unload_ship_no_double_inventory_movement(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TASK-004: stock deducted at collect; ship must not create second movements
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuNoDouble Co",
            "slug": f"mund-{suffix}",
            "admin_email": f"mund-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-NODBL",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=5
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 2},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=h)
    await _finish_unload_packaging(async_client, h, mid)

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    box_id = box.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 2},
    )

    mov_before_ship = await async_client.get("/operations/inventory-movements", headers=h)
    mp_moves_before = [
        m
        for m in mov_before_ship.json()
        if m.get("movement_type") == "marketplace_unload" and m.get("product_id") == pid
    ]
    assert len(mp_moves_before) == 1
    assert mp_moves_before[0]["quantity_delta"] == -2

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship.status_code == 200, ship.text

    mov_after_ship = await async_client.get("/operations/inventory-movements", headers=h)
    mp_moves_after = [
        m
        for m in mov_after_ship.json()
        if m.get("movement_type") == "marketplace_unload" and m.get("product_id") == pid
    ]
    assert len(mp_moves_after) == 1


@pytest.mark.asyncio
async def test_marketplace_unload_concurrent_collect_same_location(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TASK-004 / DEC-017: parallel collect from one cell must not oversell
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuConc Co",
            "slug": f"muc-{suffix}",
            "admin_email": f"muc-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-CONC",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=5
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 5},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=h)
    await _finish_unload_packaging(async_client, h, mid)

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    async def collect() -> int:
        resp = await async_client.post(
            f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
            headers=h,
            json={"product_id": pid, "storage_location_id": loc_id, "quantity": 4},
        )
        return resp.status_code

    assert await collect() == 200
    blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
        headers=h,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 4},
    )
    assert blocked.status_code == 422
    assert blocked.json()["detail"] == "plan_limit_exceeded"

    bal = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=h,
        params={"warehouse_id": wid},
    )
    row = next(x for x in bal.json() if x["product_id"] == pid)
    assert row["quantity"] == 6


@pytest.mark.asyncio
async def test_marketplace_unload_ship_deletes_empty_boxes(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TASK-004 / DEC-002: empty boxes removed on ship
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuEmpty Co",
            "slug": f"mue-{suffix}",
            "admin_email": f"mue-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-EMPTY",
    )
    await _inventory_in_sorting_zone(
        async_client, h, warehouse_id=wid, product_id=pid, qty=5
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 1},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=h)
    await _finish_unload_packaging(async_client, h, mid)

    filled = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert filled.status_code == 201, filled.text
    filled_id = filled.json()["id"]

    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{filled_id}/manual-line",
        headers=h,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 1},
    )
    close_filled = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{filled_id}/close",
        headers=h,
    )
    assert close_filled.status_code == 200, close_filled.text

    empty = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert empty.status_code == 201, empty.text
    empty_id = empty.json()["id"]

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship.status_code == 200, ship.text

    detail = await async_client.get(f"/operations/marketplace-unload-requests/{mid}", headers=h)
    box_ids = {b["id"] for b in detail.json()["boxes"]}
    assert filled_id in box_ids
    assert empty_id not in box_ids


@pytest.mark.asyncio
async def test_marketplace_unload_ship_blocked_when_distribution_incomplete(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TASK-014 / DEC-010: ship without full box distribution is rejected
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "MuPartial Co",
            "slug": f"mup-{suffix}",
            "admin_email": f"mup-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _link_product_wb_barcode(
        async_client, h, seller_id=sid, product_id=pid, monkeypatch=monkeypatch
    )
    loc_id = await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MU-PART",
    )
    await _inventory_in_sorting_zone(async_client, h, warehouse_id=wid, product_id=pid, qty=5)

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3},
    )
    await _patch_mp_planned_date(async_client, h, mid)
    await _patch_packaging_instructions(async_client, h, pid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=h)
    await _finish_unload_packaging(async_client, h, mid)

    loc = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    loc_barcode = next(x for x in loc.json() if x["id"] == loc_id)["barcode"]

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=h,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]

    loc_scan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/pick/scan",
        headers=h,
        json={"barcode": loc_barcode},
    )
    assert loc_scan.status_code == 200, loc_scan.text

    prod_scan = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/scan",
        headers=h,
        json={"barcode": E2E_BARCODE, "storage_location_id": loc_id},
    )
    assert prod_scan.status_code == 200, prod_scan.text

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
    )
    assert ship.status_code == 422
    assert ship.json()["detail"] == "distribution_incomplete"

    ship_ack = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=h,
        json={"acknowledge_discrepancy": True},
    )
    assert ship_ack.status_code == 200, ship_ack.text
    assert ship_ack.json()["status"] == "shipped"
    assert ship_ack.json()["ff_modified"] is True
    line = ship_ack.json()["lines"][0]
    assert line["picked_qty"] == 1
    assert line["has_discrepancy"] is True


@pytest.mark.asyncio
async def test_marketplace_unload_packaging_task_only_on_confirm(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-003: no packaging task on draft; task created on confirm with plan lines."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pkg Sync Co",
            "slug": f"pkg-sync-{suffix}",
            "admin_email": f"pkg-sync-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses", headers=h, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
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
    pid = pr.json()["id"]
    await _post_inventory(
        async_client,
        h,
        warehouse_id=wid,
        product_id=pid,
        qty=10,
        location_code="PKG-L1",
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    assert mu.status_code == 201, mu.text
    mid = mu.json()["id"]

    det0 = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det0.status_code == 200, det0.text
    assert det0.json()["status"] == "draft"
    assert det0.json()["linked_packaging_task"] is None

    by_unload0 = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}", headers=h
    )
    assert by_unload0.status_code == 404, by_unload0.text

    ln = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 3},
    )
    assert ln.status_code == 201, ln.text

    det_draft_lines = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det_draft_lines.json()["linked_packaging_task"] is None

    replaced = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"lines": [{"product_id": pid, "quantity": 5}]},
    )
    assert replaced.status_code == 200, replaced.text

    detail_after_replace = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert detail_after_replace.status_code == 200, detail_after_replace.text
    line_id = detail_after_replace.json()["lines"][0]["id"]

    deleted = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/lines/{line_id}",
        headers=h,
    )
    assert deleted.status_code == 204, deleted.text

    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=h,
        json={"product_id": pid, "quantity": 4},
    )
    await _patch_mp_planned_date(async_client, h, mid)

    confirm = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/confirm",
        headers=h,
        json={"planned_shipment_date": "2026-06-01"},
    )
    assert confirm.status_code == 200, confirm.text

    by_unload1 = await async_client.get(
        f"/operations/packaging-tasks/by-unload/{mid}", headers=h
    )
    assert by_unload1.status_code == 200, by_unload1.text
    task_id = by_unload1.json()["id"]
    assert len(by_unload1.json()["lines"]) == 1
    assert by_unload1.json()["lines"][0]["qty_total"] == 4

    det_confirmed = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=h
    )
    assert det_confirmed.json()["linked_packaging_task"]["task_id"] == task_id
    assert det_confirmed.json()["linked_packaging_task"]["qty_total"] == 4


@pytest.mark.asyncio
async def test_marketplace_unload_pick_allocations_admin_only(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-005: PUT pick-allocations — только админ FF; staff получает 403."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "PickAlloc Co",
            "slug": f"pickalloc-{suffix}",
            "admin_email": f"adm-pick-{suffix}@example.com",
            "password": "password123",
        },
    )
    admin_tok = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {admin_tok}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-pa-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-pa-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    loc_id = await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="PA-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=5
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 2},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah)
    await _finish_unload_packaging(async_client, ah, mid)
    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text

    staff_email = f"staff-pa-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=ah,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=ah,
        json={
            "settings": False,
            "mp_shipments": True,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": False,
        },
    )
    await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    staff_forbidden = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/pick-allocations",
        headers=sh,
        json={
            "allocations": [
                {
                    "product_id": pid,
                    "storage_location_id": loc_id,
                    "quantity": 1,
                }
            ]
        },
    )
    assert staff_forbidden.status_code == 403
    assert staff_forbidden.json()["detail"] == "admin_only"

    admin_ok = await async_client.put(
        f"/operations/marketplace-unload-requests/{mid}/pick-allocations",
        headers=ah,
        json={
            "allocations": [
                {
                    "product_id": pid,
                    "storage_location_id": loc_id,
                    "quantity": 1,
                }
            ]
        },
    )
    assert admin_ok.status_code == 200, admin_ok.text
    assert len(admin_ok.json()) >= 1


@pytest.mark.asyncio
async def test_marketplace_unload_create_boxes_batch(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REV-FIX-002 / S05: POST boxes/batch создаёт N открытых коробов и ШК."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "BatchBox Co",
            "slug": f"batchbox-{suffix}",
            "admin_email": f"adm-bb-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-bb-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-bb-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    loc_id = await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="BB-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=3
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 2},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah
    )
    assert sub.status_code == 200, sub.text
    await _finish_unload_packaging(async_client, ah, mid)

    invalid_count = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 0, "box_preset": "60_40_40"},
    )
    assert invalid_count.status_code == 422

    batch = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 3, "box_preset": "60_40_40"},
    )
    assert batch.status_code == 201, batch.text
    boxes = batch.json()
    assert len(boxes) == 3
    barcodes = {b["internal_barcode"] for b in boxes}
    assert len(barcodes) == 3
    assert all(b["closed_at"] is None for b in boxes)
    assert all(b["lines"] == [] for b in boxes)

    second_box_id = boxes[1]["id"]
    manual = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{second_box_id}/manual-line",
        headers=ah,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 1},
    )
    assert manual.status_code == 200, manual.text

    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    assert len(detail.json()["boxes"]) == 3


@pytest.mark.asyncio
async def test_marketplace_unload_create_boxes_batch_one_by_one(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REV-FIX-009: два последовательных batch create по 1 коробу — без open_box_exists."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "BatchOne Co",
            "slug": f"batchone-{suffix}",
            "admin_email": f"adm-bo-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-bo-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-bo-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="BO-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=3
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 2},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah)
    await _finish_unload_packaging(async_client, ah, mid)

    first = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 1, "box_preset": "60_40_40"},
    )
    assert first.status_code == 201, first.text
    first_boxes = first.json()
    assert len(first_boxes) == 1
    assert first_boxes[0]["closed_at"] is None

    second = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 1, "box_preset": "60_40_40"},
    )
    assert second.status_code == 201, second.text
    second_boxes = second.json()
    assert len(second_boxes) == 1
    assert second_boxes[0]["closed_at"] is None
    assert second_boxes[0]["id"] != first_boxes[0]["id"]

    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    assert len(detail.json()["boxes"]) == 2


@pytest.mark.asyncio
async def test_marketplace_unload_attach_allow_over_plan(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-019: attach готового короба сверх плана при allow_over_plan=true."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "AttachOP Co",
            "slug": f"attop-{suffix}",
            "admin_email": f"adm-ao-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-ao-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-ao-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    loc_id = await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=30,
        location_code=f"L-ao-{suffix}",
    )

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 10},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah
    )
    assert sub.status_code == 200, sub.text

    base_in = "/operations/inbound-intake-requests"
    inbound = await async_client.post(base_in, headers=ah, json={"warehouse_id": wid})
    assert inbound.status_code == 201, inbound.text
    rid = inbound.json()["id"]
    await async_client.post(
        f"{base_in}/{rid}/lines",
        headers=ah,
        json={"product_id": pid, "expected_qty": 15},
    )
    await async_client.post(f"{base_in}/{rid}/submit", headers=ah)
    await post_primary_accept(async_client, base_in, rid, ah)
    got = await async_client.get(f"{base_in}/{rid}", headers=ah)
    assert got.status_code == 200, got.text
    body = got.json()
    whb = body["boxes"][0]["internal_barcode"]
    sku = body["lines"][0]["sku_code"]
    await fulfill_inbound_via_box_scans(async_client, ah, rid, sku, 15)
    verify = await async_client.post(f"{base_in}/{rid}/verify", headers=ah)
    assert verify.status_code == 200, verify.text
    await complete_inbound_to_storage(
        async_client,
        ah,
        rid,
        product_id=pid,
        storage_location_id=loc_id,
        quantity=15,
    )

    blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/attach",
        headers=ah,
        json={"barcode": whb, "box_preset": "60_40_40", "allow_over_plan": False},
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["detail"] == "plan_limit_exceeded"

    ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/attach",
        headers=ah,
        json={"barcode": whb, "box_preset": "60_40_40", "allow_over_plan": True},
    )
    assert ok.status_code == 201, ok.text
    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    picked = sum(
        int(ln["quantity"])
        for b in detail.json()["boxes"]
        for ln in b["lines"]
        if ln["product_id"] == pid
    )
    assert picked == 15


@pytest.mark.asyncio
async def test_marketplace_unload_box_remove_copy_delete(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-010 / DEC-007: remove line rolls back stock; delete only empty; copy within plan."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "BoxAct Co",
            "slug": f"boxact-{suffix}",
            "admin_email": f"adm-ba-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-ba-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-ba-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    loc_id = await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=10,
        location_code="BA-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=5
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 5},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    await _patch_packaging_instructions(async_client, ah, pid)
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah
    )
    await _finish_unload_packaging(async_client, ah, mid)

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]
    add = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
        headers=ah,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 4},
    )
    assert add.status_code == 200, add.text
    line_id = add.json()["id"]

    bal_after_collect = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    row_after = next(x for x in bal_after_collect.json() if x["product_id"] == pid)
    assert row_after["quantity"] == 11

    blocked_delete = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}",
        headers=ah,
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["detail"] == "box_not_empty"

    remove = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/lines/{line_id}/remove",
        headers=ah,
        json={"quantity": 2},
    )
    assert remove.status_code == 200, remove.text
    assert remove.json()["quantity"] == 2

    bal_after_remove = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    row_removed = next(x for x in bal_after_remove.json() if x["product_id"] == pid)
    assert row_removed["quantity"] == 13

    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/lines/{line_id}/remove",
        headers=ah,
        json={},
    )
    empty_delete = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}",
        headers=ah,
    )
    assert empty_delete.status_code == 204, empty_delete.text

    box2 = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    box2_id = box2.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box2_id}/manual-line",
        headers=ah,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 2},
    )
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box2_id}/close",
        headers=ah,
    )

    copy_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box2_id}/copy",
        headers=ah,
    )
    assert copy_ok.status_code == 201, copy_ok.text
    copied = copy_ok.json()
    assert copied["closed_at"]
    detail_after_copy = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    copied_box = next(
        b for b in detail_after_copy.json()["boxes"] if b["id"] == copied["id"]
    )
    assert len(copied_box["lines"]) == 1
    assert copied_box["lines"][0]["quantity"] == 2

    copy_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box2_id}/copy",
        headers=ah,
    )
    assert copy_blocked.status_code == 422
    assert copy_blocked.json()["detail"] == "plan_limit_exceeded"


@pytest.mark.asyncio
async def test_marketplace_unload_box_ops_allowed_before_packaging_done(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MP-005: create box / batch allowed while packaging in progress."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "PkgGate Co",
            "slug": f"pkggate-{suffix}",
            "admin_email": f"pkggate-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-pg-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-pg-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="PG-LOC",
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 2},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah
    )
    assert sub.status_code == 200, sub.text

    box_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box_ok.status_code == 201, box_ok.text

    batch_ok = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 2, "box_preset": "60_40_40"},
    )
    assert batch_ok.status_code == 201, batch_ok.text
    assert len(batch_ok.json()) == 2


@pytest.mark.asyncio
async def test_marketplace_unload_ship_rejects_empty_boxes_only(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-015/016: ship requires full box distribution; empty boxes are not enough."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "EmptyBox Co",
            "slug": f"emptybox-{suffix}",
            "admin_email": f"emptybox-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-eb-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-eb-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="EB-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=5
    )
    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 3},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    await async_client.post(f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah)
    await _finish_unload_packaging(async_client, ah, mid)

    batch = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/batch",
        headers=ah,
        json={"count": 2, "box_preset": "60_40_40"},
    )
    assert batch.status_code == 201, batch.text
    assert all(b["lines"] == [] for b in batch.json())

    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=ah,
    )
    assert ship.status_code == 422
    assert ship.json()["detail"] == "distribution_incomplete"


@pytest.mark.asyncio
async def test_marketplace_unload_cancel_partial_distribution_restores_inventory(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TASK-019 / DEC-016: cancel before ship rolls back box stock and clears reserves."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "CancelMu Co",
            "slug": f"cancelmu-{suffix}",
            "admin_email": f"cancelmu-{suffix}@example.com",
            "password": "password123",
        },
    )
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-cancel-{suffix}"}
    )
    wid = wh.json()["id"]
    sid, wb_wid = await _seller_wb_mp_warehouse(async_client, ah, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"S-cancel-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    pid = pr.json()["id"]
    await _patch_packaging_instructions(async_client, ah, pid)
    loc_id = await _post_inventory(
        async_client,
        ah,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="CANCEL-LOC",
    )
    await _inventory_in_sorting_zone(
        async_client, ah, warehouse_id=wid, product_id=pid, qty=5
    )

    bal_before = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    row_before = next(x for x in bal_before.json() if x["product_id"] == pid)
    assert row_before["quantity"] == 10

    mu = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid = mu.json()["id"]
    await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 5},
    )
    await _patch_mp_planned_date(async_client, ah, mid)
    sub = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/submit", headers=ah
    )
    assert sub.status_code == 200, sub.text
    await _finish_unload_packaging(async_client, ah, mid)

    box = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes",
        headers=ah,
        json={"box_preset": "60_40_40"},
    )
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]
    add = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/boxes/{box_id}/manual-line",
        headers=ah,
        json={"product_id": pid, "storage_location_id": loc_id, "quantity": 2},
    )
    assert add.status_code == 200, add.text

    bal_partial = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    row_partial = next(x for x in bal_partial.json() if x["product_id"] == pid)
    assert row_partial["quantity"] == 8

    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=ah)
    sorting_id = next(x for x in locs.json() if x["code"] == "__SORTING__")["id"]
    bal_loc_before = await async_client.get(
        "/operations/inventory-balances",
        headers=ah,
        params={"storage_location_id": loc_id},
    )
    bal_sort_before = await async_client.get(
        "/operations/inventory-balances",
        headers=ah,
        params={"storage_location_id": sorting_id},
    )
    loc_qty_before = next(x for x in bal_loc_before.json() if x["product_id"] == pid)["quantity"]
    sort_qty_before = next(x for x in bal_sort_before.json() if x["product_id"] == pid)["quantity"]

    detail_partial = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    assert detail_partial.json()["lines"][0]["picked_qty"] == 2
    assert detail_partial.json()["boxes"][0]["lines"][0]["quantity"] == 2

    cancel = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/cancel",
        headers=ah,
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"

    detail_cancel = await async_client.get(
        f"/operations/marketplace-unload-requests/{mid}", headers=ah
    )
    body = detail_cancel.json()
    assert body["lines"][0]["picked_qty"] == 0
    assert all(box["lines"] == [] for box in body["boxes"])

    bal_after = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=ah,
        params={"warehouse_id": wid},
    )
    row_after = next(x for x in bal_after.json() if x["product_id"] == pid)
    assert row_after["quantity"] == row_before["quantity"]

    bal_loc_after = await async_client.get(
        "/operations/inventory-balances",
        headers=ah,
        params={"storage_location_id": loc_id},
    )
    bal_sort_after = await async_client.get(
        "/operations/inventory-balances",
        headers=ah,
        params={"storage_location_id": sorting_id},
    )
    loc_qty_after = next(x for x in bal_loc_after.json() if x["product_id"] == pid)["quantity"]
    sort_qty_after = next(x for x in bal_sort_after.json() if x["product_id"] == pid)["quantity"]
    assert loc_qty_after == loc_qty_before
    assert sort_qty_after == sort_qty_before + 2

    mu2 = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=ah,
        json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid},
    )
    mid2 = mu2.json()["id"]
    add_line = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid2}/lines",
        headers=ah,
        json={"product_id": pid, "quantity": 3},
    )
    assert add_line.status_code == 201, add_line.text
    await _patch_mp_planned_date(async_client, ah, mid2)
    sub2 = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid2}/submit", headers=ah
    )
    assert sub2.status_code == 200, sub2.text

    ship_blocked = await async_client.post(
        f"/operations/marketplace-unload-requests/{mid}/ship",
        headers=ah,
    )
    assert ship_blocked.status_code == 409
    assert ship_blocked.json()["detail"] == "bad_status"
