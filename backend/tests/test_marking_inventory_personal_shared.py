"""SVC-01: personal inventory vs shared baskets — no double-count on shared pools."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.marking_code import (
    STATUS_AVAILABLE,
    STATUS_PRINTED,
    MarkingCode,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.services import marking_code_service as mc_svc
from app.services.tokens import decode_access_token


async def _seed_tenant_seller(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID]:
    email = f"inv-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Inv FF",
            "slug": f"inv-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Inv Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])
    return tenant_id, seller_id


async def _product_in_session(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    sku: str,
    name: str,
) -> Product:
    product = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        sku_code=sku,
        name=name,
        length_mm=100,
        width_mm=100,
        height_mm=100,
    )
    session.add(product)
    await session.flush()
    return product


async def _pool_with_codes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    gtin: str,
    title: str,
    available: int = 0,
    printed: int = 0,
    product_ids: list[uuid.UUID],
) -> MarkingPool:
    pool = MarkingPool(
        tenant_id=tenant_id,
        seller_id=seller_id,
        gtin=gtin,
        title=title,
    )
    session.add(pool)
    await session.flush()
    for product_id in product_ids:
        session.add(
            MarkingPoolProduct(
                tenant_id=tenant_id,
                pool_id=pool.id,
                product_id=product_id,
            )
        )
    seq = 0
    for _ in range(available):
        seq += 1
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
                cis_code=f"01{gtin}21{'A' * 20}{seq:04d}",
                gtin=gtin,
                status=STATUS_AVAILABLE,
            )
        )
    for _ in range(printed):
        seq += 1
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
                cis_code=f"01{gtin}21{'B' * 20}{seq:04d}",
                gtin=gtin,
                status=STATUS_PRINTED,
            )
        )
    return pool


def _row_by_product(
    result: mc_svc.MarkingInventoryResult, product_id: uuid.UUID
) -> mc_svc.ProductMarkingInventoryRow:
    for row in result.rows:
        if row.product_id == product_id:
            return row
    raise AssertionError(f"product {product_id} not in inventory rows")


@pytest.mark.asyncio
async def test_inventory_personal_and_shared_no_double_count(
    async_client: AsyncClient,
) -> None:
    """Pool A (1 product X, 100 avail), Pool B (X,Y,Z, 1000 avail) — no inflation."""
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        x = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="SKU-X", name="Product X"
        )
        y = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="SKU-Y", name="Product Y"
        )
        z = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="SKU-Z", name="Product Z"
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000001",
            title="Personal A",
            available=100,
            product_ids=[x.id],
        )
        pool_b = await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000002",
            title="Shared B",
            available=1000,
            product_ids=[x.id, y.id, z.id],
        )
        await session.commit()

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    row_x = _row_by_product(result, x.id)
    assert row_x.personal_available == 100
    assert row_x.available_count == 100
    assert len(row_x.shared_baskets) == 1
    basket = row_x.shared_baskets[0]
    assert basket.pool_id == pool_b.id
    assert basket.available == 1000
    assert basket.products_count == 3
    assert basket.gtin == "04600000000002"
    assert basket.title == "Shared B"

    row_y = _row_by_product(result, y.id)
    assert row_y.personal_available == 0
    assert len(row_y.shared_baskets) == 1
    assert row_y.shared_baskets[0].pool_id == pool_b.id
    assert row_y.shared_baskets[0].available == 1000

    row_z = _row_by_product(result, z.id)
    assert row_z.personal_available == 0
    assert len(row_z.shared_baskets) == 1

    total_personal = sum(r.personal_available for r in result.rows)
    assert total_personal == 100


@pytest.mark.asyncio
async def test_inventory_only_shared_pool(async_client: AsyncClient) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="ONLY-SHARED",
            name="Only shared",
        )
        other_product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="OTHER-SHARED",
            name="Other in pool",
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000003",
            title="Shared only",
            available=50,
            printed=5,
            product_ids=[product.id, other_product.id],
        )
        await session.commit()

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    row = _row_by_product(result, product.id)
    assert row.personal_available == 0
    assert row.personal_printed == 0
    assert len(row.shared_baskets) == 1
    assert row.shared_baskets[0].available == 50
    assert row.shared_baskets[0].printed == 5
    assert row.shared_baskets[0].products_count == 2


@pytest.mark.asyncio
async def test_inventory_two_personal_pools_sum(async_client: AsyncClient) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="TWO-PERSONAL",
            name="Two personal pools",
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000004",
            title="Personal 1",
            available=30,
            printed=2,
            product_ids=[product.id],
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000005",
            title="Personal 2",
            available=70,
            printed=3,
            product_ids=[product.id],
        )
        await session.commit()

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    row = _row_by_product(result, product.id)
    assert row.personal_available == 100
    assert row.personal_printed == 5
    assert row.available_count == 100
    assert row.printed_count == 5
    assert row.shared_baskets == []


@pytest.mark.asyncio
async def test_inventory_empty_seller(async_client: AsyncClient) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    assert result.rows == []
    assert result.unlinked_available_count == 0

    async with SessionLocal() as session:
        other_seller = uuid.uuid4()
        products_before = (
            await session.execute(select(Product).where(Product.seller_id == other_seller))
        ).scalars().all()
        assert products_before == []
        result_other = await mc_svc.list_inventory(session, tenant_id, seller_id=other_seller)

    assert result_other.rows == []
