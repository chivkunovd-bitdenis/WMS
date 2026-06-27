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


@pytest.mark.asyncio
async def test_pending_marking_pagination_and_available(async_client: AsyncClient) -> None:
    """TC-NEW CZ-H8: limit/offset pagination and batched available counts."""
    h = await _register_admin(async_client)
    suffix = uuid.uuid4().hex[:8]
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pag Seller", "email": f"pag-{suffix}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "WH Pag", "code": f"wh-pag-{suffix}"},
    )
    wh_id = wh.json()["id"]

    product_ids: list[str] = []
    for idx in range(3):
        product = await async_client.post(
            "/products",
            headers=h,
            json={
                "name": f"Pag Product {idx}",
                "sku_code": f"PAG-{suffix}-{idx}",
                "length_mm": 10,
                "width_mm": 10,
                "height_mm": 10,
                "seller_id": seller_id,
            },
        )
        product_id = product.json()["id"]
        product_ids.append(product_id)
        await async_client.patch(
            f"/products/{product_id}/packaging-instructions",
            headers=h,
            json={"requires_honest_sign": True},
        )
        codes = [f"01{'0' * 10}999{idx}{'21'}{'V' * 20}{i:04d}" for i in range(2)]
        imp = await async_client.post(
            "/operations/marking-codes/import",
            headers=h,
            data={
                "seller_id": seller_id,
                "pools_json": json.dumps(
                    [{"title": f"Pool {idx}", "product_ids": [product_id]}],
                ),
            },
            files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
        )
        assert imp.status_code == 200, imp.text

    line_specs: list[tuple[str, str]] = []
    for idx, product_id in enumerate(product_ids):
        loc_id = await _inventory_at_location(
            async_client,
            h,
            warehouse_id=wh_id,
            product_id=product_id,
            qty=1,
            location_code=f"pag-{suffix}-{idx}",
        )
        line_specs.append((product_id, loc_id))

    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {"product_id": product_id, "storage_location_id": loc_id, "quantity": 1}
                for product_id, loc_id in line_specs
            ],
        },
    )
    assert task.status_code == 201, task.text

    page = await async_client.get(
        "/operations/marking-codes/pending-marking",
        headers=h,
        params={"limit": 2, "offset": 0},
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 2
    assert all(row["marking_available_count"] == 2 for row in body["rows"])

    tail = await async_client.get(
        "/operations/marking-codes/pending-marking",
        headers=h,
        params={"limit": 2, "offset": 2},
    )
    assert tail.status_code == 200, tail.text
    assert tail.json()["total"] == 3
    assert len(tail.json()["rows"]) == 1
