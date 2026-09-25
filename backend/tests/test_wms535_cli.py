from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.cli.backfill_wb_product_barcodes import (
    BackfillReport,
    _fetch_page_with_retry,
    process_cards_page,
)
from app.cli.merge_duplicate_wb_chrt_products import run_merge
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.wildberries_client import WildberriesClientError


async def _seed_scope() -> tuple[uuid.UUID, uuid.UUID]:
    tenant = Tenant(name="WMS 535 CLI", slug=f"wms-535-cli-{uuid.uuid4().hex}")
    async with SessionLocal() as session:
        session.add(tenant)
        await session.flush()
        seller = Seller(tenant_id=tenant.id, name="CLI seller")
        session.add(seller)
        await session.commit()
        return tenant.id, seller.id


@pytest.mark.asyncio
async def test_backfill_retries_429_and_temporary_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    delays: list[float] = []

    async def fake_fetch(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WildberriesClientError("upstream_error", status_code=429)
        if attempts == 2:
            raise WildberriesClientError("upstream_error", status_code=503)
        return {"cards": [], "cursor": {}}

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "app.cli.backfill_wb_product_barcodes.fetch_cards_list", fake_fetch
    )
    monkeypatch.setattr("app.cli.backfill_wb_product_barcodes.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient() as client:
        result = await _fetch_page_with_retry(
            client,
            api_token="not-printed",
            cursor_updated_at=None,
            cursor_nm_id=None,
        )
    assert result == {"cards": [], "cursor": {}}
    assert attempts == 3
    assert delays == [1, 2]


@pytest.mark.asyncio
async def test_backfill_page_is_dry_run_by_default_and_apply_is_idempotent(
    db_session: object,
) -> None:
    del db_session
    tenant_id, seller_id = await _seed_scope()
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Existing",
            sku_code="EXISTING",
            wb_chrt_id=501,
            wb_barcode="5000000000001",
        )
        session.add(product)
        await session.commit()
        product_id = product.id

    cards = [
        {
            "nmID": 9001,
            "sizes": [
                {
                    "chrtID": 501,
                    "skus": ["5000000000001", "5000000000002"],
                }
            ],
        }
    ]
    dry_report = BackfillReport(
        mode="dry-run", tenant_id=str(tenant_id), seller_id=str(seller_id)
    )
    async with SessionLocal() as session:
        await process_cards_page(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            cards=cards,
            apply=False,
            report=dry_report,
        )
    assert dry_report.barcodes_added == 2
    async with SessionLocal() as session:
        assert await session.scalar(select(ProductBarcode.id)) is None

    apply_report = BackfillReport(
        mode="apply", tenant_id=str(tenant_id), seller_id=str(seller_id)
    )
    async with SessionLocal() as session:
        await process_cards_page(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            cards=cards,
            apply=True,
            report=apply_report,
        )
    assert apply_report.barcodes_added == 2
    async with SessionLocal() as session:
        assert set(
            (
                await session.execute(
                    select(ProductBarcode.barcode).where(
                        ProductBarcode.product_id == product_id
                    )
                )
            ).scalars()
        ) == {"5000000000001", "5000000000002"}

    repeat_report = BackfillReport(
        mode="apply", tenant_id=str(tenant_id), seller_id=str(seller_id)
    )
    async with SessionLocal() as session:
        await process_cards_page(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            cards=cards,
            apply=True,
            report=repeat_report,
        )
    assert repeat_report.barcodes_added == 0
    assert repeat_report.barcodes_existing == 2


@pytest.mark.asyncio
async def test_duplicate_merge_discovers_and_moves_product_foreign_keys(
    db_session: object,
) -> None:
    del db_session
    tenant_id, seller_id = await _seed_scope()
    async with SessionLocal() as session:
        keeper = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Earlier",
            sku_code="DUP-A",
            wb_chrt_id=777,
            wb_barcode="7000000000001",
        )
        duplicate = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Later",
            sku_code="DUP-B",
            wb_chrt_id=777,
            wb_barcode="7000000000002",
        )
        session.add_all([keeper, duplicate])
        await session.flush()
        session.add_all(
            [
                ProductBarcode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=keeper.id,
                    barcode="7000000000001",
                ),
                ProductBarcode(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=duplicate.id,
                    barcode="7000000000002",
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=duplicate.id,
                    marketplace="ozon",
                    external_product_id="wms535-duplicate",
                    external_offer_id="wms535-offer",
                    external_sku="wms535-sku",
                    external_barcodes=[],
                ),
            ]
        )
        await session.commit()
        ordered = list(
            (
                await session.execute(
                    select(Product)
                    .where(
                        Product.tenant_id == tenant_id,
                        Product.seller_id == seller_id,
                        Product.wb_chrt_id == 777,
                    )
                    .order_by(Product.created_at, Product.id)
                )
            )
            .scalars()
            .all()
        )
        keeper_id, duplicate_id = ordered[0].id, ordered[1].id

    dry_run = await run_merge(
        tenant_id=tenant_id,
        seller_id=seller_id,
        apply=False,
        expected_pairs=None,
    )
    assert dry_run["eligible"] == 1
    reference_names = {
        item["table"] for item in dry_run["foreign_key_references_discovered"]
    }
    assert "product_marketplace_links" in reference_names

    applied = await run_merge(
        tenant_id=tenant_id,
        seller_id=seller_id,
        apply=True,
        expected_pairs=1,
    )
    assert applied["merged"] == 1
    async with SessionLocal() as session:
        assert await session.get(Product, duplicate_id) is None
        assert await session.get(Product, keeper_id) is not None
        linked_product_id = await session.scalar(
            select(ProductMarketplaceLink.product_id).where(
                ProductMarketplaceLink.external_product_id == "wms535-duplicate"
            )
        )
        assert linked_product_id == keeper_id
        alias_product_ids = set(
            (
                await session.execute(
                    select(ProductBarcode.product_id).where(
                        ProductBarcode.barcode.in_(
                            ("7000000000001", "7000000000002")
                        )
                    )
                )
            ).scalars()
        )
        assert alias_product_ids == {keeper_id}
