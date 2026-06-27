from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.marking_code import (
    STATUS_AVAILABLE,
    MarkingCode,
    MarkingPool,
    MarkingPoolProduct,
)
from app.services.tokens import decode_access_token


async def _seed_tenant_seller_product(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
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

    product_resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Пул-товар",
            "sku_code": f"POOL-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(seller_id),
        },
    )
    assert product_resp.status_code == 200, product_resp.text
    product_id = uuid.UUID(product_resp.json()["id"])

    return tenant_id, seller_id, product_id


@pytest.mark.asyncio
async def test_create_pool_link_product_and_code(async_client: AsyncClient) -> None:
    tenant_id, seller_id, product_id = await _seed_tenant_seller_product(async_client)
    gtin = "04600000000001"
    cis = f"01{gtin}21{'A' * 20}0001"

    async with SessionLocal() as session:
        pool = MarkingPool(
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin=gtin,
            title="Тестовый пул",
        )
        session.add(pool)
        await session.flush()

        session.add(
            MarkingPoolProduct(
                tenant_id=tenant_id,
                pool_id=pool.id,
                product_id=product_id,
            )
        )
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
                product_id=product_id,
                cis_code=cis,
                gtin=gtin,
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        loaded_pool = await session.get(
            MarkingPool,
            pool.id,
            options=[selectinload(MarkingPool.pool_products)],
        )
        assert loaded_pool is not None
        assert loaded_pool.title == "Тестовый пул"
        assert len(loaded_pool.pool_products) == 1
        assert loaded_pool.pool_products[0].product_id == product_id

        codes = (
            await session.execute(
                select(MarkingCode).where(MarkingCode.pool_id == pool.id)
            )
        ).scalars().all()
        assert len(codes) == 1
        assert codes[0].cis_code == cis
        assert codes[0].status == STATUS_AVAILABLE


@pytest.mark.asyncio
async def test_migration_backfill_creates_pool_for_legacy_code(async_client: AsyncClient) -> None:
    tenant_id, seller_id, product_id = await _seed_tenant_seller_product(async_client)
    gtin = "04600000000002"
    cis = f"01{gtin}21{'B' * 20}0002"
    code_id = uuid.uuid4()

    async with SessionLocal() as session:
        session.add(
            MarkingCode(
                id=code_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=product_id,
                pool_id=None,
                cis_code=cis,
                gtin=gtin,
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic/versions/20260626_0043_marking_pools.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0043", migration_path)
    assert spec is not None and spec.loader is not None
    migration_0043 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_0043)
    async with SessionLocal() as session:
        await session.run_sync(migration_0043._backfill_marking_pools)
        await session.commit()

    async with SessionLocal() as session:
        code = await session.get(MarkingCode, code_id)
        assert code is not None
        assert code.pool_id is not None

        pool = await session.get(MarkingPool, code.pool_id)
        assert pool is not None
        assert pool.gtin == gtin
        assert pool.seller_id == seller_id

        links = (
            await session.execute(
                select(MarkingPoolProduct).where(MarkingPoolProduct.pool_id == pool.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].product_id == product_id


@pytest.mark.asyncio
async def test_list_inventory_does_not_auto_link_by_gtin(async_client: AsyncClient) -> None:
    tenant_id, seller_id, product_id = await _seed_tenant_seller_product(async_client)
    gtin = "04600000000099"
    cis = f"01{gtin}21{'C' * 20}0099"
    code_id = uuid.uuid4()

    async with SessionLocal() as session:
        session.add(
            MarkingCode(
                id=code_id,
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=None,
                pool_id=None,
                cis_code=cis,
                gtin=gtin,
                status=STATUS_AVAILABLE,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        from app.services import marking_code_service as mc_svc

        await mc_svc.list_inventory(session, tenant_id, seller_id=seller_id)
        code = await session.get(MarkingCode, code_id)
        assert code is not None
        assert code.product_id is None
