from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_PRINTED, MarkingCode


async def _seed_product_with_pool_codes(
    async_client: AsyncClient,
    *,
    code_count: int,
    sku_suffix: str,
) -> tuple[dict[str, str], str, str, str]:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": f"Print All {sku_suffix}", "email": f"pa-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": f"WPA {sku_suffix}", "code": f"w-pa-{sku_suffix}"},
    )
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    sku = f"PA-{sku_suffix}-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": f"Pool item {sku_suffix}",
            "sku_code": sku,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = pr.json()["id"]

    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )

    codes = [f"01{'0' * 10}7777{'21'}{'F' * 20}{i:04d}" for i in range(code_count)]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": f"Pool {sku_suffix}", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    return h, seller_id, product_id, wh_id


@pytest.mark.asyncio
async def test_print_all_aggregates_lines_in_order(async_client: AsyncClient) -> None:
    h, _seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=5, sku_suffix="agg"
    )
    loc_a = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=2, location_code="pa-a"
    )
    loc_b = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=3, location_code="pa-b"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {"product_id": product_id, "storage_location_id": loc_a, "quantity": 2},
                {"product_id": product_id, "storage_location_id": loc_b, "quantity": 3},
            ],
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    line_ids = [ln["id"] for ln in task.json()["lines"]]

    preview = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"dry_run": True},
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["dry_run"] is True
    assert preview_body["quantity"] == 5
    assert len(preview_body["lines"]) == 2
    assert all(ln["shortage"] == 0 for ln in preview_body["lines"])

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    body = printed.json()
    assert body["quantity"] == 5
    assert len(body["codes"]) == 5
    assert len(body["lines"]) == 2
    assert body["lines"][0]["quantity"] == 2
    assert body["lines"][1]["quantity"] == 3

    async with SessionLocal() as session:
        for line_id in line_ids:
            count = (
                await session.execute(
                    select(func.count(MarkingCode.id)).where(
                        MarkingCode.packaging_task_line_id == uuid.UUID(line_id),
                        MarkingCode.status == STATUS_PRINTED,
                    )
                )
            ).scalar_one()
            assert int(count) > 0

    task_after = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=h)
    assert sum(ln["qty_marking_printed"] for ln in task_after.json()["lines"]) == 5


@pytest.mark.asyncio
async def test_print_all_shortage_without_partial(async_client: AsyncClient) -> None:
    h, _seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=2, sku_suffix="short"
    )
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=5, location_code="pa-s"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 5}],
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]

    preview = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"dry_run": True, "allow_partial": False},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["quantity"] == 0
    assert preview.json()["lines"][0]["shortage"] == 3

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"allow_partial": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == 0
    assert printed.json()["codes"] == []

    partial = await async_client.post(
        f"/operations/marking-codes/packaging-tasks/{task_id}/print-all",
        headers=h,
        json={"allow_partial": True},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["quantity"] == 2
    assert partial.json()["lines"][0]["shortage"] == 3
