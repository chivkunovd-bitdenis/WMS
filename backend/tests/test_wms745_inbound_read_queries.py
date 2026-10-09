from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import event, select

from app.db.session import SessionLocal, engine
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.product import Product
from app.models.seller import Seller
from app.models.user import User
from app.models.warehouse import Warehouse

LEGACY_JSON = Path(__file__).parent / "fixtures" / "wms745" / "inbound_request_200_legacy.json"
FIXED_CREATED_AT = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)


def _fixed_id(section: int, index: int = 0) -> uuid.UUID:
    return uuid.UUID(int=7_450_000_000_000 + section * 1_000 + index)


async def _seed_request(
    *,
    tenant_id: uuid.UUID,
    line_count: int,
    box_count: int,
    section: int,
    document_number: str,
) -> uuid.UUID:
    request_id = _fixed_id(section)
    warehouse_id = _fixed_id(section + 1)
    seller_id = _fixed_id(section + 2)

    products = [
        Product(
            id=_fixed_id(section + 10, i),
            tenant_id=tenant_id,
            seller_id=seller_id,
            name=f"Товар {section}-{i + 1:03d}",
            sku_code=f"WMS745-{section}-{i + 1:03d}",
            length_mm=100,
            width_mm=100,
            height_mm=100,
            weight_g=10,
        )
        for i in range(line_count)
    ]
    boxes = [
        InboundIntakeBox(
            id=_fixed_id(section + 20, i),
            tenant_id=tenant_id,
            request_id=request_id,
            box_number=i + 1,
            internal_barcode=f"INB-WMS745-{section}-{i + 1:03d}",
            is_damaged=False,
        )
        for i in range(box_count)
    ]
    request = InboundIntakeRequest(
        id=request_id,
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        status="receiving",
        operation_type="inbound",
        marketplace="wildberries",
        created_at=FIXED_CREATED_AT,
        planned_box_count=box_count,
        document_number=document_number,
        display_number=f"{section:06d}",
        waybill_number=f"WAYBILL-{section}",
        has_discrepancy=False,
        boxes_discrepancy=False,
    )
    lines = [
        InboundIntakeLine(
            id=_fixed_id(section + 30, i),
            request_id=request_id,
            product_id=products[i].id,
            expected_qty=1,
            actual_qty=0,
            defective_qty=0,
            posted_qty=0,
            added_by_fulfillment=False,
        )
        for i in range(line_count)
    ]
    box_lines = [
        InboundIntakeBoxLine(
            id=_fixed_id(section + 40, i),
            box_id=boxes[i * box_count // line_count].id,
            product_id=products[i].id,
            quantity=1,
            posted_qty=0,
        )
        for i in range(line_count)
    ]

    async with SessionLocal() as session:
        session.add_all(
            [
                Warehouse(
                    id=warehouse_id,
                    tenant_id=tenant_id,
                    name="Склад WMS-745",
                    code=f"WMS745-{section}",
                    barcode=f"WH-WMS745-{section}",
                ),
                Seller(id=seller_id, tenant_id=tenant_id, name="Селлер WMS-745"),
                request,
                *products,
                *boxes,
                *lines,
                *box_lines,
            ]
        )
        await session.commit()
    return request_id


async def _get_and_count_queries(
    async_client: AsyncClient,
    *,
    url: str,
    headers: dict[str, str],
) -> tuple[Response, int]:
    query_count = 0

    def count_statement(*_args: object, **_kwargs: object) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        response = await async_client.get(url, headers=headers)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
    return response, query_count


@pytest.mark.asyncio
async def test_get_inbound_request_queries_are_bounded_and_json_matches_legacy_snapshot(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    email = f"wms745-{suffix}@example.com"
    registration = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-745 {suffix}",
            "slug": f"wms745-{suffix}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    async with SessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one()
        tenant_id = user.tenant_id

    large_id = await _seed_request(
        tenant_id=tenant_id,
        line_count=200,
        box_count=10,
        section=50,
        document_number="WMS745-200",
    )
    small_id = await _seed_request(
        tenant_id=tenant_id,
        line_count=20,
        box_count=2,
        section=60,
        document_number="WMS745-020",
    )

    large_response, large_query_count = await _get_and_count_queries(
        async_client,
        url=f"/operations/inbound-intake-requests/{large_id}",
        headers=headers,
    )
    small_response, small_query_count = await _get_and_count_queries(
        async_client,
        url=f"/operations/inbound-intake-requests/{small_id}",
        headers=headers,
    )

    assert large_response.status_code == 200, large_response.text
    assert small_response.status_code == 200, small_response.text
    assert LEGACY_JSON.is_file(), "legacy response snapshot must be captured before product changes"
    assert large_response.content == LEGACY_JSON.read_bytes()

    assert (
        large_query_count <= 30 and abs(large_query_count - small_query_count) <= 5
    ), (
        "GET query count must remain bounded as request lines grow: "
        f"20 lines={small_query_count}, 200 lines={large_query_count}; "
        "expected <=30 total queries and a difference <=5"
    )
