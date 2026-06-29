"""SVC-02: linked_products_count and is_shared on pool list/detail rows."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.marking_code import MarkingPool, MarkingPoolProduct
from app.models.product import Product
from app.services import marking_code_service as mc_svc
from app.services.tokens import decode_access_token


async def _seed_tenant_seller(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID]:
    email = f"pool-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pool FF",
            "slug": f"pool-{uuid.uuid4().hex[:8]}",
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
        json={"name": "Pool Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
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
) -> Product:
    product = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        sku_code=sku,
        name=f"Product {sku}",
        length_mm=100,
        width_mm=100,
        height_mm=100,
    )
    session.add(product)
    await session.flush()
    return product


async def _pool_with_linked_products(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> MarkingPool:
    pool = MarkingPool(
        tenant_id=tenant_id,
        seller_id=seller_id,
        gtin=f"0460000000{uuid.uuid4().hex[:4]}",
        title=f"Pool {len(product_ids)} products",
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
    return pool


@pytest.mark.parametrize(
    ("linked_count", "expected_shared"),
    [
        (0, False),
        (1, False),
        (2, True),
    ],
)
@pytest.mark.asyncio
async def test_pool_list_and_detail_linked_products_flags(
    async_client: AsyncClient,
    linked_count: int,
    expected_shared: bool,
) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        product_ids: list[uuid.UUID] = []
        for idx in range(linked_count):
            product = await _product_in_session(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                sku=f"SKU-{linked_count}-{idx}",
            )
            product_ids.append(product.id)
        pool = await _pool_with_linked_products(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_ids=product_ids,
        )
        pool_id = pool.id
        await session.commit()

    async with SessionLocal() as session:
        rows = await mc_svc.list_pools(session, tenant_id, seller_id=seller_id)
        detail = await mc_svc.get_pool_detail(session, tenant_id, pool_id)

    row = next(r for r in rows if r.id == pool_id)
    assert row.linked_products_count == linked_count
    assert row.is_shared is expected_shared
    assert detail.linked_products_count == linked_count
    assert detail.is_shared is expected_shared
