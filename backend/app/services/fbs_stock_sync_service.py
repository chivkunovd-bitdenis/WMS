"""Reconcile WMS FBS availability with Wildberries marketplace stocks (PUT + readback)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_stock_sync_item import (
    STOCK_SYNC_STATUS_CONFIRMED,
    STOCK_SYNC_STATUS_CONFLICT,
    STOCK_SYNC_STATUS_ERROR,
    STOCK_SYNC_STATUS_PENDING,
    FbsStockSyncItem,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.services.fbs_stock_availability_service import fbs_available_qty_by_product
from app.services.wildberries_client import (
    MarketplaceStockAmount,
    WildberriesClientError,
    fetch_marketplace_stocks,
    put_marketplace_stocks,
    split_marketplace_stocks_batches,
)
from app.services.wildberries_credentials_service import (
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)

logger = logging.getLogger(__name__)

SYNC_LEASE_DURATION = timedelta(minutes=5)
DEFAULT_RATE_INTERVAL_SECONDS = 0.2
MAX_429_RETRY_AFTER_SECONDS = 60.0

ERROR_DUPLICATE_CHRT = "duplicate_chrt_id"
ERROR_READBACK_MISMATCH = "readback_mismatch"
ERROR_MISSING_TOKEN = "missing_marketplace_token"
ERROR_SYNC_BUSY = "sync_busy"
ERROR_BINDING_MISMATCH = "binding_mismatch"
ERROR_SELLER_NOT_FOUND = "seller_not_found"


class StockSyncRateLimiter(Protocol):
    async def wait(self, seconds: float = 0.0) -> None:
        """Pause between WB calls; inject no-op implementation in unit tests."""


class NoopStockSyncRateLimiter:
    async def wait(self, seconds: float = 0.0) -> None:
        return


class FbsStockSyncError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class FbsStockSyncResult:
    bindings_processed: int = 0
    products_targeted: int = 0
    products_confirmed: int = 0
    products_zeroed: int = 0
    skipped_missing_chrt_id: list[uuid.UUID] = field(default_factory=list)
    conflicts: int = 0
    errors: int = 0
    skipped_busy: bool = False
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _PublishTarget:
    chrt_id: int
    amount: int
    product_id: uuid.UUID | None
    zeroed: bool


async def _seller_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller | None:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    return seller


async def _resolve_marketplace_api_token(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> str:
    marketplace_token = await get_decrypted_marketplace_token(session, tenant_id, seller_id)
    if marketplace_token:
        return marketplace_token
    pair = await get_decrypted_tokens_for_seller(session, tenant_id, seller_id)
    if pair is None:
        raise FbsStockSyncError(ERROR_SELLER_NOT_FOUND)
    _content, supplies_token = pair
    if not supplies_token:
        raise FbsStockSyncError(ERROR_MISSING_TOKEN)
    return supplies_token


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _try_acquire_lease(
    session: AsyncSession,
    binding: FbsWarehouseBinding,
) -> bool:
    now = _utcnow()
    if binding.lease_until is not None and binding.lease_until > now:
        return False
    binding.lease_until = now + SYNC_LEASE_DURATION
    await session.commit()
    return True


async def _release_lease(session: AsyncSession, binding: FbsWarehouseBinding) -> None:
    binding.lease_until = None
    await session.commit()


async def _load_seller_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[Product]:
    stmt = select(Product).where(
        Product.tenant_id == tenant_id,
        Product.seller_id == seller_id,
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _load_existing_sync_items(
    session: AsyncSession,
    binding_id: uuid.UUID,
) -> dict[int, FbsStockSyncItem]:
    stmt = select(FbsStockSyncItem).where(FbsStockSyncItem.binding_id == binding_id)
    res = await session.execute(stmt)
    return {item.chrt_id: item for item in res.scalars().all()}


def _build_publish_plan(
    products: list[Product],
    availability: dict[uuid.UUID, int],
    existing_items: dict[int, FbsStockSyncItem],
) -> tuple[list[_PublishTarget], list[uuid.UUID], set[int]]:
    """Return (publish targets, skipped missing chrt product ids, conflict chrt ids)."""
    skipped_missing: list[uuid.UUID] = []
    chrt_to_products: dict[int, list[Product]] = {}
    for product in products:
        if product.wb_chrt_id is None:
            skipped_missing.append(product.id)
            continue
        chrt_to_products.setdefault(int(product.wb_chrt_id), []).append(product)

    conflict_chrts = {chrt for chrt, group in chrt_to_products.items() if len(group) > 1}

    targets_by_chrt: dict[int, _PublishTarget] = {}
    for chrt_id, group in chrt_to_products.items():
        if chrt_id in conflict_chrts:
            continue
        product = group[0]
        amount = int(availability.get(product.id, 0))
        targets_by_chrt[chrt_id] = _PublishTarget(
            chrt_id=chrt_id,
            amount=amount,
            product_id=product.id,
            zeroed=False,
        )

    for chrt_id, item in existing_items.items():
        if chrt_id in targets_by_chrt or chrt_id in conflict_chrts:
            continue
        targets_by_chrt[chrt_id] = _PublishTarget(
            chrt_id=chrt_id,
            amount=0,
            product_id=item.product_id,
            zeroed=True,
        )

    return list(targets_by_chrt.values()), skipped_missing, conflict_chrts


async def _upsert_pending_items(
    session: AsyncSession,
    binding_id: uuid.UUID,
    targets: list[_PublishTarget],
    existing_items: dict[int, FbsStockSyncItem],
) -> dict[int, FbsStockSyncItem]:
    items: dict[int, FbsStockSyncItem] = {}
    for target in targets:
        item = existing_items.get(target.chrt_id)
        if item is None:
            item = FbsStockSyncItem(
                binding_id=binding_id,
                chrt_id=target.chrt_id,
                product_id=target.product_id,
            )
            session.add(item)
        else:
            item.product_id = target.product_id
        item.last_target_amount = target.amount
        item.status = STOCK_SYNC_STATUS_PENDING
        item.last_error_code = None
        items[target.chrt_id] = item
    await session.commit()
    return items


async def _mark_conflict_items(
    session: AsyncSession,
    binding_id: uuid.UUID,
    conflict_chrts: set[int],
    chrt_to_products: dict[int, list[uuid.UUID]],
    existing_items: dict[int, FbsStockSyncItem],
) -> None:
    for chrt_id in conflict_chrts:
        for product_id in chrt_to_products.get(chrt_id, []):
            item = existing_items.get(chrt_id)
            if item is None:
                item = FbsStockSyncItem(
                    binding_id=binding_id,
                    chrt_id=chrt_id,
                    product_id=product_id,
                )
                session.add(item)
                existing_items[chrt_id] = item
            item.status = STOCK_SYNC_STATUS_CONFLICT
            item.last_error_code = ERROR_DUPLICATE_CHRT
    if conflict_chrts:
        await session.commit()


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


async def _put_batch_with_retry(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    warehouse_id: int,
    batch: list[MarketplaceStockAmount],
    rate_limiter: StockSyncRateLimiter,
    marketplace_api_base: str | None,
) -> str | None:
    """PUT one batch; on 429 retry once after rate limiter wait. Returns error code or None."""
    retried_429 = False
    while True:
        try:
            await put_marketplace_stocks(
                http_client,
                api_token=api_token,
                warehouse_id=warehouse_id,
                stocks=batch,
                marketplace_api_base=marketplace_api_base,
            )
            return None
        except WildberriesClientError as exc:
            if exc.status_code == 429 and not retried_429:
                retried_429 = True
                await rate_limiter.wait(MAX_429_RETRY_AFTER_SECONDS)
                continue
            if exc.status_code == 409:
                return _wb_error_code(exc)
            return _wb_error_code(exc)


def _compare_readback(
    batch: list[MarketplaceStockAmount],
    readback: list[MarketplaceStockAmount],
) -> bool:
    expected = {item.chrt_id: item.amount for item in batch}
    actual = {item.chrt_id: item.amount for item in readback}
    if set(expected) != set(actual):
        return False
    return all(actual[chrt_id] == expected[chrt_id] for chrt_id in expected)


async def _publish_batches(
    session: AsyncSession,
    *,
    binding: FbsWarehouseBinding,
    targets: list[_PublishTarget],
    sync_items: dict[int, FbsStockSyncItem],
    http_client: httpx.AsyncClient,
    api_token: str,
    rate_limiter: StockSyncRateLimiter,
    marketplace_api_base: str | None,
) -> tuple[int, int]:
    """Returns (confirmed_count, error_count)."""
    if not targets:
        return 0, 0

    amounts = [
        MarketplaceStockAmount(chrt_id=t.chrt_id, amount=t.amount) for t in targets
    ]
    batches = split_marketplace_stocks_batches(amounts)
    confirmed = 0
    errors = 0

    for batch_index, batch in enumerate(batches):
        if batch_index > 0:
            await rate_limiter.wait(DEFAULT_RATE_INTERVAL_SECONDS)

        put_error = await _put_batch_with_retry(
            http_client,
            api_token=api_token,
            warehouse_id=int(binding.wb_warehouse_id),
            batch=batch,
            rate_limiter=rate_limiter,
            marketplace_api_base=marketplace_api_base,
        )
        if put_error is not None:
            for entry in batch:
                item = sync_items[entry.chrt_id]
                item.status = STOCK_SYNC_STATUS_ERROR
                item.last_error_code = put_error
            errors += len(batch)
            await session.commit()
            continue

        await rate_limiter.wait(DEFAULT_RATE_INTERVAL_SECONDS)

        chrt_ids = [entry.chrt_id for entry in batch]
        try:
            readback = await fetch_marketplace_stocks(
                http_client,
                api_token=api_token,
                warehouse_id=int(binding.wb_warehouse_id),
                chrt_ids=chrt_ids,
                marketplace_api_base=marketplace_api_base,
            )
        except WildberriesClientError as exc:
            err = _wb_error_code(exc)
            for entry in batch:
                item = sync_items[entry.chrt_id]
                item.status = STOCK_SYNC_STATUS_ERROR
                item.last_error_code = err
            errors += len(batch)
            await session.commit()
            continue

        if not _compare_readback(batch, readback):
            for entry in batch:
                item = sync_items[entry.chrt_id]
                item.status = STOCK_SYNC_STATUS_ERROR
                item.last_error_code = ERROR_READBACK_MISMATCH
            errors += len(batch)
            await session.commit()
            continue

        readback_map = {row.chrt_id: row.amount for row in readback}
        for entry in batch:
            item = sync_items[entry.chrt_id]
            item.status = STOCK_SYNC_STATUS_CONFIRMED
            item.last_confirmed_amount = readback_map[entry.chrt_id]
            item.last_error_code = None
            confirmed += 1
        await session.commit()

    return confirmed, errors


async def sync_binding_stocks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    binding: FbsWarehouseBinding,
    http_client: httpx.AsyncClient,
    *,
    rate_limiter: StockSyncRateLimiter | None = None,
    marketplace_api_base: str | None = None,
) -> FbsStockSyncResult:
    """Publish absolute FBS stock amounts for one seller WB warehouse binding."""
    limiter = rate_limiter or NoopStockSyncRateLimiter()

    if binding.tenant_id != tenant_id or binding.seller_id != seller_id:
        raise FbsStockSyncError(ERROR_BINDING_MISMATCH)

    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsStockSyncError(ERROR_SELLER_NOT_FOUND)

    if not binding.is_active or not binding.stock_sync_enabled:
        return FbsStockSyncResult()

    if not await _try_acquire_lease(session, binding):
        return FbsStockSyncResult(skipped_busy=True, error_code=ERROR_SYNC_BUSY)

    result = FbsStockSyncResult()
    try:
        try:
            api_token = await _resolve_marketplace_api_token(session, tenant_id, seller_id)
        except FbsStockSyncError as exc:
            binding.last_sync_status = STOCK_SYNC_STATUS_ERROR
            binding.last_sync_at = _utcnow()
            binding.last_error_code = exc.code
            await session.commit()
            return FbsStockSyncResult(errors=1, error_code=exc.code)

        products = await _load_seller_products(session, tenant_id, seller_id)
        product_ids = [p.id for p in products if p.wb_chrt_id is not None]
        availability = await fbs_available_qty_by_product(
            session,
            tenant_id,
            binding.wms_warehouse_id,
            product_ids,
        )
        existing_items = await _load_existing_sync_items(session, binding.id)

        targets, skipped_missing, conflict_chrts = _build_publish_plan(
            products, availability, existing_items
        )
        result.skipped_missing_chrt_id = skipped_missing

        chrt_to_product_ids: dict[int, list[uuid.UUID]] = {}
        for product in products:
            if product.wb_chrt_id is not None:
                chrt_to_product_ids.setdefault(int(product.wb_chrt_id), []).append(
                    product.id
                )
        if conflict_chrts:
            await _mark_conflict_items(
                session,
                binding.id,
                conflict_chrts,
                chrt_to_product_ids,
                existing_items,
            )
            result.conflicts = len(conflict_chrts)

        publish_targets = [t for t in targets if t.chrt_id not in conflict_chrts]
        result.products_targeted = len(publish_targets)
        result.products_zeroed = sum(1 for t in publish_targets if t.zeroed)

        sync_items = await _upsert_pending_items(
            session, binding.id, publish_targets, existing_items
        )

        confirmed, errors = await _publish_batches(
            session,
            binding=binding,
            targets=publish_targets,
            sync_items=sync_items,
            http_client=http_client,
            api_token=api_token,
            rate_limiter=limiter,
            marketplace_api_base=marketplace_api_base,
        )
        result.products_confirmed = confirmed
        result.errors = errors + result.conflicts
        result.bindings_processed = 1

        if errors > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_ERROR
            binding.last_error_code = ERROR_READBACK_MISMATCH
        elif result.conflicts > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_CONFLICT
            binding.last_error_code = ERROR_DUPLICATE_CHRT
        else:
            binding.last_sync_status = STOCK_SYNC_STATUS_CONFIRMED
            binding.last_error_code = None
        binding.last_sync_at = _utcnow()
        await session.commit()
    finally:
        await session.refresh(binding)
        binding.lease_until = None
        await session.commit()

    return result
