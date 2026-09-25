from __future__ import annotations

import time
import uuid
from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.services.seller_wb_catalog_service import (
    list_linked_wb_catalog_page_rows,
    list_seller_wb_catalog_rows,
)
from app.services.tokens import decode_access_token
from app.services.wildberries_import_cards_service import upsert_imported_cards
from app.services.wildberries_product_import_service import upsert_products_from_wb_cards
from app.services.wildberries_product_link_service import link_product_to_wb_card


async def _tenant_and_seller(async_client: AsyncClient) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = str(int(time.time() * 1000))
    registration = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WMS 535",
            "slug": f"wms-535-{suffix}",
            "admin_email": f"wms-535-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = registration.json()["access_token"]
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    seller = await async_client.post(
        "/sellers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "WB aliases"},
    )
    return tenant_id, uuid.UUID(seller.json()["id"])


@pytest.mark.asyncio
async def test_import_keeps_all_barcodes_on_one_chrt_product(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    chrt_id = 5_000_000_001
    initial_card = {
        "nmID": 7001,
        "vendorCode": "WMS535-A",
        "title": "Initial title",
        "sizes": [
            {
                "chrtID": chrt_id,
                "techSize": "M",
                "skus": [" 2000000000001 ", "2000000000002", "2000000000001", ""],
            }
        ],
    }
    async with SessionLocal() as session:
        first = await upsert_products_from_wb_cards(
            session, tenant_id, seller_id, [initial_card]
        )
        assert first["products_created"] == 1
        assert first["barcodes_added"] == 2

        changed_card = {
            **initial_card,
            "title": "Renamed title",
            "sizes": [
                {
                    "chrtID": chrt_id,
                    "techSize": "M renamed",
                    "skus": ["2000000000002", "2000000000003"],
                }
            ],
        }
        second = await upsert_products_from_wb_cards(
            session, tenant_id, seller_id, [changed_card]
        )
        assert second["products_created"] == 0
        assert second["products_updated"] == 1

        products = list(
            (
                await session.execute(
                    select(Product).where(
                        Product.tenant_id == tenant_id,
                        Product.seller_id == seller_id,
                        Product.wb_chrt_id == chrt_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(products) == 1
        product = products[0]
        assert product.wb_barcode == "2000000000001"
        assert product.name == "Initial title"
        assert product.sku_code == "WMS535-A/M"
        aliases = set(
            (
                await session.execute(
                    select(ProductBarcode.barcode).where(
                        ProductBarcode.product_id == product.id
                    )
                )
            ).scalars()
        )
        assert aliases == {
            "2000000000001",
            "2000000000002",
            "2000000000003",
        }

        rows = await list_seller_wb_catalog_rows(
            session, tenant_id, seller_id, search="2000000000003"
        )
        assert len(rows) == 1
        assert rows[0].product_id == product.id
        assert rows[0].wb_primary_barcode == "2000000000001"
        assert rows[0].wb_barcodes == (
            "2000000000001",
            "2000000000002",
            "2000000000003",
        )

        scope_fk = next(
            constraint
            for constraint in cast(
                Any, ProductBarcode.__table__
            ).foreign_key_constraints
            if constraint.name == "fk_product_barcodes_product_scope"
        )
        assert [column.name for column in scope_fk.columns] == [
            "tenant_id",
            "seller_id",
            "product_id",
        ]


@pytest.mark.asyncio
async def test_import_skips_missing_chrt_and_rolls_back_barcode_conflict(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    async with SessionLocal() as session:
        missing = await upsert_products_from_wb_cards(
            session,
            tenant_id,
            seller_id,
            [{"vendorCode": "NO-CHRT", "sizes": [{"skus": ["3001", "3002"]}]}],
        )
        assert missing["products_created"] == 0
        assert missing["sizes_missing_chrt_id"] == 1
        assert missing["missing_chrt_id_details"] == [
            {
                "nm_id": None,
                "vendor_code": "NO-CHRT",
                "size": None,
                "barcodes": ["3001", "3002"],
            }
        ]

        await upsert_products_from_wb_cards(
            session,
            tenant_id,
            seller_id,
            [
                {
                    "nmID": 8001,
                    "vendorCode": "OWNER-A",
                    "title": "Owner A",
                    "sizes": [{"chrtID": 101, "skus": ["CONFLICT-CODE"]}],
                },
                {
                    "nmID": 8002,
                    "vendorCode": "OWNER-B",
                    "title": "Owner B",
                    "sizes": [{"chrtID": 102, "skus": ["OWNER-B-CODE"]}],
                },
            ],
        )
        conflict = await upsert_products_from_wb_cards(
            session,
            tenant_id,
            seller_id,
            [
                {
                    "nmID": 8002,
                    "vendorCode": "OWNER-B",
                    "title": "Must not persist",
                    "sizes": [
                        {"chrtID": 102, "skus": ["CONFLICT-CODE", "NEW-PARTIAL-CODE"]}
                    ],
                }
            ],
        )
        assert conflict["products_skipped"] == 1
        assert conflict["barcode_conflicts"] == 1
        assert conflict["barcode_conflict_details"][0]["incoming_chrt_id"] == 102
        assert conflict["barcode_conflict_details"][0]["existing_chrt_id"] == 101
        owner_b = await session.scalar(
            select(Product).where(
                Product.tenant_id == tenant_id,
                Product.seller_id == seller_id,
                Product.wb_chrt_id == 102,
            )
        )
        assert owner_b is not None
        assert owner_b.name == "Owner B"
        partial = await session.scalar(
            select(ProductBarcode.id).where(
                ProductBarcode.tenant_id == tenant_id,
                ProductBarcode.seller_id == seller_id,
                ProductBarcode.barcode == "NEW-PARTIAL-CODE",
            )
        )
        assert partial is None


@pytest.mark.asyncio
async def test_import_preserves_existing_identity_and_fills_empty_primary_barcode(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Existing name",
            sku_code="V1/0",
            wb_chrt_id=901,
            wb_barcode=None,
        )
        session.add(product)
        await session.commit()
        product_id = product.id

        result = await upsert_products_from_wb_cards(
            session,
            tenant_id,
            seller_id,
            [
                {
                    "nmID": 9001,
                    "vendorCode": "V1",
                    "title": "Changed by WB",
                    "sizes": [
                        {
                            "chrtID": 901,
                            "techSize": "0",
                            "skus": ["901-CODE-1", "901-CODE-2"],
                        }
                    ],
                }
            ],
        )

        assert result["products_updated"] == 1
        stored = await session.get(Product, product_id)
        assert stored is not None
        assert stored.sku_code == "V1/0"
        assert stored.name == "Existing name"
        assert stored.wb_barcode == "901-CODE-1"


@pytest.mark.asyncio
async def test_new_size_primary_barcode_conflict_reports_both_chrt_ids(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    async with SessionLocal() as session:
        owner = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Owner",
            sku_code="OWNER",
            wb_chrt_id=902,
            wb_barcode="SHARED-PRIMARY",
        )
        session.add(owner)
        await session.commit()
        owner_id = owner.id

        result = await upsert_products_from_wb_cards(
            session,
            tenant_id,
            seller_id,
            [
                {
                    "nmID": 9003,
                    "vendorCode": "NEW-SIZE",
                    "sizes": [
                        {
                            "chrtID": 903,
                            "techSize": "M",
                            "skus": ["SHARED-PRIMARY", "NEW-CODE"],
                        }
                    ],
                }
            ],
        )

        assert result["products_created"] == 0
        assert result["products_skipped"] == 1
        assert result["barcode_conflicts"] == 1
        assert result["barcode_conflict_details"] == [
            {
                "barcode": "SHARED-PRIMARY",
                "incoming_chrt_id": 903,
                "incoming_product_id": None,
                "existing_chrt_id": 902,
                "existing_product_id": str(owner_id),
            }
        ]


@pytest.mark.asyncio
async def test_manual_relink_replaces_primary_and_releases_wrong_card_barcodes(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    cards = [
        {
            "nmID": 9101,
            "vendorCode": "CARD-A",
            "sizes": [
                {"chrtID": 910101, "techSize": "A", "skus": ["A-1", "A-2"]}
            ],
        },
        {
            "nmID": 9102,
            "vendorCode": "CARD-B",
            "sizes": [
                {"chrtID": 910201, "techSize": "B", "skus": ["B-1", "B-2"]}
            ],
        },
    ]
    async with SessionLocal() as session:
        await upsert_imported_cards(session, tenant_id, seller_id, cards)
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Manual",
            sku_code="MANUAL-RELINK",
        )
        session.add(product)
        await session.commit()
        product_id = product.id

        await link_product_to_wb_card(
            session, tenant_id, seller_id, product_id, 9101, wb_barcode="A-2"
        )
        await link_product_to_wb_card(
            session, tenant_id, seller_id, product_id, 9102, wb_barcode="B-2"
        )

        stored = await session.get(Product, product_id)
        assert stored is not None
        assert stored.wb_nm_id == 9102
        assert stored.wb_chrt_id == 910201
        assert stored.wb_barcode == "B-2"
        aliases = set(
            (
                await session.execute(
                    select(ProductBarcode.barcode).where(
                        ProductBarcode.product_id == product_id
                    )
                )
            ).scalars()
        )
        assert aliases == {"B-1", "B-2"}


@pytest.mark.asyncio
async def test_catalog_page_search_does_not_mix_sibling_size_skus(
    async_client: AsyncClient,
) -> None:
    tenant_id, seller_id = await _tenant_and_seller(async_client)
    card = {
        "nmID": 8100,
        "vendorCode": "SIBLING-SIZES",
        "title": "Sibling sizes",
        "sizes": [
            {"chrtID": 201, "techSize": "S", "skus": ["SIZE-S-1", "SIZE-S-2"]},
            {"chrtID": 202, "techSize": "M", "skus": ["SIZE-M-1"]},
        ],
    }
    async with SessionLocal() as session:
        await upsert_imported_cards(session, tenant_id, seller_id, [card])
        await upsert_products_from_wb_cards(session, tenant_id, seller_id, [card])
        rows, total, _scope_total, _categories = await list_linked_wb_catalog_page_rows(
            session,
            tenant_id,
            seller_id=seller_id,
            search="SIZE-S-2",
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].wb_size == "S"
        assert rows[0].wb_barcodes == ("SIZE-S-1", "SIZE-S-2")

        nm_rows, nm_total, _scope_total, _categories = (
            await list_linked_wb_catalog_page_rows(
                session,
                tenant_id,
                seller_id=seller_id,
                search="8100",
            )
        )
        assert nm_total == 2
        assert {row.wb_size for row in nm_rows} == {"S", "M"}

        size_rows, size_total, _scope_total, _categories = (
            await list_linked_wb_catalog_page_rows(
                session,
                tenant_id,
                seller_id=seller_id,
                search="M",
            )
        )
        assert size_total == 1
        assert size_rows[0].wb_size == "M"
