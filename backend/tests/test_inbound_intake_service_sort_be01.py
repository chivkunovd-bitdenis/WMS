"""SORT-BE-01: product-centric mixed box/loose distribution."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBoxLine
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as svc
from app.services.catalog_service import create_location, create_product, create_warehouse
from app.services.tokens import decode_access_token


async def _tenant_id(async_client: AsyncClient) -> uuid.UUID:
    email = f"sortbe01-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "SORTBE01 FF",
            "slug": f"sortbe01-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


async def _mixed_sorting_request(
    async_client: AsyncClient,
    tenant_id: uuid.UUID,
    *,
    loose_qty: int = 4,
    box_qty: int = 6,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Request in sorting: loose_qty rosyp + box_qty in one box = accepted total."""
    async with SessionLocal() as session:
        wh = await create_warehouse(
            session, tenant_id, name="W", code=f"w-{uuid.uuid4().hex[:6]}"
        )
        loc_a = await create_location(
            session, tenant_id, wh.id, code=f"A-{uuid.uuid4().hex[:4]}"
        )
        loc_b = await create_location(
            session, tenant_id, wh.id, code=f"B-{uuid.uuid4().hex[:4]}"
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
        loc_a_id = loc_a.id
        loc_b_id = loc_b.id

    async with SessionLocal() as session:
        await svc.add_line(
            session,
            tenant_id,
            request_id,
            product_id=product_id,
            expected_qty=loose_qty + box_qty,
        )
        await svc.submit_request(session, tenant_id, request_id)
        await svc.begin_receiving(session, tenant_id, request_id)
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        line = req_loaded.lines[0]
        await svc.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=loose_qty
        )
        req_loaded = await svc.get_request(session, tenant_id, request_id)
        assert req_loaded is not None
        boxes = await box_svc.create_boxes_for_request(
            session, tenant_id, req_loaded, box_count=1
        )
        box_id = boxes[0].id
        session.add(
            InboundIntakeBoxLine(box_id=box_id, product_id=product_id, quantity=box_qty)
        )
        await session.flush()
        await svc.sync_request_actuals_from_boxes(session, req_loaded)
        done = await svc.complete_receiving(session, tenant_id, request_id)
        assert done.status == svc.STATUS_SORTING
        assert done.lines[0].actual_qty == loose_qty + box_qty

    return request_id, product_id, box_id, loc_a_id, loc_b_id


@pytest.mark.asyncio
async def test_mixed_distribution_lines_across_cells(async_client: AsyncClient) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, product_id, box_id, loc_a, loc_b = await _mixed_sorting_request(
        async_client, tenant_id, loose_qty=4, box_qty=6
    )

    async with SessionLocal() as session:
        rows = await svc.replace_distribution_lines(
            session,
            tenant_id,
            request_id,
            lines=[
                (None, product_id, loc_a, 2),
                (None, product_id, loc_b, 2),
                (box_id, product_id, loc_a, 3),
                (box_id, product_id, loc_b, 3),
            ],
        )
        assert len(rows) == 4
        assert sum(r.quantity for r in rows) == 10
        loose_rows = [r for r in rows if r.box_id is None]
        box_rows = [r for r in rows if r.box_id is not None]
        assert sum(r.quantity for r in loose_rows) == 4
        assert sum(r.quantity for r in box_rows) == 6


@pytest.mark.asyncio
async def test_mixed_distribution_rejects_over_accepted(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, product_id, box_id, loc_a, _loc_b = await _mixed_sorting_request(
        async_client, tenant_id
    )

    async with SessionLocal() as session:
        with pytest.raises(svc.InboundIntakeError) as exc:
            await svc.replace_distribution_lines(
                session,
                tenant_id,
                request_id,
                lines=[
                    (None, product_id, loc_a, 4),
                    (box_id, product_id, loc_a, 7),
                ],
            )
        assert exc.value.code in ("qty_exceeds_accepted", "qty_exceeds_box_remaining")


@pytest.mark.asyncio
async def test_mixed_distribution_rejects_loose_over_pool(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, product_id, _box_id, loc_a, loc_b = await _mixed_sorting_request(
        async_client, tenant_id, loose_qty=4, box_qty=6
    )

    async with SessionLocal() as session:
        with pytest.raises(svc.InboundIntakeError) as exc:
            await svc.replace_distribution_lines(
                session,
                tenant_id,
                request_id,
                lines=[
                    (None, product_id, loc_a, 3),
                    (None, product_id, loc_b, 2),
                ],
            )
        assert exc.value.code == "qty_exceeds_accepted"


@pytest.mark.asyncio
async def test_complete_distribution_mixed_box_and_loose(
    async_client: AsyncClient,
) -> None:
    tenant_id = await _tenant_id(async_client)
    request_id, product_id, box_id, loc_a, loc_b = await _mixed_sorting_request(
        async_client, tenant_id, loose_qty=4, box_qty=6
    )

    async with SessionLocal() as session:
        await svc.replace_distribution_lines(
            session,
            tenant_id,
            request_id,
            lines=[
                (None, product_id, loc_a, 4),
                (box_id, product_id, loc_b, 6),
            ],
        )
        done = await svc.complete_distribution(session, tenant_id, request_id)
        assert done.lines[0].posted_qty == 10
        assert done.status == svc.STATUS_DONE
        req = await svc.get_request(session, tenant_id, request_id)
        assert req is not None
        box = next(b for b in req.boxes if b.id == box_id)
        bl = next(bl for bl in box.lines if bl.product_id == product_id)
        assert bl.posted_qty == 6
