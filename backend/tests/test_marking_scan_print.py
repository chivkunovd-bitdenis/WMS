from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin


@pytest.mark.asyncio
async def test_scan_print_one_unit_per_scan(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Scan Print", "email": f"sp-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    wh = await async_client.post("/warehouses", headers=h, json={"name": "WSP", "code": "w-sp"})
    wh_id = wh.json()["id"]

    sku = f"SCAN-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Scan item",
            "sku_code": sku,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )

    codes = [f"01{'0' * 10}7777{'21'}{'F' * 20}{i:04d}" for i in range(3)]
    await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Scan pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=2, location_code="sp-a1"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 2}],
        },
    )
    task_id = task.json()["id"]

    first = await async_client.post(
        "/operations/marking-codes/scan-print",
        headers=h,
        json={"packaging_task_id": task_id, "product_barcode": sku},
    )
    assert first.status_code == 410, first.text
    assert first.json()["detail"]["code"] == "endpoint_removed"


@pytest.mark.asyncio
async def test_print_rejects_completed_task(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Closed task", "email": f"ct-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WCT", "code": "w-ct"})
    wh_id = wh.json()["id"]
    sku = f"CT-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Closed item",
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
    cis = f"01{'0' * 10}8888{'21'}{'C' * 20}0001"
    await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "CT pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=1, location_code="ct-1"
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
    line_id = task.json()["lines"][0]["id"]
    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert printed.status_code == 200, printed.text
    packed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line_id}/pack",
        headers=h,
        json={"quantity": 1},
    )
    assert packed.status_code == 200, packed.text
    done = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/complete",
        headers=h,
        json={"acknowledge_all_packed": True},
    )
    assert done.status_code == 200, done.text

    blocked = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "task_not_active"
