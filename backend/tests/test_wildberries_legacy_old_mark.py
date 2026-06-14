"""Mark pre-split WB products as OLD/ when importing multi-size cards."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.tokens import decode_access_token
from app.services.wildberries_import_cards_service import upsert_imported_cards
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


@pytest.mark.asyncio
async def test_multi_size_sync_marks_legacy_product_old(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Old Mark Co",
            "slug": f"old-{suffix}",
            "admin_email": f"old-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    tenant_id = uuid.UUID(decode_access_token(reg.json()["access_token"])["tenant_id"])
    sid = (await async_client.post("/sellers", headers=ah, json={"name": "IP Old"})).json()["id"]
    seller_uuid = uuid.UUID(sid)

    legacy = await async_client.post(
        "/products",
        headers=ah,
        json={
            "name": "Лосины merged",
            "sku_code": f"LEG-MERGE-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    assert legacy.status_code == 200
    pid = uuid.UUID(legacy.json()["id"])

    card = {
        "nmID": 800200,
        "vendorCode": f"LEG-MERGE-{suffix}",
        "title": "Лосины",
        "sizes": [
            {"techSize": "S", "skus": ["7110000000001"]},
            {"techSize": "M", "skus": ["7110000000002"]},
        ],
    }

    async with SessionLocal() as session:
        await upsert_imported_cards(session, tenant_id, seller_uuid, [card])
        p = await session.get(Product, pid)
        assert p is not None
        p.wb_nm_id = 800200
        p.wb_vendor_code = f"LEG-MERGE-{suffix}"
        await session.commit()

        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_uuid, [card])
        assert stats["legacy_marked_old"] == 1
        assert stats["products_created"] == 2

        await session.refresh(p)
        assert p.sku_code.startswith("OLD/")
        assert p.name.startswith("[OLD] ")

    plist = await async_client.get("/products", headers=ah)
    rows = [r for r in plist.json() if r.get("seller_id") == sid]
    assert len(rows) == 3
    size_skus = {r["sku_code"] for r in rows if r["id"] != str(pid)}
    assert f"LEG-MERGE-{suffix}/S" in size_skus
    assert f"LEG-MERGE-{suffix}/M" in size_skus
