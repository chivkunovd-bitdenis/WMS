from __future__ import annotations

from httpx import AsyncClient


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
    assert boxes, "expected inbound boxes after primary accept"
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
