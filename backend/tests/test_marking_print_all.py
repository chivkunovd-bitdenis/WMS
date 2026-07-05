"""print-all endpoint removed from UI — returns 410 Gone."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin


@pytest.mark.asyncio
async def test_print_all_returns_410(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Print all gone", "email": f"pag-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WPAG", "code": "w-pag"})
    wh_id = wh.json()["id"]
    sku = f"PAG-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Print all gone item",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )
    cis = f"01{'0' * 10}3333{'21'}{'A' * 20}0001"
    await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": "PAG pool", "product_ids": [product_id]}]),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=1, location_code="pag-1"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 1}],
        },
    )
    task_id = task.json()["id"]

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"allow_partial": False},
    )
    assert resp.status_code == 410, resp.text
    assert resp.json()["detail"]["code"] == "endpoint_removed"
