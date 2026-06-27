from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin


@pytest.mark.asyncio
async def test_pending_marking_lists_unprinted_lines(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    suffix = uuid.uuid4().hex[:8]
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pending Seller", "email": f"s-{suffix}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "WH", "code": f"wh-{suffix}"},
    )
    wh_id = wh.json()["id"]
    product = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pending Product",
            "sku_code": f"PND-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = product.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )
    cis = f"01{'0' * 10}8888{'21'}{'W' * 20}0001"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=1,
        location_code=f"w-{suffix}",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 1}],
        },
    )
    line_id = task.json()["lines"][0]["id"]

    pending = await async_client.get(
        "/operations/marking-codes/pending-marking",
        headers=h,
    )
    assert pending.status_code == 200, pending.text
    body = pending.json()
    assert body["total"] == 1
    assert body["rows"][0]["packaging_task_line_id"] == line_id
    assert body["rows"][0]["qty_remaining"] == 1

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert printed.status_code == 200

    after = await async_client.get("/operations/marking-codes/pending-marking", headers=h)
    assert after.json()["total"] == 0
