from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_PRINTED, MarkingCode


async def _seed_product_with_pool_codes(
    async_client: AsyncClient,
    *,
    code_count: int,
) -> tuple[dict[str, str], str, str, str]:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pool Print", "email": f"pp-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    wh = await async_client.post("/warehouses", headers=h, json={"name": "WPP", "code": "w-pp"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pool item",
            "sku_code": f"PP-{uuid.uuid4().hex[:6]}",
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

    codes = [f"01{'0' * 10}5555{'21'}{'E' * 20}{i:04d}" for i in range(code_count)]
    csv_body = "cis\n" + "\n".join(codes)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Pool print", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    return h, seller_id, product_id, wh_id


@pytest.mark.asyncio
async def test_print_from_pool_full_quantity(async_client: AsyncClient) -> None:
    h, seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=50
    )
    pack_qty = 50
    loc_id = await _inventory_at_location(
        async_client,
        h,
        warehouse_id=wh_id,
        product_id=product_id,
        qty=pack_qty,
        location_code="pp-a1",
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {
                    "product_id": product_id,
                    "storage_location_id": loc_id,
                    "quantity": pack_qty,
                }
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]
    task_id = task.json()["id"]

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={
            "layout_json": {"units": [{"block": "cz", "copies": 2}]},
            "allow_partial": False,
        },
    )
    assert printed.status_code == 200, printed.text
    body = printed.json()
    assert body["quantity"] == 50
    assert len(body["codes"]) == 50
    assert body["shortage"] is None
    assert body["layout"]["units"] == [{"block": "cz", "copies": 2}]

    async with SessionLocal() as session:
        printed_codes = (
            await session.execute(
                select(MarkingCode).where(
                    MarkingCode.packaging_task_line_id == uuid.UUID(line_id),
                    MarkingCode.status == STATUS_PRINTED,
                )
            )
        ).scalars().all()
        assert len(printed_codes) == 50
        assert all(c.product_id == uuid.UUID(product_id) for c in printed_codes)

    inv = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=h,
    )
    row = next(r for r in inv.json()["rows"] if r["product_id"] == product_id)
    assert row["available_count"] == 0
    assert row["printed_count"] == 50

    task_after = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=h)
    assert task_after.json()["document_number"] is not None
    assert task_after.json()["lines"][0]["qty_marking_printed"] == 50


@pytest.mark.asyncio
async def test_sequential_print_does_not_reuse_codes(async_client: AsyncClient) -> None:
    h, _seller_id, product_id, wh_id = await _seed_product_with_pool_codes(
        async_client, code_count=3
    )
    loc_a = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=2, location_code="pp2-a"
    )
    loc_b = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=2, location_code="pp2-b"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [
                {"product_id": product_id, "storage_location_id": loc_a, "quantity": 2},
                {"product_id": product_id, "storage_location_id": loc_b, "quantity": 2},
            ],
        },
    )
    assert task.status_code == 201, task.text
    line_a = task.json()["lines"][0]["id"]
    line_b = task.json()["lines"][1]["id"]

    async def _print_line(line_id: str) -> list[str]:
        res = await async_client.post(
            f"/operations/marking-codes/packaging-lines/{line_id}/print",
            headers=h,
            json={"allow_partial": True, "duplicate_copies": 1},
        )
        assert res.status_code == 200, res.text
        return res.json()["codes"]

    codes_a = await _print_line(line_a)
    codes_b = await _print_line(line_b)
    all_codes = codes_a + codes_b
    assert len(all_codes) == len(set(all_codes))
    assert len(all_codes) == 3
    assert len(codes_a) == 2
    assert len(codes_b) == 1
