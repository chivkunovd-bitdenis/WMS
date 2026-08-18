"""Tests for FBS stock reconciliation service (STOCK-080).

TC-NEW-FBS-STOCK-002: batching 1001 → two PUT batches.
TC-NEW-FBS-STOCK-009: PUT + readback match/mismatch.
TC-NEW-FBS-STOCK-010: stale published chrt zeroed when product gone.
TC-NEW-FBS-STOCK-011: missing chrt + duplicate chrt conflict.
TC-NEW-FBS-STOCK-012: WB errors without token leakage; 429 single retry.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_stock_sync_item import (
    STOCK_SYNC_STATUS_CONFIRMED,
    STOCK_SYNC_STATUS_CONFLICT,
    STOCK_SYNC_STATUS_ERROR,
    FbsStockSyncItem,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.fbs_stock_sync_service import (
    DEFAULT_RATE_INTERVAL_SECONDS,
    ERROR_DUPLICATE_CHRT,
    ERROR_READBACK_MISMATCH,
    ERROR_SYNC_BUSY,
    ERROR_UNSAFE_STOCK_UNKNOWN,
    ERROR_UNSAFE_ZERO_BLOCKED,
    NoopStockSyncRateLimiter,
    _build_publish_plan,
    _try_acquire_lease,
    sync_binding_stocks,
)
from app.services.integration_fernet import encrypt_secret
from app.services.seller_wb_catalog_service import list_seller_wb_catalog_rows
from app.services.wildberries_client import MarketplaceStockAmount


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@dataclass
class _SeedContext:
    tenant: Tenant
    seller: Seller
    warehouse: Warehouse
    binding: FbsWarehouseBinding
    api_token: str = "wb-test-token-secret"


async def _seed_binding(
    session: AsyncSession,
    *,
    wb_warehouse_id: int = 501001,
) -> _SeedContext:
    tenant = Tenant(id=uuid.uuid4(), name="Tenant", slug=f"t-{uuid.uuid4().hex[:8]}")
    seller = Seller(id=uuid.uuid4(), tenant_id=tenant.id, name="Seller")
    warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="FBS WH",
        code=f"wh-{uuid.uuid4().hex[:6]}",
    )
    binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        seller_id=seller.id,
        wb_warehouse_id=wb_warehouse_id,
        wms_warehouse_id=warehouse.id,
        is_active=True,
        stock_sync_enabled=True,
    )
    creds = SellerWildberriesCredentials(
        seller_id=seller.id,
        marketplace_token_encrypted=encrypt_secret("wb-test-token-secret"),
    )
    session.add_all([tenant, seller, warehouse, binding, creds])
    await session.commit()
    return _SeedContext(tenant=tenant, seller=seller, warehouse=warehouse, binding=binding)


def _product(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    chrt_id: int | None,
    sku_suffix: str,
    fbs_stock_sync_enabled: bool = True,
    fbs_stock_limit: int | None = None,
) -> Product:
    return Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=f"Product {sku_suffix}",
        sku_code=f"SKU-{sku_suffix}",
        wb_chrt_id=chrt_id,
        fbs_stock_sync_enabled=fbs_stock_sync_enabled,
        fbs_stock_limit=fbs_stock_limit,
    )


async def _add_fbs_pool(
    session: AsyncSession,
    ctx: _SeedContext,
    product: Product,
    quantity: int,
) -> None:
    """Seed a manual pool allocation for ctx.binding — the new source of truth."""
    session.add(
        FbsBindingStockPool(
            tenant_id=ctx.tenant.id,
            binding_id=ctx.binding.id,
            product_id=product.id,
            quantity=quantity,
        )
    )
    await session.commit()


@dataclass
class RecordingRateLimiter:
    waits: list[float] = field(default_factory=list)

    async def wait(self, seconds: float = 0.0) -> None:
        self.waits.append(seconds)


class _MockStocksTransport:
    """Stateful mock for PUT/POST /api/v3/stocks/{warehouseId}."""

    def __init__(
        self,
        *,
        put_status_sequence: list[int] | None = None,
        readback_overrides: dict[int, int] | None = None,
    ) -> None:
        self.stored: dict[int, int] = {}
        self.put_calls: list[list[MarketplaceStockAmount]] = []
        self.post_calls: list[list[int]] = []
        self.put_attempts = 0
        self._put_status_sequence = list(put_status_sequence or [])
        self._readback_overrides = readback_overrides or {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            self.put_attempts += 1
            if self._put_status_sequence:
                status = self._put_status_sequence.pop(0)
                if status == 429:
                    return httpx.Response(
                        429,
                        headers={"Retry-After": "1"},
                        json={"detail": "wb-test-token-secret"},
                    )
                if status >= 400:
                    return httpx.Response(status, json={"detail": "error"})
            body = json.loads(request.content.decode())
            stocks = body.get("stocks", [])
            batch: list[MarketplaceStockAmount] = []
            for entry in stocks:
                chrt_id = int(entry["chrtId"])
                amount = int(entry["amount"])
                self.stored[chrt_id] = amount
                batch.append(MarketplaceStockAmount(chrt_id=chrt_id, amount=amount))
            self.put_calls.append(batch)
            return httpx.Response(204)

        if request.method == "POST":
            body = json.loads(request.content.decode())
            chrt_ids = [int(x) for x in body.get("chrtIds", [])]
            self.post_calls.append(chrt_ids)
            stocks = []
            for chrt_id in chrt_ids:
                amount = self._readback_overrides.get(chrt_id, self.stored.get(chrt_id, 0))
                stocks.append({"chrtId": chrt_id, "amount": amount})
            return httpx.Response(200, json={"stocks": stocks})

        raise AssertionError(f"unexpected method {request.method}")


def _client(transport: _MockStocksTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(transport.handler),
        base_url="https://wb-mock.test",
    )


@pytest.mark.asyncio
async def test_sync_skips_products_with_disabled_fbs_sync_flag(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    disabled = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=9101,
        sku_suffix="disabled",
        fbs_stock_sync_enabled=False,
    )
    db_session.add(disabled)
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_targeted == 0
    assert result.products_zeroed == 0
    assert transport.put_calls == []


def test_build_publish_plan_reads_amounts_directly_from_pool() -> None:
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    product_a = _product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        chrt_id=9201,
        sku_suffix="pool-100",
    )
    product_b = _product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        chrt_id=9202,
        sku_suffix="pool-10",
    )
    pool_quantities = {
        product_a.id: 100,
        product_b.id: 10,
    }

    targets, blocked_targets, skipped_missing, conflict_chrts = _build_publish_plan(
        [product_a, product_b],
        pool_quantities,
        {},
    )
    by_chrt = {target.chrt_id: target.amount for target in targets}

    assert blocked_targets == []
    assert skipped_missing == []
    assert conflict_chrts == set()
    assert by_chrt[9201] == 100
    assert by_chrt[9202] == 10
    assert all(not target.is_explicit_zero for target in targets)


def test_build_publish_plan_skips_missing_and_publishes_explicit_zero() -> None:
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    missing = _product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        chrt_id=9211,
        sku_suffix="missing-from-pool",
    )
    explicit_zero = _product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        chrt_id=9212,
        sku_suffix="explicit-zero",
    )

    targets, blocked_targets, skipped_missing, conflict_chrts = _build_publish_plan(
        [missing, explicit_zero],
        {explicit_zero.id: 0},
        {},
    )

    # missing has no row in fbs_binding_stock_pools for this binding — that just
    # means the admin hasn't allocated any of the pool to this warehouse yet, not
    # an error, so it's silently skipped.
    assert blocked_targets == []
    assert skipped_missing == []
    assert conflict_chrts == set()
    by_chrt = {target.chrt_id: target for target in targets}
    assert set(by_chrt) == {9212}
    assert by_chrt[9212].amount == 0
    assert by_chrt[9212].is_explicit_zero is True


@pytest.mark.asyncio
async def test_sync_does_not_zero_disabled_product_from_stale_confirmed_item(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    disabled = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=9301,
        sku_suffix="disabled-zero-once",
        fbs_stock_sync_enabled=False,
    )
    db_session.add(disabled)
    await db_session.commit()

    db_session.add(
        FbsStockSyncItem(
            binding_id=ctx.binding.id,
            chrt_id=9301,
            product_id=disabled.id,
            last_target_amount=5,
            last_confirmed_amount=5,
            status=STOCK_SYNC_STATUS_CONFIRMED,
        )
    )
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_targeted == 0
    assert result.products_zeroed == 0
    assert result.errors == 0
    assert transport.put_calls == []


# Manual-pool model: no fbs_binding_stock_pools row for this binding means the
# admin hasn't allocated any of the pool here yet — nothing publishes, no error.
@pytest.mark.asyncio
async def test_sync_skips_enabled_product_without_pool_allocation(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=331,
        sku_suffix="no-fbs-pool",
    )
    db_session.add(product)
    await db_session.commit()

    transport = _MockStocksTransport()
    transport.stored[331] = 20
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_targeted == 0
    assert result.products_confirmed == 0
    assert result.errors == 0
    assert transport.put_calls == []
    assert transport.stored[331] == 20

    item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == ctx.binding.id)
        )
    ).scalar_one_or_none()
    assert item is None

    await db_session.refresh(ctx.binding)
    # Пустой план публикации — это НЕ успех: в Wildberries не ушло ни одной позиции.
    # Раньше здесь стоял confirmed, и экран показывал «Wildberries подтвердил остаток»
    # на выгрузке, которая ничего не отправила.
    assert ctx.binding.last_sync_status == "nothing_to_publish"
    assert ctx.binding.last_error_code is None


# TC-NEW-FBS-STOCK-009 — PUT + readback happy path
@pytest.mark.asyncio
async def test_sync_confirms_when_readback_matches(db_session: AsyncSession) -> None:
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=333,
        sku_suffix="a",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 7)

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.bindings_processed == 1
    assert result.products_targeted == 1
    assert result.products_confirmed == 1
    assert result.errors == 0

    item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == ctx.binding.id)
        )
    ).scalar_one()
    assert item.status == STOCK_SYNC_STATUS_CONFIRMED
    assert item.last_confirmed_amount == 7
    assert "wb-test-token-secret" not in str(result)


# Manual-pool model: the number in fbs_binding_stock_pools publishes AS-IS — not
# reduced by FBS order reservations, not derived from InventoryBalance/StockDirection.
@pytest.mark.asyncio
async def test_sync_publishes_exact_manual_pool_amount(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=1210,
        sku_suffix="f10-pool",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 200)

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_targeted == 1
    assert result.products_confirmed == 1
    assert result.errors == 0
    assert [[entry.amount for entry in batch] for batch in transport.put_calls] == [[200]]
    assert transport.stored[1210] == 200
    assert transport.post_calls == [[1210]]

    item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == ctx.binding.id)
        )
    ).scalar_one()
    assert item.status == STOCK_SYNC_STATUS_CONFIRMED
    assert item.last_target_amount == 200
    assert item.last_confirmed_amount == 200


# Manual-pool model: two bindings for the same product each carry their own row in
# fbs_binding_stock_pools — no shared computed number, so no ambiguity to block.
@pytest.mark.asyncio
async def test_sync_publishes_independent_pool_amounts_per_binding(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session, wb_warehouse_id=501101)
    second_warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        name="Second FBS WH",
        code=f"wh2-{uuid.uuid4().hex[:6]}",
    )
    second_binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        wb_warehouse_id=501102,
        wms_warehouse_id=second_warehouse.id,
        is_active=True,
        stock_sync_enabled=True,
    )
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=1211,
        sku_suffix="f10-independent-pool",
    )
    db_session.add_all([second_warehouse, second_binding, product])
    await db_session.commit()
    # Manual split: 12 units to the first binding, 8 to the second — same product,
    # two different WB warehouses, no shared computed number.
    await _add_fbs_pool(db_session, ctx, product, 12)
    db_session.add(
        FbsBindingStockPool(
            tenant_id=ctx.tenant.id,
            binding_id=second_binding.id,
            product_id=product.id,
            quantity=8,
        )
    )
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        first_result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )
        second_result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            second_binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert first_result.products_targeted == 1
    assert second_result.products_targeted == 1
    assert first_result.products_confirmed == 1
    assert second_result.products_confirmed == 1
    assert first_result.errors == 0
    assert second_result.errors == 0
    assert [[entry.amount for entry in batch] for batch in transport.put_calls] == [[12], [8]]

    rows = list(
        (
            await db_session.execute(
                select(FbsStockSyncItem).where(FbsStockSyncItem.chrt_id == 1211)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    amounts_by_binding = {row.binding_id: row.last_target_amount for row in rows}
    assert amounts_by_binding[ctx.binding.id] == 12
    assert amounts_by_binding[second_binding.id] == 8
    assert {row.status for row in rows} == {STOCK_SYNC_STATUS_CONFIRMED}


@pytest.mark.asyncio
async def test_seller_catalog_prefers_active_confirmed_readback_over_irrelevant_error(
    db_session: AsyncSession,
) -> None:
    """TC-NEW-F22-001: catalog exposes confirmed WB readback instead of stale safe error."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=111001,
        sku_suffix="catalog-confirmed",
    )
    inactive_warehouse = Warehouse(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        name="Inactive FBS WH",
        code=f"inactive-{uuid.uuid4().hex[:6]}",
    )
    inactive_binding = FbsWarehouseBinding(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        wb_warehouse_id=501002,
        wms_warehouse_id=inactive_warehouse.id,
        is_active=False,
        stock_sync_enabled=True,
    )
    db_session.add_all(
        [
            product,
            inactive_warehouse,
            inactive_binding,
            FbsStockSyncItem(
                binding_id=ctx.binding.id,
                chrt_id=111001,
                product_id=product.id,
                last_target_amount=7,
                last_confirmed_amount=7,
                status=STOCK_SYNC_STATUS_CONFIRMED,
                updated_at=datetime(2026, 8, 13, 14, 10, tzinfo=UTC),
            ),
            FbsStockSyncItem(
                binding_id=inactive_binding.id,
                chrt_id=111001,
                product_id=product.id,
                last_target_amount=None,
                last_confirmed_amount=None,
                status=STOCK_SYNC_STATUS_ERROR,
                last_error_code=ERROR_UNSAFE_STOCK_UNKNOWN,
                updated_at=datetime(2026, 8, 13, 14, 20, tzinfo=UTC),
            ),
        ]
    )
    await db_session.commit()

    rows = await list_seller_wb_catalog_rows(db_session, ctx.tenant.id, ctx.seller.id)
    row = next(row for row in rows if row.product_id == product.id)

    assert row.fbs_sync_status == STOCK_SYNC_STATUS_CONFIRMED
    assert row.fbs_published_amount == 7


@pytest.mark.asyncio
async def test_seller_catalog_keeps_active_safe_error_without_confirmed_readback(
    db_session: AsyncSession,
) -> None:
    """TC-NEW-F22-001: safe-zero guard remains visible when active binding has no success."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=111002,
        sku_suffix="catalog-safe-error",
    )
    db_session.add_all(
        [
            product,
            FbsStockSyncItem(
                binding_id=ctx.binding.id,
                chrt_id=111002,
                product_id=product.id,
                last_target_amount=None,
                last_confirmed_amount=None,
                status=STOCK_SYNC_STATUS_ERROR,
                last_error_code=ERROR_UNSAFE_STOCK_UNKNOWN,
                updated_at=datetime(2026, 8, 13, 14, 30, tzinfo=UTC),
            ),
        ]
    )
    await db_session.commit()

    rows = await list_seller_wb_catalog_rows(db_session, ctx.tenant.id, ctx.seller.id)
    row = next(row for row in rows if row.product_id == product.id)

    assert row.fbs_sync_status == STOCK_SYNC_STATUS_ERROR
    assert row.fbs_published_amount is None


@pytest.mark.asyncio
async def test_sync_marks_error_on_readback_mismatch(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-009: false 204 — PUT ok but POST returns different amount."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=444,
        sku_suffix="m",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 5)

    transport = _MockStocksTransport(readback_overrides={444: 6})
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 0
    assert result.errors == 1
    item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == ctx.binding.id)
        )
    ).scalar_one()
    assert item.status == STOCK_SYNC_STATUS_ERROR
    assert item.last_error_code == ERROR_READBACK_MISMATCH

    await db_session.refresh(ctx.binding)
    assert ctx.binding.last_error_code == ERROR_READBACK_MISMATCH


# TC-NEW-F22-001 — stale confirmed rows must not produce automatic PUT 0
@pytest.mark.asyncio
async def test_sync_skips_previously_published_absent_product_without_zeroing(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    stale_item = FbsStockSyncItem(
        binding_id=ctx.binding.id,
        chrt_id=999,
        product_id=None,
        last_target_amount=5,
        last_confirmed_amount=5,
        status=STOCK_SYNC_STATUS_CONFIRMED,
    )
    db_session.add(stale_item)
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_zeroed == 0
    assert result.products_targeted == 0
    assert transport.put_calls == []
    assert transport.stored == {}


# TC-NEW-FBS-STOCK-011 — missing chrt + duplicate conflict
@pytest.mark.asyncio
async def test_sync_skips_missing_chrt_and_conflicts_duplicates(
    db_session: AsyncSession,
) -> None:
    ctx = await _seed_binding(db_session)
    missing = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=None,
        sku_suffix="no-chrt",
    )
    dup_a = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=777,
        sku_suffix="dup-a",
    )
    dup_b = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=777,
        sku_suffix="dup-b",
    )
    ok = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=888,
        sku_suffix="ok",
    )
    db_session.add_all([missing, dup_a, dup_b, ok])
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, ok, 8)

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert missing.id in result.skipped_missing_chrt_id
    assert result.conflicts == 1
    assert result.products_targeted == 1
    published_chrts = {entry.chrt_id for batch in transport.put_calls for entry in batch}
    assert 777 not in published_chrts
    assert 888 in published_chrts

    conflict_item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(
                FbsStockSyncItem.binding_id == ctx.binding.id,
                FbsStockSyncItem.chrt_id == 777,
            )
        )
    ).scalar_one()
    assert conflict_item.status == STOCK_SYNC_STATUS_CONFLICT
    assert conflict_item.last_error_code == ERROR_DUPLICATE_CHRT


# TC-NEW-FBS-STOCK-002 — 1001 items → two PUT batches
@pytest.mark.asyncio
async def test_sync_splits_1001_items_into_two_batches(db_session: AsyncSession) -> None:
    ctx = await _seed_binding(db_session)
    products = [
        _product(
            tenant_id=ctx.tenant.id,
            seller_id=ctx.seller.id,
            chrt_id=chrt_id,
            sku_suffix=str(chrt_id),
        )
        for chrt_id in range(1, 1002)
    ]
    db_session.add_all(products)
    await db_session.commit()
    db_session.add_all(
        [
            FbsBindingStockPool(
                tenant_id=ctx.tenant.id,
                binding_id=ctx.binding.id,
                product_id=product.id,
                quantity=1,
            )
            for product in products
        ]
    )
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_targeted == 1001
    assert result.products_confirmed == 1001
    assert len(transport.put_calls) == 2
    assert len(transport.put_calls[0]) == 1000
    assert len(transport.put_calls[1]) == 1
    merged = [entry.chrt_id for batch in transport.put_calls for entry in batch]
    assert merged == list(range(1, 1002))
    assert len(merged) == len(set(merged))


# TC-NEW-FBS-STOCK-012 — upstream errors without token leakage
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 409])
async def test_sync_upstream_error_marks_batch_error(
    db_session: AsyncSession,
    status_code: int,
) -> None:
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=101,
        sku_suffix="err",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    transport = _MockStocksTransport(put_status_sequence=[status_code])
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 0
    assert result.errors == 1
    assert "wb-test-token-secret" not in str(result)
    item = (
        await db_session.execute(
            select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == ctx.binding.id)
        )
    ).scalar_one()
    assert item.status == STOCK_SYNC_STATUS_ERROR
    assert item.last_error_code == f"wb_upstream_error_{status_code}"

    await db_session.refresh(ctx.binding)
    assert ctx.binding.last_error_code == f"wb_upstream_error_{status_code}"


@pytest.mark.asyncio
async def test_sync_429_after_retry_marks_binding_upstream_error(
    db_session: AsyncSession,
) -> None:
    """STOCKFIX-055: exhausted 429 retry surfaces wb_upstream_error_429 on binding."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=205,
        sku_suffix="429-fail",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    transport = _MockStocksTransport(put_status_sequence=[429, 429])
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            rate_limiter=NoopStockSyncRateLimiter(),
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 0
    assert result.errors == 1
    await db_session.refresh(ctx.binding)
    assert ctx.binding.last_error_code == "wb_upstream_error_429"
    assert ctx.binding.last_error_code != ERROR_READBACK_MISMATCH


@pytest.mark.asyncio
async def test_sync_transport_error_marks_binding_not_readback_mismatch(
    db_session: AsyncSession,
) -> None:
    """STOCKFIX-055: transport failure surfaces wb_transport_error on binding."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=206,
        sku_suffix="transport",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            raise httpx.ConnectError("connection refused")
        raise AssertionError(f"unexpected method {request.method}")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://wb-mock.test"
    ) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            rate_limiter=NoopStockSyncRateLimiter(),
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 0
    assert result.errors == 1
    await db_session.refresh(ctx.binding)
    assert ctx.binding.last_error_code == "wb_transport_error"
    assert ctx.binding.last_error_code != ERROR_READBACK_MISMATCH


@pytest.mark.asyncio
async def test_sync_429_retries_once_then_succeeds(db_session: AsyncSession) -> None:
    """TC-NEW-FBS-STOCK-012: 429 triggers one retry via rate limiter, then confirms."""
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=202,
        sku_suffix="429",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    transport = _MockStocksTransport(put_status_sequence=[429])
    limiter = RecordingRateLimiter()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            rate_limiter=limiter,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 1
    assert transport.put_attempts == 2
    assert 1.0 in limiter.waits


@pytest.mark.asyncio
async def test_default_rate_limiter_paces_wb_calls(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production path uses AsyncStockSyncRateLimiter (~200ms between WB calls)."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "app.services.fbs_stock_sync_service.asyncio.sleep",
        fake_sleep,
    )

    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=303,
        sku_suffix="pace",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 1
    assert DEFAULT_RATE_INTERVAL_SECONDS in sleeps


@pytest.mark.asyncio
async def test_sync_429_honors_retry_after_on_production_limiter(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """429 Retry-After header is passed to the default limiter wait."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "app.services.fbs_stock_sync_service.asyncio.sleep",
        fake_sleep,
    )

    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id,
        seller_id=ctx.seller.id,
        chrt_id=204,
        sku_suffix="retry-after",
    )
    db_session.add(product)
    await db_session.commit()
    await _add_fbs_pool(db_session, ctx, product, 4)

    transport = _MockStocksTransport(put_status_sequence=[429])
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 1
    assert transport.put_attempts == 2
    assert 1.0 in sleeps


@pytest.mark.asyncio
async def test_sync_skips_when_lease_active(db_session: AsyncSession) -> None:
    """Concurrent sync: active lease → skipped_busy."""
    ctx = await _seed_binding(db_session)
    ctx.binding.lease_until = datetime.now(UTC) + timedelta(minutes=5)
    await db_session.commit()

    transport = _MockStocksTransport()
    async with _client(transport) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.skipped_busy is True
    assert result.error_code == ERROR_SYNC_BUSY
    assert result.bindings_processed == 0
    assert len(transport.put_calls) == 0


@pytest.mark.asyncio
async def test_try_acquire_lease_handles_naive_loaded_lease_until(
    db_session: AsyncSession,
) -> None:
    """SQLite may load timezone=True values as naive; lease compare must not crash."""
    ctx = await _seed_binding(db_session)
    ctx.binding.lease_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    acquired = await _try_acquire_lease(db_session, ctx.binding)

    assert acquired is True
    assert ctx.binding.lease_until is not None
    assert ctx.binding.lease_until.tzinfo is UTC


@pytest.mark.asyncio
async def test_partial_batch_failure_leaves_confirmed_batch(
    db_session: AsyncSession,
) -> None:
    """Batch 1 confirms; batch 2 PUT fails — first batch stays confirmed (idempotent)."""
    ctx = await _seed_binding(db_session)
    products = [
        _product(
            tenant_id=ctx.tenant.id,
            seller_id=ctx.seller.id,
            chrt_id=chrt_id,
            sku_suffix=str(chrt_id),
        )
        for chrt_id in range(1, 1002)
    ]
    db_session.add_all(products)
    await db_session.commit()
    db_session.add_all(
        [
            FbsBindingStockPool(
                tenant_id=ctx.tenant.id,
                binding_id=ctx.binding.id,
                product_id=product.id,
                quantity=1,
            )
            for product in products
        ]
    )
    await db_session.commit()

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.method == "PUT":
            call_count += 1
            if call_count == 2:
                return httpx.Response(409, json={"detail": "conflict"})
            return httpx.Response(204)
        body = json.loads(request.content.decode())
        chrt_ids = body.get("chrtIds", [])
        stocks = [{"chrtId": cid, "amount": 1} for cid in chrt_ids]
        return httpx.Response(200, json={"stocks": stocks})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://wb-mock.test"
    ) as http_client:
        result = await sync_binding_stocks(
            db_session,
            ctx.tenant.id,
            ctx.seller.id,
            ctx.binding,
            http_client,
            rate_limiter=NoopStockSyncRateLimiter(),
            marketplace_api_base="https://wb-mock.test",
        )

    assert result.products_confirmed == 1000
    assert result.errors == 1

    confirmed_rows = (
        (
            await db_session.execute(
                select(FbsStockSyncItem).where(
                    FbsStockSyncItem.binding_id == ctx.binding.id,
                    FbsStockSyncItem.status == STOCK_SYNC_STATUS_CONFIRMED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(confirmed_rows) == 1000

    error_rows = (
        (
            await db_session.execute(
                select(FbsStockSyncItem).where(
                    FbsStockSyncItem.binding_id == ctx.binding.id,
                    FbsStockSyncItem.status == STOCK_SYNC_STATUS_ERROR,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(error_rows) == 1

    await db_session.refresh(ctx.binding)
    assert ctx.binding.last_error_code == "wb_upstream_error_409"


@pytest.mark.asyncio
async def test_try_acquire_lease_atomic_under_concurrency(
    db_session: AsyncSession,
) -> None:
    """STOCKFIX-050: two parallel workers — only one acquires lease."""
    ctx = await _seed_binding(db_session)
    binding_id = ctx.binding.id
    barrier = asyncio.Barrier(2)
    results: list[bool] = []

    async def attempt_acquire() -> None:
        async with SessionLocal() as session:
            binding = await session.get(FbsWarehouseBinding, binding_id)
            assert binding is not None
            await barrier.wait()
            acquired = await _try_acquire_lease(session, binding)
            results.append(acquired)

    await asyncio.gather(attempt_acquire(), attempt_acquire())

    assert sorted(results) == [False, True]

    async with SessionLocal() as session:
        binding = await session.get(FbsWarehouseBinding, binding_id)
        assert binding is not None
        assert binding.lease_until is not None
