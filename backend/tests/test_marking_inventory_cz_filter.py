"""FIX-01: list_inventory returns only ЧЗ-relevant products."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.marking_code import (
    STATUS_AVAILABLE,
    MarkingCode,
    MarkingPool,
    MarkingPoolProduct,
)
from app.models.product import Product
from app.services import marking_code_service as mc_svc
from app.services.tokens import decode_access_token


async def _seed_tenant_seller(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
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
    return tenant_id, seller_id, headers


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


async def _second_seller(
    async_client: AsyncClient,
    headers: dict[str, str],
) -> uuid.UUID:
    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Other seller", "email": f"o-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    return uuid.UUID(seller_resp.json()["id"])


async def _cz_product_with_pool_codes(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    sku: str,
    name: str,
    gtin: str,
    pool_title: str,
    code_count: int,
    code_tag: str = "I",
) -> Product:
    product = await _product_in_session(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        sku=sku,
        name=name,
        requires_honest_sign=True,
    )
    pool = MarkingPool(
        tenant_id=tenant_id,
        seller_id=seller_id,
        gtin=gtin,
        title=pool_title,
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
    for i in range(code_count):
        session.add(
            MarkingCode(
                tenant_id=tenant_id,
                seller_id=seller_id,
                pool_id=pool.id,
                cis_code=f"01{gtin}21{code_tag * 20}{i:04d}",
                gtin=gtin,
                status=STATUS_AVAILABLE,
            )
        )
    return product


@pytest.mark.asyncio
async def test_inventory_excludes_regular_product_without_pools(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id, _headers = await _seed_tenant_seller(async_client)

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
    tenant_id, seller_id, _headers = await _seed_tenant_seller(async_client)

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
    tenant_id, seller_id, _headers = await _seed_tenant_seller(async_client)

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


@pytest.mark.asyncio
async def test_inventory_tenant_isolation_same_sku_pool_title(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CZISO-001: other tenant with same SKU/GTIN/pool title must not leak into inventory."""
    shared_sku = "CZ-ISO-SKU"
    shared_name = "ЧЗ товар isolation"
    shared_gtin = "04600000000088"
    shared_pool_title = "Личный пул"

    tenant_a, seller_a, _ = await _seed_tenant_seller(async_client)
    tenant_b, seller_b, _ = await _seed_tenant_seller(async_client)

    async with SessionLocal() as session:
        product_a = await _cz_product_with_pool_codes(
            session,
            tenant_id=tenant_a,
            seller_id=seller_a,
            sku=shared_sku,
            name=shared_name,
            gtin=shared_gtin,
            pool_title=shared_pool_title,
            code_count=3,
        )
        product_b = await _cz_product_with_pool_codes(
            session,
            tenant_id=tenant_b,
            seller_id=seller_b,
            sku=shared_sku,
            name=shared_name,
            gtin=shared_gtin,
            pool_title=shared_pool_title,
            code_count=7,
        )
        await session.commit()

    async with SessionLocal() as session:
        result_a = await mc_svc.list_inventory(session, tenant_a, seller_id=seller_a)
        result_b = await mc_svc.list_inventory(session, tenant_b, seller_id=seller_b)

    assert _product_ids(result_a) == {product_a.id}
    assert _product_ids(result_b) == {product_b.id}
    row_a = result_a.rows[0]
    row_b = result_b.rows[0]
    assert row_a.sku_code == shared_sku
    assert row_b.sku_code == shared_sku
    assert row_a.personal_available == 3
    assert row_b.personal_available == 7
    assert row_a.shared_baskets == []
    assert row_b.shared_baskets == []


@pytest.mark.asyncio
async def test_inventory_seller_isolation_same_sku_pool_title(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CZISO-002: other seller with same title/GTIN/pool must not leak."""
    shared_name = "ЧЗ seller isolation"
    shared_gtin = "04600000000089"
    shared_pool_title = "Seller pool"
    # SKU is tenant-unique in this model, so seller isolation keeps the
    # human-readable metadata aligned and varies only the SKU code.

    tenant_id, seller_a, headers = await _seed_tenant_seller(async_client)
    seller_b = await _second_seller(async_client, headers)

    async with SessionLocal() as session:
        product_a = await _cz_product_with_pool_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_a,
            sku="CZ-ISO-SELLER-A",
            name=shared_name,
            gtin=shared_gtin,
            pool_title=shared_pool_title,
            code_count=4,
            code_tag="A",
        )
        product_b = await _cz_product_with_pool_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_b,
            sku="CZ-ISO-SELLER-B",
            name=shared_name,
            gtin=shared_gtin,
            pool_title=shared_pool_title,
            code_count=9,
            code_tag="B",
        )
        await session.commit()

    async with SessionLocal() as session:
        result_a = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_a)
        result_b = await mc_svc.list_inventory(session, tenant_id, seller_id=seller_b)

    assert _product_ids(result_a) == {product_a.id}
    assert _product_ids(result_b) == {product_b.id}
    assert result_a.rows[0].personal_available == 4
    assert result_b.rows[0].personal_available == 9
    assert product_b.id not in _product_ids(result_a)
    assert product_a.id not in _product_ids(result_b)
    assert result_a.rows[0].shared_baskets == []
    assert result_b.rows[0].shared_baskets == []
