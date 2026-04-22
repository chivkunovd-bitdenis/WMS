from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


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
    assert add_blocked.json()["detail"] == "not_editable"

    del_blocked = await async_client.delete(
        f"/operations/marketplace-unload-requests/{mid}/lines/{line_id}",
        headers=h,
    )
    assert del_blocked.status_code == 409
    assert del_blocked.json()["detail"] == "not_editable"

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
