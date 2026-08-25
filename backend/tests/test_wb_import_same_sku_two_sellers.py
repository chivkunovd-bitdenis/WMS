"""Один и тот же артикул у двух продавцов — это норма, а не конфликт.

Прод, 25.08.2026: у Loviana и ООО «Фэшн» одни и те же модели обуви. Пока артикул
с размером считался уникальным на весь тенант, импорт карточек WB для ООО «Фэшн»
молча пропускал товар — `J308-24/36` «уже есть», хотя есть он у Loviana. Так не
завелись 50 из 72 карточек, и переносить остатки было некуда.
"""

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
async def test_same_vendor_and_size_imports_for_both_sellers(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Two Sellers Co",
            "slug": f"two-sellers-{suffix}",
            "admin_email": f"two-sellers-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(decode_access_token(token)["tenant_id"])
    ah = {"Authorization": f"Bearer {token}"}

    sid_a = uuid.UUID(
        (await async_client.post("/sellers", headers=ah, json={"name": "Loviana"})).json()["id"]
    )
    sid_b = uuid.UUID(
        (await async_client.post("/sellers", headers=ah, json={"name": "OOO Fashion"})).json()["id"]
    )

    vendor = f"J308-24-{suffix}"

    def card(barcode: str) -> dict[str, object]:
        # Один артикул, один размер, но у каждого продавца свой штрихкод — как в WB.
        return {
            "nmID": 900_500_001,
            "vendorCode": vendor,
            "title": "Туфли",
            "sizes": [{"skus": [barcode], "chrtID": 1, "techSize": "36"}],
        }

    async with SessionLocal() as session:
        first = await upsert_products_from_wb_cards(
            session, tenant_id, sid_a, [card(f"1{suffix}")]
        )
        assert first["products_created"] == 1

        second = await upsert_products_from_wb_cards(
            session, tenant_id, sid_b, [card(f"2{suffix}")]
        )
        assert second["products_created"] == 1, "второй продавец не должен пропускаться"
        assert second["products_skipped"] == 0

        rows = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.wb_vendor_code == vendor,
                    )
                )
            ).scalars()
        )

    assert len(rows) == 2
    assert {r.seller_id for r in rows} == {sid_a, sid_b}
    # Артикул у обоих одинаковый — именно это и запрещало старое ограничение.
    assert len({r.sku_code for r in rows}) == 1
    assert {r.wb_barcode for r in rows} == {f"1{suffix}", f"2{suffix}"}


@pytest.mark.asyncio
async def test_same_seller_same_sku_still_deduplicated(
    async_client: AsyncClient,
) -> None:
    """Внутри одного продавца артикул по-прежнему один: повторный импорт не плодит строки."""
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "One Seller Co",
            "slug": f"one-seller-{suffix}",
            "admin_email": f"one-seller-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    tenant_id = uuid.UUID(decode_access_token(token)["tenant_id"])
    ah = {"Authorization": f"Bearer {token}"}
    sid = uuid.UUID(
        (await async_client.post("/sellers", headers=ah, json={"name": "Solo"})).json()["id"]
    )

    vendor = f"SOLO-{suffix}"
    card = {
        "nmID": 900_500_002,
        "vendorCode": vendor,
        "title": "Ботинки",
        "sizes": [{"skus": [f"3{suffix}"], "chrtID": 1, "techSize": "38"}],
    }

    async with SessionLocal() as session:
        await upsert_products_from_wb_cards(session, tenant_id, sid, [card])
        again = await upsert_products_from_wb_cards(session, tenant_id, sid, [card])
        assert again["products_created"] == 0

        rows = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.wb_vendor_code == vendor,
                    )
                )
            ).scalars()
        )

    assert len(rows) == 1
