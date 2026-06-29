"""FIX-02: list_product_codes resolves codes via product pools (import product_id=NULL)."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_packaging_tasks import _register_admin

from app.db.session import SessionLocal
from app.models.marking_code import MarkingCode
from app.services import marking_code_service as mc_svc
from app.services.marking_code_service import MarkingCodeServiceError
from app.services.tokens import decode_access_token

SHARED_SKU = "PC-ISO-SKU"
SHARED_POOL_TITLE = "Personal pool"


async def _register_tenant_admin(
    async_client: AsyncClient,
    *,
    org_prefix: str,
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
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    tenant_id = uuid.UUID(str(decode_access_token(reg.json()["access_token"])["tenant_id"]))
    return headers, tenant_id


async def _create_seller(
    async_client: AsyncClient,
    headers: dict[str, str],
) -> uuid.UUID:
    seller = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": "Codes pool", "email": f"cp-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    return uuid.UUID(seller.json()["id"])


async def _create_cz_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: uuid.UUID,
    sku: str = SHARED_SKU,
) -> uuid.UUID:
    pr = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Pool codes item",
            "sku_code": sku,
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(seller_id),
            "requires_honest_sign": True,
        },
    )
    assert pr.status_code == 200, pr.text
    return uuid.UUID(pr.json()["id"])


async def _import_pool_codes(
    async_client: AsyncClient,
    headers: dict[str, str],
    *,
    seller_id: uuid.UUID,
    product_id: uuid.UUID,
    code_count: int,
    pool_title: str = SHARED_POOL_TITLE,
    code_prefix: str = "F",
) -> list[str]:
    codes = [
        f"01{'0' * 10}7777{'21'}{code_prefix * 20}{i:04d}" for i in range(code_count)
    ]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=headers,
        data={
            "seller_id": str(seller_id),
            "pools_json": json.dumps(
                [{"title": pool_title, "product_ids": [str(product_id)]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text
    return codes


@pytest.mark.asyncio
async def test_list_product_codes_includes_pool_import_without_product_id(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    tenant_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["tenant_id"]))

    seller_id = await _create_seller(async_client, h)
    product_id = await _create_cz_product(
        async_client,
        h,
        seller_id=seller_id,
        sku=f"PC-{uuid.uuid4().hex[:6]}",
    )

    code_count = 16
    await _import_pool_codes(
        async_client,
        h,
        seller_id=seller_id,
        product_id=product_id,
        code_count=code_count,
    )

    async with SessionLocal() as session:
        db_codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(
                        MarkingCode.tenant_id == tenant_id,
                        MarkingCode.seller_id == seller_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(db_codes) == code_count
        assert all(c.product_id is None for c in db_codes)
        assert all(c.pool_id is not None for c in db_codes)
        pool_ids = await mc_svc._pool_ids_for_product(session, tenant_id, product_id)
        assert pool_ids
        available = await mc_svc.count_available_for_product(session, tenant_id, product_id)
        assert available == code_count
        rows = await mc_svc.list_product_codes(session, tenant_id, product_id)
        assert len(rows) == code_count, (
            f"module={mc_svc.__file__} count={available} list={len(rows)}"
        )

    api = await async_client.get(
        f"/operations/marking-codes/products/{product_id}/codes",
        headers=h,
    )
    assert api.status_code == 200, api.text
    assert len(api.json()) == code_count


@pytest.mark.asyncio
async def test_list_product_codes_tenant_isolation_same_sku_pool(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CZISO-003: foreign tenant must not read codes for same SKU/pool title."""
    headers_a, tenant_a = await _register_tenant_admin(async_client, org_prefix="cz-iso-a")
    headers_b, tenant_b = await _register_tenant_admin(async_client, org_prefix="cz-iso-b")

    seller_a = await _create_seller(async_client, headers_a)
    seller_b = await _create_seller(async_client, headers_b)
    product_a = await _create_cz_product(async_client, headers_a, seller_id=seller_a)
    product_b = await _create_cz_product(async_client, headers_b, seller_id=seller_b)

    codes_a = await _import_pool_codes(
        async_client,
        headers_a,
        seller_id=seller_a,
        product_id=product_a,
        code_count=4,
        code_prefix="A",
    )
    codes_b = await _import_pool_codes(
        async_client,
        headers_b,
        seller_id=seller_b,
        product_id=product_b,
        code_count=8,
        code_prefix="B",
    )

    async with SessionLocal() as session:
        rows_a = await mc_svc.list_product_codes(session, tenant_a, product_a)
        rows_b = await mc_svc.list_product_codes(session, tenant_b, product_b)
        with pytest.raises(MarkingCodeServiceError, match="product_not_found"):
            await mc_svc.list_product_codes(session, tenant_b, product_a)

    assert len(rows_a) == 4
    assert len(rows_b) == 8
    assert {row.cis_code for row in rows_a} == set(codes_a)
    assert {row.cis_code for row in rows_b} == set(codes_b)
    assert set(codes_a).isdisjoint(codes_b)

    foreign_api = await async_client.get(
        f"/operations/marking-codes/products/{product_a}/codes",
        headers=headers_b,
    )
    assert foreign_api.status_code == 404
    assert foreign_api.json()["detail"] == "product_not_found"


@pytest.mark.asyncio
async def test_list_product_codes_seller_isolation_same_sku_pool(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-CZISO-004: other seller with same title/pool metadata must not share code lookup."""
    headers, tenant_id = await _register_tenant_admin(async_client, org_prefix="cz-iso-seller")

    seller_a = await _create_seller(async_client, headers)
    seller_b = await _create_seller(async_client, headers)
    # SKU remains distinct because this tenant enforces SKU uniqueness, but the
    # lookup contract should still ignore same product/pool metadata across sellers.
    product_a = await _create_cz_product(
        async_client,
        headers,
        seller_id=seller_a,
        sku=f"{SHARED_SKU}-A",
    )
    product_b = await _create_cz_product(
        async_client,
        headers,
        seller_id=seller_b,
        sku=f"{SHARED_SKU}-B",
    )

    codes_a = await _import_pool_codes(
        async_client,
        headers,
        seller_id=seller_a,
        product_id=product_a,
        code_count=3,
        code_prefix="S",
    )
    codes_b = await _import_pool_codes(
        async_client,
        headers,
        seller_id=seller_b,
        product_id=product_b,
        code_count=6,
        code_prefix="T",
    )

    async with SessionLocal() as session:
        rows_a = await mc_svc.list_product_codes(session, tenant_id, product_a)
        rows_b = await mc_svc.list_product_codes(session, tenant_id, product_b)
        available_a = await mc_svc.count_available_for_product(session, tenant_id, product_a)
        available_b = await mc_svc.count_available_for_product(session, tenant_id, product_b)
        db_codes = list(
            (
                await session.execute(
                    select(MarkingCode).where(
                        MarkingCode.tenant_id == tenant_id,
                        MarkingCode.seller_id == seller_a,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows_a) == 3
    assert len(rows_b) == 6
    assert available_a == 3
    assert available_b == 6
    assert {row.cis_code for row in rows_a} == set(codes_a)
    assert {row.cis_code for row in rows_b} == set(codes_b)
    assert all(code.cis_code in codes_a for code in db_codes)
    assert not any(code.cis_code in codes_b for code in db_codes)
