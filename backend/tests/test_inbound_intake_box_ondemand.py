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
async def test_create_open_box_on_demand_scan_close_updates_actual(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-IN-BE-02: on-demand box → scan +1 → close → actual_qty from box."""
    suffix = str(int(time.time() * 1000))
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=5)

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        assert box.intake_opened_at is not None
        assert box.intake_closed_at is None
        assert box.box_number == 1
        assert box.internal_barcode.startswith("INB-")

        line = await box_svc.scan_product_into_box(
            session,
            tenant_id,
            rid,
            box.id,
            barcode=sku,
        )
        assert line.quantity == 1

        closed = await box_svc.close_box_intake(session, tenant_id, rid, box.id)
        assert closed.intake_closed_at is not None

        req = await intake_svc.get_request(session, tenant_id, rid)
        assert req is not None
        assert req.status == intake_svc.STATUS_VERIFYING
        req_line = next(ln for ln in req.lines if ln.product_id == pid)
        assert req_line.actual_qty == 1


@pytest.mark.asyncio
async def test_create_open_box_rejects_second_open_box(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 1)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _, _ = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    async with SessionLocal() as session:
        await box_svc.create_open_box(session, tenant_id, rid)
        try:
            await box_svc.create_open_box(session, tenant_id, rid)
            pytest.fail("expected open_box_exists")
        except box_svc.InboundIntakeBoxError as exc:
            assert exc.code == "open_box_exists"


@pytest.mark.asyncio
async def test_scan_without_open_box_rejected(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000) + 2)
    ah, tenant_id = await _register_admin(async_client, suffix)
    rid, _pid, sku = await _submitted_request(async_client, ah, suffix, expected_qty=3)

    async with SessionLocal() as session:
        box = await box_svc.create_open_box(session, tenant_id, rid)
        await box_svc.close_box_intake(session, tenant_id, rid, box.id)

        box2 = await box_svc.create_open_box(session, tenant_id, rid)
        try:
            await box_svc.scan_product_into_box(
                session,
                tenant_id,
                rid,
                box.id,
                barcode=sku,
            )
            pytest.fail("expected box_closed for closed box")
        except box_svc.InboundIntakeBoxError as exc:
            assert exc.code == "box_closed"

        line = await box_svc.scan_product_into_box(
            session,
            tenant_id,
            rid,
            box2.id,
            barcode=sku,
        )
        assert line.quantity == 1
