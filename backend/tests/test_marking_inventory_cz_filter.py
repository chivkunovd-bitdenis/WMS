"""FIX-01: list_inventory returns only ЧЗ-relevant products."""

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
    email = f"czf-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "CZ Filter FF",
            "slug": f"czf-{uuid.uuid4().hex[:8]}",
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
        json={"name": "CZ Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
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
    requires_honest_sign: bool = False,
) -> Product:
    product = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        sku_code=sku,
        name=name,
        length_mm=100,
        width_mm=100,
        height_mm=100,
        requires_honest_sign=requires_honest_sign,
    )
    session.add(product)
    await session.flush()
    return product


def _product_ids(result: mc_svc.MarkingInventoryResult) -> set[uuid.UUID]:
    return {row.product_id for row in result.rows}


@pytest.mark.asyncio
async def test_inventory_excludes_regular_product_without_pools(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        regular = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="REGULAR-NO-POOL",
            name="Regular no pool",
            requires_honest_sign=False,
        )
        await session.commit()
        regular_id = regular.id

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    assert regular_id not in _product_ids(result)
    assert result.rows == []


@pytest.mark.asyncio
async def test_inventory_includes_product_with_honest_sign_flag(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        cz_product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="CZ-FLAG",
            name="ЧЗ product",
            requires_honest_sign=True,
        )
        for i in range(100):
            await _product_in_session(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                sku=f"REG-{i:03d}",
                name=f"Regular {i}",
                requires_honest_sign=False,
            )
        await session.commit()
        cz_id = cz_product.id

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    assert len(result.rows) == 1
    assert result.rows[0].product_id == cz_id
    assert result.rows[0].requires_honest_sign is True


@pytest.mark.asyncio
async def test_inventory_includes_product_with_linked_pool_no_flag(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            sku="POOL-LINK",
            name="Pool linked",
            requires_honest_sign=False,
        )
        pool = MarkingPool(
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000077",
            title="Empty linked pool",
        )
        session.add(pool)
        await session.flush()
        session.add(
            MarkingPoolProduct(
                tenant_id=tenant_id,
                pool_id=pool.id,
                product_id=product.id,
            )
        )
        await session.commit()
        product_id = product.id

    async with SessionLocal() as session:
        result = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)

    assert len(result.rows) == 1
    assert result.rows[0].product_id == product_id
    assert result.rows[0].requires_honest_sign is False
    assert result.rows[0].personal_available == 0
    assert result.rows[0].shared_baskets == []
