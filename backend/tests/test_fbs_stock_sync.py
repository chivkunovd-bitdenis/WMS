"""Tests for FBS stock reconciliation service (STOCK-080).

TC-NEW-FBS-STOCK-002: batching 1001 → two PUT batches.
TC-NEW-FBS-STOCK-009: PUT + readback match/mismatch.
TC-NEW-FBS-STOCK-010: stale published chrt zeroed when product gone.
TC-NEW-FBS-STOCK-011: missing chrt + duplicate chrt conflict.
TC-NEW-FBS-STOCK-012: WB errors without token leakage; 429 single retry.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models import Base
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
    NoopStockSyncRateLimiter,
    sync_binding_stocks,
)
from app.services.integration_fernet import encrypt_secret
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
) -> Product:
    return Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=f"Product {sku_suffix}",
        sku_code=f"SKU-{sku_suffix}",
        wb_chrt_id=chrt_id,
    )


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
    assert item.last_confirmed_amount == 0
    assert "wb-test-token-secret" not in str(result)


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


# TC-NEW-FBS-STOCK-010 — zero stale published chrt
@pytest.mark.asyncio
async def test_sync_zeroes_previously_published_absent_product(
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

    assert result.products_zeroed == 1
    assert result.products_targeted == 1
    assert transport.put_calls[0][0].amount == 0
    assert transport.stored[999] == 0


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
    from datetime import UTC, datetime, timedelta

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
        stocks = [{"chrtId": cid, "amount": 0} for cid in chrt_ids]
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
        await db_session.execute(
            select(FbsStockSyncItem).where(
                FbsStockSyncItem.binding_id == ctx.binding.id,
                FbsStockSyncItem.status == STOCK_SYNC_STATUS_CONFIRMED,
            )
        )
    ).scalars().all()
    assert len(confirmed_rows) == 1000

    error_rows = (
        await db_session.execute(
            select(FbsStockSyncItem).where(
                FbsStockSyncItem.binding_id == ctx.binding.id,
                FbsStockSyncItem.status == STOCK_SYNC_STATUS_ERROR,
            )
        )
    ).scalars().all()
    assert len(error_rows) == 1
