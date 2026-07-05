"""CZ-BE-01: catalog product print write-off (including shared baskets)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_marking_inventory_personal_shared import (
    _pool_with_codes,
    _product_in_session,
)

from app.db.session import SessionLocal
from app.models.marking_code import STATUS_AVAILABLE, STATUS_PRINTED, MarkingCode, MarkingCodeEvent
from app.services.tokens import decode_access_token


async def _auth_headers(async_client: AsyncClient) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    email = f"cat-print-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Cat Print FF",
            "slug": f"cat-print-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Cat seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])
    return headers, tenant_id, seller_id


async def _count_available(
    session: AsyncSession, *, tenant_id: uuid.UUID, pool_id: uuid.UUID
) -> int:
    stmt = select(func.count(MarkingCode.id)).where(
        MarkingCode.tenant_id == tenant_id,
        MarkingCode.pool_id == pool_id,
        MarkingCode.status == STATUS_AVAILABLE,
    )
    return int((await session.execute(stmt)).scalar_one())


@pytest.mark.asyncio
async def test_catalog_print_write_off_personal_pool(async_client: AsyncClient) -> None:
    headers, tenant_id, seller_id = await _auth_headers(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="CAT-PERS",
            name="Catalog personal",
        )
        product.requires_honest_sign = True
        pool = await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000010",
            title="Personal pool",
            available=5,
            product_ids=[product.id],
        )
        await session.commit()
        product_id = product.id
        pool_id = pool.id

    resp = await async_client.post(
        f"/operations/marking-codes/products/{product_id}/print",
        headers=headers,
        json={"quantity": 3, "allow_partial": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quantity"] == 3
    assert len(body["codes"]) == 3
    assert body["shortage"] is None

    async with SessionLocal() as session:
        assert await _count_available(session, tenant_id=tenant_id, pool_id=pool_id) == 2
        printed = (
            await session.execute(
                select(func.count(MarkingCode.id)).where(
                    MarkingCode.pool_id == pool_id,
                    MarkingCode.status == STATUS_PRINTED,
                )
            )
        ).scalar_one()
        assert int(printed) == 3


@pytest.mark.asyncio
async def test_catalog_print_shared_basket_product_b_gets_next(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id = await _auth_headers(async_client)

    async with SessionLocal() as session:
        product_a = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="SH-A",
            name="Shared A",
        )
        product_b = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="SH-B",
            name="Shared B",
        )
        product_a.requires_honest_sign = True
        product_b.requires_honest_sign = True
        pool = await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000011",
            title="Shared pool",
            available=4,
            product_ids=[product_a.id, product_b.id],
        )
        await session.commit()
        pool_id = pool.id
        product_a_id = product_a.id
        product_b_id = product_b.id

    first = await async_client.post(
        f"/operations/marking-codes/products/{product_a_id}/print",
        headers=headers,
        json={"quantity": 2},
    )
    assert first.status_code == 200, first.text
    first_codes = set(first.json()["codes"])

    second = await async_client.post(
        f"/operations/marking-codes/products/{product_b_id}/print",
        headers=headers,
        json={"quantity": 2},
    )
    assert second.status_code == 200, second.text
    second_codes = set(second.json()["codes"])
    assert first_codes.isdisjoint(second_codes)

    async with SessionLocal() as session:
        assert await _count_available(session, tenant_id=tenant_id, pool_id=pool_id) == 0


@pytest.mark.asyncio
async def test_catalog_print_shortage_without_allow_partial_rolls_back(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id = await _auth_headers(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="SHORT",
            name="Short pool",
        )
        product.requires_honest_sign = True
        pool = await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000012",
            title="Tiny",
            available=1,
            product_ids=[product.id],
        )
        await session.commit()
        product_id = product.id
        pool_id = pool.id

    resp = await async_client.post(
        f"/operations/marking-codes/products/{product_id}/print",
        headers=headers,
        json={"quantity": 3, "allow_partial": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["quantity"] == 0
    assert body["shortage"] == 2

    async with SessionLocal() as session:
        assert await _count_available(session, tenant_id=tenant_id, pool_id=pool_id) == 1


@pytest.mark.asyncio
async def test_catalog_print_records_printed_event(async_client: AsyncClient) -> None:
    headers, tenant_id, seller_id = await _auth_headers(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="EVT",
            name="Event product",
        )
        product.requires_honest_sign = True
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000013",
            title="Evt pool",
            available=2,
            product_ids=[product.id],
        )
        await session.commit()
        product_id = product.id

    resp = await async_client.post(
        f"/operations/marking-codes/products/{product_id}/print",
        headers=headers,
        json={"quantity": 1},
    )
    assert resp.status_code == 200, resp.text
    code_id = uuid.UUID(resp.json()["printed_codes"][0]["id"])

    async with SessionLocal() as session:
        events = (
            await session.execute(
                select(MarkingCodeEvent).where(MarkingCodeEvent.code_id == code_id)
            )
        ).scalars().all()
        assert any(e.event_type == "printed" for e in events)
