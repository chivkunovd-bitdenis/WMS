from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import post_primary_accept


@pytest.mark.asyncio
async def test_seller_inbound_draft_visible_and_own_product_line_only(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Inbound Seller Co",
            "slug": f"inb-sel-{suffix}",
            "admin_email": f"inb-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_tok = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {admin_tok}"}

    wh = await async_client.post(
        "/warehouses", headers=ah, json={"name": "W", "code": f"w-{suffix}"}
    )
    wid = wh.json()["id"]
    loc = await async_client.post(
        f"/warehouses/{wid}/locations", headers=ah, json={"code": "A1"}
    )
    lid = loc.json()["id"]

    s1 = await async_client.post(
        "/sellers", headers=ah, json={"name": "Seller One"}
    )
    s2 = await async_client.post(
        "/sellers", headers=ah, json={"name": "Seller Two"}
    )
    sid1 = s1.json()["id"]
    sid2 = s2.json()["id"]

    p_own = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Mine",
            "sku_code": f"MINE-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid1,
        },
    )
    p_other = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Theirs",
            "sku_code": f"THEIRS-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid2,
        },
    )
    pid_own = p_own.json()["id"]
    pid_other = p_other.json()["id"]

    seller_email = f"inb-sl-{suffix}@example.com"
    acc = await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid1,
            "email": seller_email,
            "password": "password123",
        },
    )
    assert acc.status_code == 201

    login = await async_client.post(
        "/auth/login",
        json={"email": seller_email, "password": "password123"},
    )
    assert login.status_code == 200
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    wh_list = await async_client.get("/warehouses", headers=sh)
    assert wh_list.status_code == 200
    assert len(wh_list.json()) >= 1

    create = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=sh,
        json={
            "warehouse_id": wid,
            "operation_type": "return",
            "waybill_number": "  TN-001  ",
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["operation_type"] == "return"
    assert create.json()["waybill_number"] == "TN-001"
    assert create.json()["warehouse_name"] == "W"
    rid = create.json()["id"]

    listed = await async_client.get(
        "/operations/inbound-intake-requests", headers=sh
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["operation_type"] == "return"
    assert listed.json()[0]["waybill_number"] == "TN-001"
    assert listed.json()[0]["warehouse_name"] == "W"
    assert listed.json()[0]["goods_qty_total"] == 0

    detail = await async_client.get(
        f"/operations/inbound-intake-requests/{rid}", headers=sh
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["waybill_number"] == "TN-001"

    bad_line = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=sh,
        json={
            "product_id": pid_other,
            "expected_qty": 2,
            "storage_location_id": lid,
        },
    )
    assert bad_line.status_code == 422
    assert bad_line.json()["detail"] == "product_seller_mismatch"

    ok_line = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=sh,
        json={
            "product_id": pid_own,
            "expected_qty": 4,
            "storage_location_id": lid,
        },
    )
    assert ok_line.status_code == 201, ok_line.text
    line_id = ok_line.json()["id"]

    patch_meta = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"planned_box_count": 3, "waybill_number": "TN-002"},
    )
    assert patch_meta.status_code == 200, patch_meta.text
    assert patch_meta.json()["planned_box_count"] == 3
    assert patch_meta.json()["waybill_number"] == "TN-002"

    submit = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=sh,
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "submitted"
    assert submit.json()["waybill_number"] == "TN-002"

    patch_submitted_meta = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"waybill_number": "TN-003"},
    )
    assert patch_submitted_meta.status_code == 200, patch_submitted_meta.text
    assert patch_submitted_meta.json()["status"] == "submitted"
    assert patch_submitted_meta.json()["waybill_number"] == "TN-003"

    patch_submitted_line = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/expected",
        headers=sh,
        json={"expected_qty": 5},
    )
    assert patch_submitted_line.status_code == 200, patch_submitted_line.text
    assert patch_submitted_line.json()["expected_qty"] == 5

    started = await post_primary_accept(
        async_client,
        "/operations/inbound-intake-requests",
        rid,
        ah,
        create_boxes=False,
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "receiving"

    locked_meta = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}",
        headers=sh,
        json={"waybill_number": "TN-004"},
    )
    assert locked_meta.status_code == 409
    assert locked_meta.json()["detail"] == "not_draft"

    locked_line = await async_client.patch(
        f"/operations/inbound-intake-requests/{rid}/lines/{line_id}/expected",
        headers=sh,
        json={"expected_qty": 6},
    )
    assert locked_line.status_code == 409
    assert locked_line.json()["detail"] == "not_draft"
