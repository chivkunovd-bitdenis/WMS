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


async def _begin_receiving_via_api(
    async_client: AsyncClient,
    base: str,
    request_id: str,
    headers: dict[str, str],
) -> None:
    """Move submitted request to receiving without legacy primary-accept."""
    path = f"{base}/{request_id}"
    got = await async_client.get(path, headers=headers)
    assert got.status_code == 200, got.text
    body = got.json()
    if body["status"] != "submitted":
        return
    lines = body["lines"]
    assert lines, "expected at least one line to begin receiving"
    line_id = lines[0]["id"]
    patch = await async_client.patch(
        f"{path}/lines/{line_id}/actual",
        headers=headers,
        json={"actual_qty": 0},
    )
    assert patch.status_code == 200, patch.text


async def _create_closed_boxes_for_request(
    headers: dict[str, str],
    request_id: str,
    *,
    box_count: int,
) -> None:
    """Pre-create closed boxes (legacy primary-accept shape for existing tests)."""
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
    await _begin_receiving_via_api(async_client, base, request_id, headers)
    if create_boxes and actual_box_count > 0:
        await _create_closed_boxes_for_request(
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
        created = await async_client.post(f"{base}/boxes", headers=headers)
        assert created.status_code == 201, created.text
        box = created.json()
        box_id = box["id"]
    else:
        box = boxes[0]
        box_id = box["id"]
        if box.get("intake_closed_at") is None and not box.get("is_open"):
            open_res = await async_client.post(
                f"{base}/boxes/open",
                headers=headers,
                json={"barcode": box["internal_barcode"]},
            )
            assert open_res.status_code == 200, open_res.text
    lines = body["lines"]
    assert lines, "expected inbound lines"
    product_id = lines[0]["product_id"]
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
