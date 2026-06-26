from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import (
    EVENT_IMPORTED,
    EVENT_PRINTED,
    EVENT_REPRINTED,
    MarkingCodeEvent,
)


@pytest.mark.asyncio
async def test_import_records_imported_events(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Evt Seller", "email": f"evt-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "События",
            "sku_code": f"EVT-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = pr.json()["id"]

    codes = [f"01{'0' * 10}9999{'21'}{'C' * 20}{i:04d}" for i in range(3)]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Evt pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 3
    doc_number = imp.json()["document_number"]

    async with SessionLocal() as session:
        imported_count = (
            await session.execute(
                select(func.count(MarkingCodeEvent.id)).where(
                    MarkingCodeEvent.event_type == EVENT_IMPORTED,
                    MarkingCodeEvent.document_number == doc_number,
                )
            )
        ).scalar_one()
        assert imported_count == 3


@pytest.mark.asyncio
async def test_print_records_printed_and_reprint_records_reprinted(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Print Evt", "email": f"pe-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-pe"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Печать-события",
            "sku_code": f"PE-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )

    codes = [f"01{'0' * 10}8888{'21'}{'D' * 20}{i:04d}" for i in range(2)]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Print pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=2, location_code="pe-a1"
    )

    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 2}],
        },
    )
    assert task.status_code == 201
    line_id = task.json()["lines"][0]["id"]
    doc_number = task.json().get("document_number")

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": False},
    )
    assert printed.status_code == 200

    async with SessionLocal() as session:
        printed_events = (
            await session.execute(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.packaging_task_line_id == uuid.UUID(line_id),
                    MarkingCodeEvent.event_type == EVENT_PRINTED,
                )
            )
        ).scalars().all()
        assert len(printed_events) == 2
        assert all(e.copies == 2 for e in printed_events)
        if doc_number:
            assert all(e.document_number == doc_number for e in printed_events)

    reprint = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": True},
    )
    assert reprint.status_code == 200

    async with SessionLocal() as session:
        reprinted_events = (
            await session.execute(
                select(MarkingCodeEvent).where(
                    MarkingCodeEvent.packaging_task_line_id == uuid.UUID(line_id),
                    MarkingCodeEvent.event_type == EVENT_REPRINTED,
                )
            )
        ).scalars().all()
        assert len(reprinted_events) == 2
        assert all(e.copies == 1 for e in reprinted_events)
