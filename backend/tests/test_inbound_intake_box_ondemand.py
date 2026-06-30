"""IN-BE-02: on-demand inbound intake boxes (service-level)."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as intake_svc
from app.services.tokens import decode_access_token


async def _register_admin(
    async_client: AsyncClient, suffix: str
) -> tuple[dict[str, str], uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"OnDemand FF {suffix}",
            "slug": f"ondemand-{suffix}",
            "admin_email": f"ondemand-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    ah = {"Authorization": f"Bearer {token}"}
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    return ah, tenant_id


async def _submitted_request(
    async_client: AsyncClient,
    ah: dict[str, str],
    suffix: str,
    *,
    expected_qty: int = 5,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    wh = await async_client.post(
        "/warehouses",
        headers=ah,
        json={"name": "W", "code": f"w-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "P",
            "sku_code": f"sku-{suffix}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert pr.status_code == 200, pr.text
    pid = uuid.UUID(pr.json()["id"])
    sku = pr.json()["sku_code"]

    cr = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=ah,
        json={"warehouse_id": wid},
    )
    assert cr.status_code == 201, cr.text
    rid = uuid.UUID(cr.json()["id"])

    ln = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/lines",
        headers=ah,
        json={"product_id": str(pid), "expected_qty": expected_qty},
    )
    assert ln.status_code == 201, ln.text

    sub = await async_client.post(
        f"/operations/inbound-intake-requests/{rid}/submit",
        headers=ah,
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == intake_svc.STATUS_SUBMITTED

    return rid, pid, sku


@pytest.mark.asyncio
async def test_create_three_boxes_on_demand_are_distinct(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    async with SessionLocal() as session:
        boxes = [await box_svc.create_open_box(session, tenant_id, rid) for _ in range(3)]
        assert [b.box_number for b in boxes] == [1, 2, 3]
        assert len({b.id for b in boxes}) == 3
        assert all(b.intake_opened_at is not None for b in boxes)
        assert all(b.intake_closed_at is None for b in boxes)

        reloaded = await box_svc.list_boxes(session, tenant_id, rid)
        assert [b.box_number for b in reloaded] == [1, 2, 3]


@pytest.mark.asyncio
async def test_box_two_scans_only_box_two(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 1)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=4)

    async with SessionLocal() as session:
        boxes = [await box_svc.create_open_box(session, tenant_id, rid) for _ in range(3)]
        box2 = boxes[1]
        for _ in range(2):
            line = await box_svc.scan_product_into_box(
                session,
                tenant_id,
                rid,
                box2.id,
                barcode=sku,
            )
        assert line.quantity == 2

        async with SessionLocal() as verify_session:
            loaded = await box_svc.list_boxes_with_lines(verify_session, tenant_id, rid)
        by_number = {b.box_number: b for b in loaded}
        assert by_number[1].lines == []
        assert by_number[3].lines == []
        assert len(by_number[2].lines) == 1
        assert by_number[2].lines[0].quantity == 2


@pytest.mark.asyncio
async def test_delete_empty_box_on_demand(async_client: AsyncClient) -> None:
    suffix = f"{int(time.time() * 1000)}-del"
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, _sku = await _submitted_request(async_client, ah, suffix, expected_qty=2)

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        box_id = box.id

    del_res = await async_client.delete(
        f"/operations/inbound-intake-requests/{rid}/boxes/{box_id}",
        headers=ah,
    )
    assert del_res.status_code == 204, del_res.text

    async with SessionLocal() as session:
        boxes = await box_svc.list_boxes(session, tenant_id, rid)
    assert boxes == []


@pytest.mark.asyncio
async def test_loose_scan_stays_loose_and_completion_does_not_require_close(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000) + 2)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=1)

    async with SessionLocal() as session:
        await box_svc.create_open_box(session, tenant_id, rid)
        await box_svc.create_open_box(session, tenant_id, rid)

        loose = await intake_svc.scan_barcode_to_loose_intake(
            session,
            tenant_id,
            rid,
            barcode=sku,
        )
        assert loose.actual_qty == 1

        req = await intake_svc.get_request(session, tenant_id, rid)
        assert req is not None
        line = next(ln for ln in req.lines if ln.product_id == pid)
        assert line.actual_qty == 1

        boxes = await box_svc.list_boxes_with_lines(session, tenant_id, rid)
        assert all(not b.lines for b in boxes)

        done = await intake_svc.complete_receiving(session, tenant_id, rid)
        assert done.status == intake_svc.STATUS_SORTING
        assert done.lines[0].actual_qty == 1
