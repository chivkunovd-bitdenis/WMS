from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_marking_ledger_import_aggregate import _import_codes_to_pool
from test_marking_reprint_defect import _seed_printed_code
from test_packaging_tasks import _inventory_at_location

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode, MarkingPoolProduct
from app.services import marking_code_service as mc_svc


async def _bind_available_to_other_product(
    client: AsyncClient, headers: dict[str, str], product_id: uuid.UUID
) -> uuid.UUID:
    async with SessionLocal() as session:
        code = await session.scalar(select(MarkingCode).where(MarkingCode.status == "available"))
        assert code and code.pool_id
        seller_id = code.seller_id
        pool_id, tenant_id, code_id = code.pool_id, code.tenant_id, code.id
    product = await client.post(
        "/products",
        headers=headers,
        json={
            "name": "Other product",
            "sku_code": "OTHER-091",
            "seller_id": str(seller_id),
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
        },
    )
    assert product.status_code == 200, product.text
    other_id = uuid.UUID(product.json()["id"])
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code
        code.product_id = other_id
        session.add(MarkingPoolProduct(tenant_id=tenant_id, pool_id=pool_id, product_id=other_id))
        await session.commit()
        assert await mc_svc.count_available_for_product(session, tenant_id, product_id) == 0
        assert await mc_svc.count_available_for_products_batch(
            session, tenant_id, {product_id}
        ) == {
            product_id: 0,
        }
    return code_id


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["catalog", "packaging"])
async def test_print_does_not_reassign_code_bound_to_other_product(
    async_client: AsyncClient,
    surface: str,
) -> None:
    h, _, product_id, wh_id = await _import_codes_to_pool(async_client, code_count=1)
    code_id = await _bind_available_to_other_product(async_client, h, uuid.UUID(product_id))
    if surface == "catalog":
        url = f"/operations/marking-codes/products/{product_id}/print"
        body = {"quantity": 1}
    else:
        loc = await _inventory_at_location(
            async_client,
            h,
            warehouse_id=wh_id,
            product_id=product_id,
            qty=1,
            location_code="binding-091",
        )
        task = await async_client.post(
            "/operations/packaging-tasks",
            headers=h,
            json={
                "warehouse_id": wh_id,
                "lines": [{"product_id": product_id, "storage_location_id": loc, "quantity": 1}],
            },
        )
        assert task.status_code == 201, task.text
        line_id = task.json()["lines"][0]["id"]
        url = f"/operations/marking-codes/packaging-lines/{line_id}/print"
        body = {}
    result = await async_client.post(url, headers=h, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["quantity"] == 0
    assert result.json()["shortage"] == 1
    ledger = await async_client.get(
        "/operations/marking-codes/ledger", headers=h, params={"product_id": product_id}
    )
    assert ledger.json()["total"] == 0
    codes = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes", headers=h
    )
    assert codes.status_code == 200, codes.text
    assert codes.json() == []
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code and code.product_id != uuid.UUID(product_id) and code.status == "available"


@pytest.mark.asyncio
async def test_replacement_does_not_reassign_other_product_code(async_client: AsyncClient) -> None:
    h, line_id, code_id = await _seed_printed_code(async_client)
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, uuid.UUID(code_id))
        assert code and code.product_id
        product_id = code.product_id
    other_code_id = await _bind_available_to_other_product(async_client, h, product_id)
    defect = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=h,
        json={"packaging_task_line_id": line_id, "reason": "Broken label"},
    )
    assert defect.status_code == 200, defect.text
    request_id = defect.json()["request_id"]
    replacement = await async_client.post(
        f"/operations/marking-codes/reprint-requests/{request_id}/replace", headers=h
    )
    assert replacement.status_code == 422, replacement.text
    assert replacement.json()["detail"] == "no_replacement_code"
    async with SessionLocal() as session:
        code = await session.get(MarkingCode, other_code_id)
        assert code and code.product_id != product_id and code.status == "available"


@pytest.mark.asyncio
async def test_ledger_and_csv_are_not_available_to_seller(async_client: AsyncClient) -> None:
    h, seller_id, _, _ = await _import_codes_to_pool(async_client, code_count=1)
    email = f"seller-091-{uuid.uuid4().hex}@example.com"
    created = await async_client.post(
        "/auth/seller-accounts",
        headers=h,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert created.status_code == 201, created.text
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    seller_h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for suffix in ["", "/export"]:
        response = await async_client.get(
            "/operations/marking-codes/ledger" + suffix, headers=seller_h
        )
        assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_ledger_keeps_print_context_without_attributing_mixed_import_to_one_product(
    async_client: AsyncClient,
) -> None:
    headers, _, product_id, _ = await _import_codes_to_pool(async_client, code_count=2)
    printed = await async_client.post(
        f"/operations/marking-codes/products/{product_id}/print",
        headers=headers,
        json={"quantity": 1},
    )
    assert printed.status_code == 200, printed.text
    ledger = await async_client.get("/operations/marking-codes/ledger", headers=headers)
    assert ledger.status_code == 200, ledger.text
    rows = {row["event_type"]: row for row in ledger.json()["rows"]}
    assert rows["printed"]["product_name"] == "Ledger товар"
    assert rows["printed"]["product_sku"].startswith("LG-")
    assert rows["printed"]["source_process_label"] == "Каталог"
    assert rows["printed"]["document_number"] is None
    assert rows["printed"]["actor_email"]
    assert rows["imported"]["aggregated_count"] == 2
    assert rows["imported"]["product_name"] is None
    assert rows["imported"]["product_sku"] is None
