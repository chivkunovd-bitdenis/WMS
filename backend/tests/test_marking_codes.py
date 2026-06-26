from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.product import Product


async def _set_product_wb_barcode(product_id: str, barcode: str) -> None:
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        product.wb_barcode = barcode
        await session.commit()


@pytest.mark.asyncio
async def test_marking_import_and_packaging_print(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "ЧЗ Seller", "email": f"cz-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = seller.json()["id"]

    wh = await async_client.post("/warehouses", headers=h, json={"name": "W", "code": "w-cz"})
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Брюки",
            "sku_code": f"SKU-CZ-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = pr.json()["id"]

    patch = await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True, "packaging_instructions": "ЧЗ x2"},
    )
    assert patch.status_code == 200, patch.text

    codes = [f"01{'0' * 10}1234{'21'}{'A' * 20}{i:04d}" for i in range(5)]
    csv_body = "cis,sku_code\n" + "\n".join(f"{c},{pr.json()['sku_code']}" for c in codes)
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Брюки пул", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    assert imp.json()["accepted_count"] == 5

    inv = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=h,
    )
    assert inv.status_code == 200
    row = next(r for r in inv.json()["rows"] if r["product_id"] == product_id)
    assert row["available_count"] == 5

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=3, location_code="cz-a1"
    )

    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 3}],
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    line_id = task.json()["lines"][0]["id"]
    assert task.json()["lines"][0]["requires_honest_sign"] is True
    assert task.json()["lines"][0]["marking_available_count"] == 5

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": False},
    )
    assert printed.status_code == 200, printed.text
    assert printed.json()["quantity"] == 3
    assert len(printed.json()["codes"]) == 3

    inv2 = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=h,
    )
    row2 = next(r for r in inv2.json()["rows"] if r["product_id"] == product_id)
    assert row2["available_count"] == 2
    assert row2["printed_count"] == 3

    dup = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": False},
    )
    assert dup.status_code == 422
    assert dup.json()["detail"] == "already_printed_use_reprint"

    reprint = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": True},
    )
    assert reprint.status_code == 200
    assert reprint.json()["is_reprint"] is True
    assert len(reprint.json()["codes"]) == 3

    task_after = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=h)
    assert task_after.status_code == 200
    assert task_after.json()["lines"][0]["qty_marking_printed"] == 3


@pytest.mark.asyncio
async def test_marking_insufficient_codes(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "ЧЗ Seller2", "email": f"cz2-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "W2", "code": "w-cz2"})
    wh_id = wh.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Пальто",
            "sku_code": f"SKU-CZ2-{uuid.uuid4().hex[:6]}",
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
    csv_body = f"cis,sku_code\n01{'0' * 10}999921{'B' * 20}0001,{pr.json()['sku_code']}"
    await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Пальто пул", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("one.csv", csv_body.encode(), "text/csv"))],
    )
    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=3, location_code="cz-b1"
    )
    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 3}],
        },
    )
    line_id = task.json()["lines"][0]["id"]
    fail = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": False, "allow_partial": False},
    )
    assert fail.status_code == 200, fail.text
    body = fail.json()
    assert body["quantity"] == 0
    assert body["shortage"] == 2
    assert body["codes"] == []

    partial = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 2, "reprint": False, "allow_partial": True},
    )
    assert partial.status_code == 200, partial.text
    partial_body = partial.json()
    assert partial_body["quantity"] == 1
    assert partial_body["shortage"] == 2
    assert len(partial_body["codes"]) == 1


@pytest.mark.asyncio
async def test_marking_pdf_import_links_by_gtin_ean13(async_client: AsyncClient) -> None:
    """PDF/CSV without sku: GTIN in CIS is 14 digits, wb_barcode may be EAN-13."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "ЧЗ GTIN", "email": f"cz-gtin-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    ean13 = "4600000000011"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Футболка ЧЗ",
            "sku_code": f"SKU-GTIN-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    assert pr.status_code == 200
    product_id = pr.json()["id"]

    await _set_product_wb_barcode(product_id, ean13)

    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True},
    )

    gtin14 = f"0{ean13}"
    cis = f"01{gtin14}21{'C' * 20}0001"
    csv_body = f"cis\n{cis}"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "GTIN pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", csv_body.encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    body = imp.json()
    assert body["accepted_count"] == 1
    assert len(body["pools"]) == 1

    inv = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=h,
    )
    assert inv.status_code == 200
    inv_body = inv.json()
    row = next(r for r in inv_body["rows"] if r["product_id"] == product_id)
    assert row["available_count"] == 1
    assert inv_body["unlinked_available_count"] == 0


@pytest.mark.asyncio
async def test_marking_import_with_pool_product_link(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "ЧЗ Explicit", "email": f"cz-ex-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Шарф",
            "sku_code": f"SKU-EX-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": seller_id,
        },
    )
    product_id = pr.json()["id"]
    cis = f"01{'9' * 14}21{'D' * 20}0001"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Шарф пул", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("one.csv", f"cis\n{cis}".encode(), "text/csv"))],
    )
    assert imp.status_code == 200
    assert imp.json()["accepted_count"] == 1

    inv = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=h,
    )
    row = next(r for r in inv.json()["rows"] if r["product_id"] == product_id)
    assert row["available_count"] == 1


@pytest.mark.asyncio
async def test_marking_import_requires_pools_json(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "ЧЗ NoProd", "email": f"cz-np-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={"seller_id": seller_id},
        files=[("files", ("one.csv", b"cis\n01", "text/csv"))],
    )
    assert imp.status_code == 422
