"""WB import: product dimensions come from the card, never from a guess.

CAT-01: an old (now removed) WB sync default used to stamp length_mm/width_mm/
height_mm with a 10x10x10 placeholder whenever the real value was unknown. Import
must never write that stub, and a re-sync must correct any product still carrying
it. Product has no field marking "entered by hand" vs "imported from WB", so the
safe rule is: only that exact 10x10x10 triple is treated as "no real data" and
gets overwritten -- any other existing value (manual or previously synced) stays.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.catalog_service import DEFAULT_PRODUCT_DIM_MM
from app.services.tokens import decode_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


async def _register_tenant_and_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[uuid.UUID, uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Dimensions Co",
            "slug": f"dim-{suffix}",
            "admin_email": f"dim-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {token}"}
    seller = await async_client.post("/sellers", headers=ah, json={"name": "Dim Shop"})
    assert seller.status_code == 201
    seller_id = uuid.UUID(seller.json()["id"])
    return tenant_id, seller_id


@pytest.mark.asyncio
async def test_import_leaves_dimensions_empty_when_card_has_no_dimensions(
    async_client: AsyncClient,
) -> None:
    """Sync must not stamp a 10x10x10 (or any other) guess when WB sent nothing."""
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    card = {
        "nmID": 800_000_001,
        "vendorCode": f"DIM-{suffix}",
        "title": "Товар без габаритов в карточке",
        "sizes": [{"skus": [f"DIMBAR-{suffix}-1"], "chrtID": 1}],
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_created"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        assert row["length_mm"] is None
        assert row["width_mm"] is None
        assert row["height_mm"] is None


@pytest.mark.asyncio
async def test_reimport_pulls_real_dimensions_over_stub(
    async_client: AsyncClient,
) -> None:
    """A product still carrying the legacy 10x10x10 stub gets corrected on re-sync."""
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    barcode = f"DIMBAR-{suffix}-2"
    async with SessionLocal() as session:
        session.add(
            Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name="Товар с заглушкой",
                sku_code=f"DIM-STUB-{suffix}",
                wb_barcode=barcode,
                length_mm=DEFAULT_PRODUCT_DIM_MM,
                width_mm=DEFAULT_PRODUCT_DIM_MM,
                height_mm=DEFAULT_PRODUCT_DIM_MM,
            )
        )
        await session.commit()

    card = {
        "nmID": 800_000_002,
        "vendorCode": f"DIM-STUB-{suffix}",
        "title": "Товар с заглушкой",
        "sizes": [{"skus": [barcode], "chrtID": 1}],
        # WB sends centimeters; import converts to millimeters.
        "dimensions": {"length": 30, "width": 22, "height": 5},
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_updated"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        assert row["length_mm"] == 300
        assert row["width_mm"] == 220
        assert row["height_mm"] == 50


@pytest.mark.asyncio
async def test_reimport_does_not_overwrite_real_dimensions(
    async_client: AsyncClient,
) -> None:
    """Any dimension other than the exact 10x10x10 stub is left alone."""
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    barcode = f"DIMBAR-{suffix}-3"
    async with SessionLocal() as session:
        session.add(
            Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name="Товар с реальными габаритами",
                sku_code=f"DIM-REAL-{suffix}",
                wb_barcode=barcode,
                length_mm=123,
                width_mm=45,
                height_mm=67,
            )
        )
        await session.commit()

    card = {
        "nmID": 800_000_003,
        "vendorCode": f"DIM-REAL-{suffix}",
        "title": "Товар с реальными габаритами",
        "sizes": [{"skus": [barcode], "chrtID": 1}],
        "dimensions": {"length": 30, "width": 22, "height": 5},
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_updated"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        assert row["length_mm"] == 123
        assert row["width_mm"] == 45
        assert row["height_mm"] == 67
