"""WB import: country of origin and shelf life come from card characteristics.

Both fields are optional on the WB card (seller may not fill them for every
category), so import must fill them when present and leave them empty
(never a made-up placeholder) when the card doesn't carry them. Import also
must not overwrite a value someone already entered by hand.
"""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.tokens import decode_access_token
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards


async def _register_tenant_and_seller(
    async_client: AsyncClient, suffix: str
) -> tuple[uuid.UUID, uuid.UUID]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Country Shelf Life Co",
            "slug": f"csl-{suffix}",
            "admin_email": f"csl-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    ah = {"Authorization": f"Bearer {token}"}
    seller = await async_client.post("/sellers", headers=ah, json={"name": "CSL Shop"})
    assert seller.status_code == 201
    seller_id = uuid.UUID(seller.json()["id"])
    return tenant_id, seller_id


@pytest.mark.asyncio
async def test_country_and_shelf_life_filled_when_card_has_them(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    card = {
        "nmID": 700_000_001,
        "vendorCode": f"CSL-{suffix}",
        "title": "Товар со страной и сроком годности",
        "sizes": [{"skus": [f"BAR-{suffix}-1"], "chrtID": 1}],
        "characteristics": [
            {"name": "Страна производства", "value": ["Россия"]},
            {"name": "Срок годности", "value": ["12 месяцев"]},
        ],
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_created"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        assert row["wb_country_of_origin"] == "Россия"
        assert row["wb_shelf_life"] == "12 месяцев"


@pytest.mark.asyncio
async def test_country_and_shelf_life_stay_empty_when_card_lacks_them(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    card = {
        "nmID": 700_000_002,
        "vendorCode": f"CSL-EMPTY-{suffix}",
        "title": "Товар без страны и срока годности",
        "sizes": [{"skus": [f"BAR-{suffix}-2"], "chrtID": 1}],
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_created"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        # No placeholder value: WB didn't send it, so we don't know it.
        assert row["wb_country_of_origin"] is None
        assert row["wb_shelf_life"] is None


@pytest.mark.asyncio
async def test_reimport_does_not_overwrite_manually_entered_value(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    tenant_id, seller_id = await _register_tenant_and_seller(async_client, suffix)

    barcode = f"BAR-{suffix}-3"
    async with SessionLocal() as session:
        session.add(
            Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name="Ручной товар",
                sku_code=f"CSL-MANUAL-{suffix}",
                wb_barcode=barcode,
                wb_country_of_origin="Беларусь",
                wb_shelf_life="24 месяца",
            )
        )
        await session.commit()

    card = {
        "nmID": 700_000_003,
        "vendorCode": f"CSL-MANUAL-{suffix}",
        "title": "Ручной товар",
        "sizes": [{"skus": [barcode], "chrtID": 1}],
        "characteristics": [
            {"name": "Страна производства", "value": ["Китай"]},
            {"name": "Срок годности", "value": ["6 месяцев"]},
        ],
    }

    async with SessionLocal() as session:
        stats = await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        assert stats["products_updated"] == 1

        res = await session.execute(
            Product.__table__.select().where(Product.tenant_id == tenant_id)
        )
        row = res.mappings().one()
        # Card says China/6 months, but the hand-entered values must survive.
        assert row["wb_country_of_origin"] == "Беларусь"
        assert row["wb_shelf_life"] == "24 месяца"
