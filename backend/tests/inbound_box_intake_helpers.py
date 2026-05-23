from __future__ import annotations

from httpx import AsyncClient


async def fulfill_inbound_via_box_scans(
    async_client: AsyncClient,
    headers: dict[str, str],
    request_id: str,
    product_barcode: str,
    total_qty: int,
) -> None:
    base = f"/operations/inbound-intake-requests/{request_id}"
    got = await async_client.get(base, headers=headers)
    assert got.status_code == 200, got.text
    boxes = got.json()["boxes"]
    assert boxes, "expected inbound boxes after primary accept"
    box = boxes[0]
    box_id = box["id"]
    inb = box["internal_barcode"]
    open_res = await async_client.post(
        f"{base}/boxes/open",
        headers=headers,
        json={"barcode": inb},
    )
    assert open_res.status_code == 200, open_res.text
    for _ in range(total_qty):
        scan = await async_client.post(
            f"{base}/boxes/{box_id}/scan",
            headers=headers,
            json={"barcode": product_barcode},
        )
        assert scan.status_code == 200, scan.text
    close = await async_client.post(f"{base}/boxes/{box_id}/close", headers=headers)
    assert close.status_code == 200, close.text
