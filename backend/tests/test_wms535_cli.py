from __future__ import annotations

import uuid
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import select

from app.cli.backfill_wb_product_barcodes import (
    BackfillReport,
    _fetch_page_with_retry,
    process_cards_page,
    run_backfill,
)
from app.cli.merge_duplicate_wb_chrt_products import run_merge
from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
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
async def test_backfill_resumes_from_explicit_cursor_and_reports_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
    db_session: object,
) -> None:
    del db_session
    tenant_id, seller_id = await _seed_scope()
    requested_cursors: list[tuple[str | None, int | None]] = []

    async def fake_tokens(*_args: object, **_kwargs: object) -> tuple[str, None, None]:
        return ("not-printed", None, None)

    async def fake_fetch(
        _client: object,
        *,
        api_token: str,
        cursor_updated_at: str | None,
        cursor_nm_id: int | None,
    ) -> dict[str, object]:
        del api_token
        requested_cursors.append((cursor_updated_at, cursor_nm_id))
        raise RuntimeError("database_connection_lost")

    monkeypatch.setattr(
        "app.cli.backfill_wb_product_barcodes.get_decrypted_tokens_for_seller",
        fake_tokens,
    )
    monkeypatch.setattr(
        "app.cli.backfill_wb_product_barcodes._fetch_page_with_retry", fake_fetch
    )

    report = await run_backfill(
        tenant_id=tenant_id,
        seller_id=seller_id,
        apply=True,
        cursor_updated_at="2026-09-25T10:11:12Z",
        cursor_nm_id=123456,
    )

    assert requested_cursors == [("2026-09-25T10:11:12Z", 123456)]
    assert report.errors_count == 1
    assert report.errors == ["RuntimeError"]


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

    cards: list[object] = [
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
                ProductDimensionEvent(
                    tenant_id=tenant_id,
                    product_id=keeper.id,
                    source="wb",
                    applied=True,
                    fingerprint="same-wb-dimensions",
                ),
                ProductDimensionEvent(
                    tenant_id=tenant_id,
                    product_id=duplicate.id,
                    source="wb",
                    applied=True,
                    fingerprint="same-wb-dimensions",
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
    reference_rows = cast(
        list[dict[str, Any]], dry_run["foreign_key_references_discovered"]
    )
    reference_names = {item["table"] for item in reference_rows}
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
        dimension_events = list(
            (
                await session.execute(
                    select(ProductDimensionEvent)
                    .where(ProductDimensionEvent.product_id == keeper_id)
                    .order_by(ProductDimensionEvent.source)
                )
            )
            .scalars()
            .all()
        )
        assert len(dimension_events) == 1
        assert dimension_events[0].applied is True
        assert dimension_events[0].source == "wb"


@pytest.mark.asyncio
async def test_duplicate_merge_dry_run_reports_same_unique_conflict_as_apply(
    db_session: object,
) -> None:
    del db_session
    tenant_id, seller_id = await _seed_scope()
    async with SessionLocal() as session:
        keeper = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Earlier conflict",
            sku_code="DUP-CONFLICT-A",
            wb_chrt_id=778,
            wb_barcode="7000000000011",
        )
        duplicate = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Later conflict",
            sku_code="DUP-CONFLICT-B",
            wb_chrt_id=778,
            wb_barcode="7000000000012",
        )
        session.add_all([keeper, duplicate])
        await session.flush()
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="CLI merge warehouse",
            code=f"merge-{uuid.uuid4().hex[:8]}",
        )
        session.add(warehouse)
        await session.flush()
        binding = FbsWarehouseBinding(
            tenant_id=tenant_id,
            seller_id=seller_id,
            marketplace="wb",
            wb_warehouse_id=778001,
            wms_warehouse_id=warehouse.id,
        )
        session.add(binding)
        await session.flush()
        session.add_all(
            [
                FbsBindingStockPool(
                    tenant_id=tenant_id,
                    binding_id=binding.id,
                    product_id=keeper.id,
                    quantity=0,
                ),
                FbsBindingStockPool(
                    tenant_id=tenant_id,
                    binding_id=binding.id,
                    product_id=duplicate.id,
                    quantity=0,
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=keeper.id,
                    marketplace="ozon",
                    external_product_id="wms535-conflict-keeper",
                    external_offer_id="wms535-conflict-offer-keeper",
                    external_sku="wms535-conflict-sku-keeper",
                    external_barcodes=[],
                ),
                ProductMarketplaceLink(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=duplicate.id,
                    marketplace="ozon",
                    external_product_id="wms535-conflict-duplicate",
                    external_offer_id="wms535-conflict-offer-duplicate",
                    external_sku="wms535-conflict-sku-duplicate",
                    external_barcodes=[],
                ),
            ]
        )
        await session.commit()
        duplicate_id = duplicate.id

    dry_run = await run_merge(
        tenant_id=tenant_id,
        seller_id=seller_id,
        apply=False,
        expected_pairs=None,
    )
    dry_pair = cast(list[dict[str, Any]], dry_run["pairs"])[0]
    assert dry_pair["status"] == "skipped"
    assert dry_pair["reason"] == (
        "unique_conflict:fbs_binding_stock_pools:"
        "uq_fbs_binding_stock_pools_binding_product"
    )
    assert dry_pair["unique_conflicts"] == [
        {
            "table": "fbs_binding_stock_pools",
            "column": "product_id",
            "constraint": "uq_fbs_binding_stock_pools_binding_product",
            "policy": "skip_pair",
        },
        {
            "table": "product_marketplace_links",
            "column": "product_id",
            "constraint": "uq_product_marketplace_links_product_provider",
            "policy": "skip_pair",
        }
    ]

    applied = await run_merge(
        tenant_id=tenant_id,
        seller_id=seller_id,
        apply=True,
        expected_pairs=1,
    )
    applied_pair = cast(list[dict[str, Any]], applied["pairs"])[0]
    assert applied_pair["reason"] == dry_pair["reason"]
    assert applied["merged"] == 0
    async with SessionLocal() as session:
        assert await session.get(Product, duplicate_id) is not None
