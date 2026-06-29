"""IN-BE-01: honest fact aggregation, collapsed statuses, complete_receiving."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBoxLine
from app.models.product import Product
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as svc
from app.services.catalog_service import create_product, create_warehouse
from app.services.tokens import decode_access_token


async def _tenant_id(async_client: AsyncClient) -> uuid.UUID:
    email = f"inbe01-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "INBE01 FF",
            "slug": f"inbe01-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


async def _setup_request(
    async_client: AsyncClient,
    tenant_id: uuid.UUID,
    *,
    expected_qty: int = 10,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        wh = await create_warehouse(
            session, tenant_id, name="W", code=f"w-{uuid.uuid4().hex[:6]}"
        )
        prod = await create_product(
            session,
            tenant_id,
            name="P",
            sku_code=f"SKU-{uuid.uuid4().hex[:6]}",
            length_mm=10,
            width_mm=10,
            height_mm=10,
        )
        req = await svc.create_request(session, tenant_id, warehouse_id=wh.id)
        request_id = req.id
        product_id = prod.id
    async with SessionLocal() as session:
        await svc.add_line(
            session,
            tenant_id,
            request_id,
            product_id=product_id,
            expected_qty=expected_qty,
        )
        await svc.submit_request(session, tenant_id, request_id)
    return request_id, product_id


@pytest.mark.asyncio
async def test_loose_only_receiving_no_boxes(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, _pid = await _setup_request(async_client, tenant_id, expected_qty=5)
    async with SessionLocal() as session:
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        assert req.status == svc.STATUS_SUBMITTED
        await svc.begin_receiving(session, tenant_id, request_id)
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        line = req.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=5
        )
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.status == svc.STATUS_SORTING
        assert done.has_discrepancy is False
        assert done.lines[0].actual_qty == 5


@pytest.mark.asyncio
async def test_mixed_box_then_loose_fact_is_sum(async_client: AsyncClient) -> None:
    """REV-IN-BE-01: box scan first, then loose — total = box + loose, no double count."""
    tenant_id = await _tenant_id(async_client)
    request_id, product_id = await _setup_request(async_client, tenant_id, expected_qty=10)
    async with SessionLocal() as session:
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        boxes = await box_svc.create_boxes_for_request(
            session, tenant_id, req_loaded, box_count=1
        )
        box = await box_svc.open_box_by_barcode(
            session,
            tenant_id,
            request_id,
            barcode=boxes[0].internal_barcode,
        )
        prod = await session.get(Product, product_id)
        assert prod is not None
        for _ in range(6):
            await box_svc.scan_product_into_box(
                session, tenant_id, request_id, box.id, barcode=prod.sku_code
            )
        await box_svc.close_box_intake(session, tenant_id, request_id, box.id)
        req_after = await svc.get_request(session, tenant_id, request_id)
        assert req_after is not None
        line = req_after.lines[0]
        assert line.actual_qty in (None, 0)
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=4
        )
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.lines[0].actual_qty == 10
        assert done.has_discrepancy is False


@pytest.mark.asyncio
async def test_mixed_loose_then_box_fact_is_sum(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, product_id = await _setup_request(async_client, tenant_id, expected_qty=10)
    async with SessionLocal() as session:
        await svc.begin_receiving(session, tenant_id, request_id)
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        line = req_loaded.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=4
        )
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        boxes = await box_svc.create_boxes_for_request(
            session, tenant_id, req_loaded, box_count=1
        )
        session.add(
            InboundIntakeBoxLine(box_id=boxes[0].id, product_id=product_id, quantity=6)
        )
        await session.flush()
        await svc.sync_request_actuals_from_boxes(session, req_loaded)
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.lines[0].actual_qty == 10
        assert done.has_discrepancy is False


@pytest.mark.asyncio
async def test_under_receive_sets_has_discrepancy_but_completes(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, _pid = await _setup_request(async_client, tenant_id, expected_qty=10)
    async with SessionLocal() as session:
        await svc.begin_receiving(session, tenant_id, request_id)
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        line = req.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=7
        )
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.has_discrepancy is True
        assert done.status == svc.STATUS_SORTING
        assert done.lines[0].actual_qty == 7


@pytest.mark.asyncio
async def test_over_receive_sets_has_discrepancy(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, _pid = await _setup_request(async_client, tenant_id, expected_qty=5)
    async with SessionLocal() as session:
        await svc.begin_receiving(session, tenant_id, request_id)
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        line = req.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=8
        )
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.has_discrepancy is True
        assert done.lines[0].actual_qty == 8


@pytest.mark.asyncio
async def test_status_transitions_collapsed_chain(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, _pid = await _setup_request(async_client, tenant_id, expected_qty=1)
    async with SessionLocal() as session:
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        assert req.status == svc.STATUS_SUBMITTED
        await svc.begin_receiving(session, tenant_id, request_id)
        mid = await svc.get_request(session, tenant_id, request_id)
        assert mid is not None
        assert mid.status == svc.STATUS_RECEIVING
        line = mid.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=1
        )
        still = await svc.get_request(session, tenant_id, request_id)
        assert still is not None
        assert still.status == svc.STATUS_RECEIVING
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.status == svc.STATUS_SORTING


@pytest.mark.asyncio
async def test_box_only_under_receive_sets_discrepancy(async_client: AsyncClient) -> None:
    """REV-IN-BE-01: box=6, loose=0, planned=10 → total=6, discrepancy=true."""
    tenant_id = await _tenant_id(async_client)
    request_id, product_id = await _setup_request(async_client, tenant_id, expected_qty=10)
    async with SessionLocal() as session:
        await svc.begin_receiving(session, tenant_id, request_id)
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        boxes = await box_svc.create_boxes_for_request(
            session, tenant_id, req_loaded, box_count=1
        )
        session.add(
            InboundIntakeBoxLine(box_id=boxes[0].id, product_id=product_id, quantity=6)
        )
        await session.flush()
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.lines[0].actual_qty == 6
        assert done.has_discrepancy is True


@pytest.mark.asyncio
async def test_primary_accept_does_not_create_boxes(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, _pid = await _setup_request(async_client, tenant_id)
    async with SessionLocal() as session:
        accepted = await svc.primary_accept_request(
            session, tenant_id, request_id, actual_box_count=3
        )
        assert accepted.status == svc.STATUS_RECEIVING
        assert accepted.boxes == []
        assert accepted.actual_box_count == 3
