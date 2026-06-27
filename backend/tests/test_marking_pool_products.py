from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.marking_code import MarkingPool, MarkingPoolProduct
from app.services.tokens import decode_access_token


async def _seed_tenant_seller_products(
    async_client: AsyncClient,
    *,
    product_count: int = 2,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, list[uuid.UUID], uuid.UUID]:
    email = f"pool-link-{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Pool Link FF",
            "slug": f"pool-link-{uuid.uuid4().hex[:8]}",
            "admin_email": email,
            "password": "password123",
        },
    )
    assert reg.status_code in (200, 201), reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))

    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Pool Link Seller", "email": f"s-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller_resp.status_code == 201, seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])

    other_seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Other Seller", "email": f"o-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert other_seller_resp.status_code == 201, other_seller_resp.text
    other_seller_id = uuid.UUID(other_seller_resp.json()["id"])

    product_ids: list[uuid.UUID] = []
    for i in range(product_count):
        product_resp = await async_client.post(
            "/products",
            headers=headers,
            json={
                "name": f"Пул-товар {i + 1}",
                "sku_code": f"POOL-LINK-{uuid.uuid4().hex[:5]}-{i}",
                "length_mm": 100,
                "width_mm": 100,
                "height_mm": 100,
                "seller_id": str(seller_id),
            },
        )
        assert product_resp.status_code == 200, product_resp.text
        product_ids.append(uuid.UUID(product_resp.json()["id"]))

    foreign_product_resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Чужой товар",
            "sku_code": f"FOREIGN-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(other_seller_id),
        },
    )
    assert foreign_product_resp.status_code == 200, foreign_product_resp.text
    foreign_product_id = uuid.UUID(foreign_product_resp.json()["id"])

    async with SessionLocal() as session:
        pool = MarkingPool(
            tenant_id=tenant_id,
            seller_id=seller_id,
            gtin="04600000000099",
            title="Пул для привязки",
        )
        session.add(pool)
        await session.commit()
        await session.refresh(pool)
        pool_id = pool.id

    return headers, pool_id, foreign_product_id, product_ids, tenant_id


@pytest.mark.asyncio
async def test_set_pool_products_replaces_list(async_client: AsyncClient) -> None:
    headers, pool_id, _, product_ids, _ = await _seed_tenant_seller_products(async_client)

    first = await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/products",
        headers=headers,
        json={"product_ids": [str(product_ids[0])]},
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["products"]) == 1
    assert first.json()["products"][0]["id"] == str(product_ids[0])

    second = await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/products",
        headers=headers,
        json={"product_ids": [str(product_ids[1])]},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["products"]) == 1
    assert second.json()["products"][0]["id"] == str(product_ids[1])

    async with SessionLocal() as session:
        links = (
            await session.execute(
                select(MarkingPoolProduct).where(MarkingPoolProduct.pool_id == pool_id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].product_id == product_ids[1]


@pytest.mark.asyncio
async def test_set_pool_products_foreign_seller_product_rejected(
    async_client: AsyncClient,
) -> None:
    headers, pool_id, foreign_product_id, product_ids, _ = await _seed_tenant_seller_products(
        async_client
    )

    resp = await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/products",
        headers=headers,
        json={"product_ids": [str(foreign_product_id)]},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "product_seller_mismatch"

    ok = await async_client.put(
        f"/operations/marking-codes/pools/{pool_id}/products",
        headers=headers,
        json={"product_ids": [str(product_ids[0])]},
    )
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_add_and_remove_pool_products(async_client: AsyncClient) -> None:
    _headers, pool_id, _, product_ids, tenant_id = await _seed_tenant_seller_products(async_client)

    from app.services import marking_code_service as mc_svc

    async with SessionLocal() as session:
        added = await mc_svc.add_pool_products(
            session,
            tenant_id,
            pool_id,
            [product_ids[0], product_ids[1]],
        )
        assert len(added.products) == 2

        removed = await mc_svc.remove_pool_products(
            session,
            tenant_id,
            pool_id,
            [product_ids[0]],
        )
        assert len(removed.products) == 1
        assert removed.products[0].id == product_ids[1]
