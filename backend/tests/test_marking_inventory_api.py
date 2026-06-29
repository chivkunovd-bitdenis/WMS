"""API-01: inventory personal/shared fields + product marking-overview (httpx)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
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
from app.services.tokens import decode_access_token


async def _register_admin(
    async_client: AsyncClient,
    *,
    org_prefix: str = "api-inv",
) -> tuple[dict[str, str], uuid.UUID]:
    email = f"{org_prefix}-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"{org_prefix} FF",
            "slug": f"{org_prefix}-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    return headers, tenant_id


async def _create_seller(
    async_client: AsyncClient,
    headers: dict[str, str],
) -> uuid.UUID:
    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "API Inv Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    return uuid.UUID(seller_resp.json()["id"])


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


@pytest.mark.asyncio
async def test_inventory_api_personal_and_shared_shape(async_client: AsyncClient) -> None:
    """TC-NEW-API01-001: GET inventory exposes personal_available + shared_baskets."""
    headers, tenant_id = await _register_admin(async_client)
    seller_id = await _create_seller(async_client, headers)

    async with SessionLocal() as session:
        x = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="API-X", name="Product X"
        )
        y = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="API-Y", name="Product Y"
        )
        z = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="API-Z", name="Product Z"
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000011",
            title="Personal A",
            available=100,
            product_ids=[x.id],
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000012",
            title="Shared B",
            available=1000,
            product_ids=[x.id, y.id, z.id],
        )
        await session.commit()

    inv = await async_client.get(
        f"/operations/marking-codes/inventory?seller_id={seller_id}",
        headers=headers,
    )
    assert inv.status_code == 200, inv.text
    body = inv.json()
    row_x = next(r for r in body["rows"] if r["product_id"] == str(x.id))

    assert row_x["available_count"] == 100
    assert row_x["personal_available"] == 100
    assert len(row_x["shared_baskets"]) == 1
    basket = row_x["shared_baskets"][0]
    assert set(basket.keys()) == {"pool_id", "gtin", "title", "available", "products_count"}
    assert basket["available"] == 1000
    assert basket["products_count"] == 3
    assert basket["gtin"] == "04600000000012"
    assert basket["title"] == "Shared B"

    row_y = next(r for r in body["rows"] if r["product_id"] == str(y.id))
    assert row_y["personal_available"] == 0
    assert row_y["shared_baskets"][0]["available"] == 1000


@pytest.mark.asyncio
async def test_marking_overview_personal_and_shared(async_client: AsyncClient) -> None:
    """TC-NEW-API01-002: overview splits personal pools vs shared baskets for product X."""
    headers, tenant_id = await _register_admin(async_client)
    seller_id = await _create_seller(async_client, headers)

    async with SessionLocal() as session:
        x = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="OV-X", name="Overview X"
        )
        y = await _product_in_session(
            session, tenant_id=tenant_id, seller_id=seller_id, sku="OV-Y", name="Overview Y"
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000021",
            title="Personal pool",
            available=40,
            printed=3,
            product_ids=[x.id],
        )
        await _pool_with_codes(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000022",
            title="Shared pool",
            available=500,
            product_ids=[x.id, y.id],
        )
        await session.commit()

    overview = await async_client.get(
        f"/operations/marking-codes/products/{x.id}/marking-overview",
        headers=headers,
    )
    assert overview.status_code == 200, overview.text
    data = overview.json()

    assert data["product"]["id"] == str(x.id)
    assert data["product"]["sku_code"] == "OV-X"
    assert data["product"]["name"] == "Overview X"
    assert "requires_honest_sign" in data["product"]

    assert len(data["personal_pools"]) == 1
    personal = data["personal_pools"][0]
    assert personal["title"] == "Personal pool"
    assert personal["available"] == 40
    assert personal["printed"] == 3
    assert personal["loaded"] == 43
    assert set(personal.keys()) == {
        "pool_id",
        "gtin",
        "title",
        "available",
        "printed",
        "loaded",
    }

    assert len(data["shared_baskets"]) == 1
    shared = data["shared_baskets"][0]
    assert shared["title"] == "Shared pool"
    assert shared["available"] == 500
    assert shared["products_count"] == 2


@pytest.mark.asyncio
async def test_marking_overview_tenant_isolation_404(async_client: AsyncClient) -> None:
    """TC-NEW-API01-003: foreign tenant cannot read product marking-overview."""
    headers_a, tenant_a = await _register_admin(async_client, org_prefix="tenant-a")
    seller_a = await _create_seller(async_client, headers_a)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_a,
            seller_id=seller_a,
            sku="ISO-A",
            name="Tenant A product",
        )
        await session.commit()
        product_id = product.id

    headers_b, _ = await _register_admin(async_client, org_prefix="tenant-b")

    resp = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/marking-overview",
        headers=headers_b,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "product_not_found"


@pytest.mark.asyncio
async def test_marking_overview_seller_scope_403(async_client: AsyncClient) -> None:
    """TC-NEW-API01-004: seller cannot read another seller's product overview."""
    headers, tenant_id = await _register_admin(async_client, org_prefix="seller-scope")
    seller_a = await _create_seller(async_client, headers)
    seller_b = await _create_seller(async_client, headers)

    async with SessionLocal() as session:
        product = await _product_in_session(
            session,
            tenant_id=tenant_id,
            seller_id=seller_a,
            sku="SCOPE-A",
            name="Seller A only",
        )
        await session.commit()
        product_id = product.id

    seller_user_email = f"seller-{uuid.uuid4().hex[:8]}@example.com"
    create_seller_account = await async_client.post(
        "/auth/seller-accounts",
        headers=headers,
        json={
            "seller_id": str(seller_b),
            "email": seller_user_email,
            "password": "password123",
        },
    )
    assert create_seller_account.status_code == 201, create_seller_account.text

    login = await async_client.post(
        "/auth/login",
        json={"email": seller_user_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/marking-overview",
        headers=seller_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "forbidden"
