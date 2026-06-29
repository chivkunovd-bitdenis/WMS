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
from app.services.tokens import decode_access_token


@pytest.mark.asyncio
async def test_list_product_codes_includes_pool_import_without_product_id(
    async_client: AsyncClient,
) -> None:
    h = await _register_admin(async_client)
    tenant_id = uuid.UUID(str(decode_access_token(h["Authorization"].split()[1])["tenant_id"]))

    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Codes pool", "email": f"cp-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert seller.status_code == 201, seller.text
    seller_id = uuid.UUID(seller.json()["id"])

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Pool codes item",
            "sku_code": f"PC-{uuid.uuid4().hex[:6]}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
            "seller_id": str(seller_id),
            "requires_honest_sign": True,
        },
    )
    assert pr.status_code == 200, pr.text
    product_id = uuid.UUID(pr.json()["id"])

    code_count = 16
    codes = [f"01{'0' * 10}7777{'21'}{'F' * 20}{i:04d}" for i in range(code_count)]
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": str(seller_id),
            "pools_json": json.dumps(
                [{"title": "Personal pool", "product_ids": [str(product_id)]}],
            ),
        },
        files=[("files", ("codes.csv", ("cis\n" + "\n".join(codes)).encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text

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
