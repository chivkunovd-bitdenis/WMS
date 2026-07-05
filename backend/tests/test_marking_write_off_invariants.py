"""CZ-TEST-01: write-off invariants for all live print paths."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_marking_catalog_product_print import _auth_headers, _count_available
from test_marking_inventory_personal_shared import _pool_with_codes, _product_in_session
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_PRINTED, MarkingCode


async def _count_printed(session: AsyncSession, *, tenant_id: uuid.UUID, pool_id: uuid.UUID) -> int:
    stmt = select(func.count(MarkingCode.id)).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.pool_id == pool_id,
        MarkingCode.status == STATUS_PRINTED,
    )
    return int((await session.execute(stmt)).scalar_one())


@pytest.mark.asyncio
async def test_packaging_line_print_write_off_invariant(async_client: AsyncClient) -> None:
    """Live path: POST /packaging-lines/{id}/print decrements available."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Pack WO", "email": f"pwo-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WPWO", "code": "w-pwo"})
    wh_id = wh.json()["id"]
    sku = f"PWO-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pack write-off",
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
    codes = [f"01{'0' * 10}1111{'21'}{'P' * 20}{i:04d}" for i in range(5)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": "PWO pool", "product_ids": [product_id]}]),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    pool_id = uuid.UUID(imp.json()["pools"][0]["pool_id"])
    from app.services.tokens import decode_access_token

    tenant_id = uuid.UUID(
        str(decode_access_token(h["Authorization"].removeprefix("Bearer "))["tenant_id"])
    )

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=3, location_code="pwo-1"
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
    line_id = task.json()["lines"][0]["id"]

    async with SessionLocal() as session:
        before_available = await _count_available(session, tenant_id=tenant_id, pool_id=pool_id)
    assert before_available == 5

    resp = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"allow_partial": False, "duplicate_copies": 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 3

    async with SessionLocal() as session:
        after_available = await _count_available(session, tenant_id=tenant_id, pool_id=pool_id)
        after_printed = await _count_printed(session, tenant_id=tenant_id, pool_id=pool_id)
    assert after_available == before_available - 3
    assert after_printed == 3


@pytest.mark.asyncio
async def test_catalog_product_print_write_off_invariant(async_client: AsyncClient) -> None:
    """Live path: POST /products/{id}/print decrements available."""
    headers, tenant_id, seller_id = await _auth_headers(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="INV-CAT",
            name="Invariant catalog",
        )
        product.requires_honest_sign = True
        pool = await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000020",
            title="Inv catalog pool",
            available=4,
            product_ids=[product.id],
        )
        await session.commit()
        product_id = product.id
        pool_id = pool.id

    async with SessionLocal() as session:
        before = await _count_available(session, tenant_id=tenant_id, pool_id=pool_id)

    resp = await async_client.post(
        f"/operations/marking-codes/products/{product_id}/print",
        headers=headers,
        json={"quantity": 2, "allow_partial": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 2

    async with SessionLocal() as session:
        after = await _count_available(session, tenant_id=tenant_id, pool_id=pool_id)
        printed = await _count_printed(session, tenant_id=tenant_id, pool_id=pool_id)
    assert after == before - 2
    assert printed == 2


@pytest.mark.asyncio
async def test_reprint_does_not_change_available_count(async_client: AsyncClient) -> None:
    """Reprint must not consume additional available codes."""
    h = await _register_admin(async_client)
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Reprint inv", "email": f"ri-{uuid.uuid4().hex[:8]}@example.com"},
    )
    seller_id = seller.json()["id"]
    wh = await async_client.post("/warehouses", headers=h, json={"name": "WRI", "code": "w-ri"})
    wh_id = wh.json()["id"]
    sku = f"RI-{uuid.uuid4().hex[:6]}"
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Reprint item",
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
    cis_list = [f"01{'0' * 10}2222{'21'}{'R' * 20}{i:04d}" for i in range(2)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": "RI pool", "product_ids": [product_id]}]),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(cis_list)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    pool_id = uuid.UUID(imp.json()["pools"][0]["pool_id"])
    from app.services.tokens import decode_access_token

    token = h["Authorization"].removeprefix("Bearer ")
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=1, location_code="ri-1"
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

    first = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert first.status_code == 200, first.text

    async with SessionLocal() as session:
        available_after_first = await _count_available(
            session, tenant_id=tenant_id, pool_id=pool_id
        )

    reprint = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": True},
    )
    assert reprint.status_code == 200, reprint.text
    assert reprint.json()["is_reprint"] is True

    async with SessionLocal() as session:
        available_after_reprint = await _count_available(
            session, tenant_id=tenant_id, pool_id=pool_id
        )
    assert available_after_reprint == available_after_first
