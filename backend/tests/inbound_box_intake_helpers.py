from __future__ import annotations

import uuid

from httpx import AsyncClient, Response

from app.db.session import SessionLocal
from app.services import inbound_intake_box_service as box_svc
from app.services import inbound_intake_service as intake_svc
from app.services.tokens import decode_access_token


def _tenant_id_from_headers(headers: dict[str, str]) -> uuid.UUID:
    token = headers["Authorization"].removeprefix("Bearer ")
    return uuid.UUID(str(decode_access_token(token)["tenant_id"]))


async def _create_boxes_for_request(
    headers: dict[str, str],
    request_id: str,
    *,
    box_count: int,
) -> None:
    tenant_id = _tenant_id_from_headers(headers)
    async with SessionLocal() as session:
        req = await intake_svc.get_request(session, tenant_id, uuid.UUID(request_id))
        if req is None:
            raise AssertionError("request_not_found")
        await box_svc.create_boxes_for_request(
            session, tenant_id, req, box_count=box_count
        )
        await session.commit()


async def post_primary_accept(
    async_client: AsyncClient,
    base: str,
    request_id: str,
    headers: dict[str, str],
    *,
    actual_box_count: int = 1,
    create_boxes: bool = True,
) -> Response:
    """Begin receiving without legacy primary-accept API (IN-BE-03)."""
    tenant_id = _tenant_id_from_headers(headers)
    async with SessionLocal() as session:
        await intake_svc.begin_receiving(
            session, tenant_id, uuid.UUID(request_id)
        )
        await session.commit()
    if create_boxes and actual_box_count > 0:
        await _create_boxes_for_request(
            headers, request_id, box_count=actual_box_count
        )
    return await async_client.get(f"{base}/{request_id}", headers=headers)


async def fulfill_inbound_via_box_scans(
    async_client: AsyncClient,
    headers: dict[str, str],
    request_id: str,
    product_barcode: str,
    total_qty: int,
) -> None:
    """Fill piece intake for one product via manual box line quantity (no product barcode scan)."""
    del product_barcode  # kept for call-site compatibility
    base = f"/operations/inbound-intake-requests/{request_id}"
    got = await async_client.get(base, headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    boxes = body["boxes"]
    if not boxes:
        await _create_boxes_for_request(headers, request_id, box_count=1)
        got = await async_client.get(base, headers=headers)
        assert got.status_code == 200, got.text
        body = got.json()
        boxes = body["boxes"]
    assert boxes, "expected inbound boxes for box intake helper"
    lines = body["lines"]
    assert lines, "expected inbound lines"
    product_id = lines[0]["product_id"]
    box = boxes[0]
    box_id = box["id"]
    inb = box["internal_barcode"]
    open_res = await async_client.post(
        f"{base}/boxes/open",
        headers=headers,
        json={"barcode": inb},
    )
    assert open_res.status_code == 200, open_res.text
    put = await async_client.put(
        f"{base}/boxes/{box_id}/lines/{product_id}",
        headers=headers,
        json={"quantity": total_qty},
    )
    assert put.status_code == 200, put.text
    close = await async_client.post(f"{base}/boxes/{box_id}/close", headers=headers)
    assert close.status_code == 200, close.text


async def complete_inbound_to_storage(
    async_client: AsyncClient,
    headers: dict[str, str],
    request_id: str,
    *,
    product_id: str,
    storage_location_id: str,
    quantity: int,
) -> Response:
    """Разложить принятое из зоны сортировки в ячейку хранения (после verify)."""
    base = f"/operations/inbound-intake-requests/{request_id}"
    got = await async_client.get(base, headers=headers)
    assert got.status_code == 200, got.text
    boxes = got.json()["boxes"]
    assert boxes, "expected inbound boxes"
    box_id = boxes[0]["id"]
    putaway = await async_client.post(
        f"{base}/boxes/{box_id}/putaway",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "storage_location_id": storage_location_id,
            "lines": [{"product_id": product_id, "quantity": quantity}],
        },
    )
    assert putaway.status_code == 200, putaway.text
    return putaway
