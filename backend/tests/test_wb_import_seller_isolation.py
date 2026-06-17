from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.tokens import decode_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


@pytest.mark.asyncio
async def test_wb_import_does_not_claim_orphan_product_by_sku(
    async_client: AsyncClient,
) -> None:
    """Tenant-wide SKU lookup must not attach another seller's row (incl. seller_id NULL)."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Import Iso",
            "slug": f"wb-imp-{suffix}",
            "admin_email": f"wb-imp-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(decode_access_token(token)["tenant_id"])
    ah = {"Authorization": f"Bearer {token}"}

    s1 = await async_client.post("/sellers", headers=ah, json={"name": "Shop One"})
    sid1 = uuid.UUID(s1.json()["id"])

    shared_sku = f"VENDOR-{suffix}"
    orphan = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Orphan row",
            "sku_code": shared_sku,
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": None,
        },
    )
    assert orphan.status_code == 200
    orphan_id = uuid.UUID(orphan.json()["id"])

    card = {
        "nmID": 900_000_001,
        "vendorCode": shared_sku,
        "title": "WB card for shop one",
        "sizes": [{"skus": [f"BAR-{suffix}-1"], "chrtID": 1}],
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, sid1, [card])
        assert stats["products_created"] == 0
        assert stats["products_skipped"] >= 1

        unchanged = await session.get(Product, orphan_id)
        assert unchanged is not None
        assert unchanged.seller_id is None
        assert unchanged.name == "Orphan row"

        own_res = await session.execute(
            select(Product).where(
                Product.tenant_id == tenant_id,
                Product.seller_id == sid1,
            )
        )
        assert list(own_res.scalars().all()) == []
