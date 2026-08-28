"""Reconcile WMS FBS availability with Wildberries marketplace stocks (PUT + readback)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
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
from app.services.wildberries_client import (
    MARKETPLACE_STOCKS_PATH,
    MarketplaceStockAmount,
    WildberriesClientError,
    fetch_marketplace_stocks,
    split_marketplace_stocks_batches,
)
from app.services.wildberries_credentials_service import (
    get_decrypted_marketplace_token,
    get_decrypted_tokens_for_seller,
)

logger = logging.getLogger(__name__)

# `last_sync_status` is a free-form text column on FbsWarehouseBinding (no enum/migration
# needed), so this status is defined locally rather than added to FBS_STOCK_SYNC_STATUSES,
# which enumerates per-item sync statuses, not binding-level ones.
STOCK_SYNC_STATUS_NOTHING_TO_PUBLISH = "nothing_to_publish"

SYNC_LEASE_DURATION = timedelta(minutes=5)
DEFAULT_RATE_INTERVAL_SECONDS = 0.2
MAX_429_RETRY_AFTER_SECONDS = 60.0

ERROR_DUPLICATE_CHRT = "duplicate_chrt_id"
ERROR_READBACK_MISMATCH = "readback_mismatch"
ERROR_MISSING_TOKEN = "missing_marketplace_token"
ERROR_SYNC_BUSY = "sync_busy"
ERROR_BINDING_MISMATCH = "binding_mismatch"
ERROR_SELLER_NOT_FOUND = "seller_not_found"
ERROR_UNSAFE_STOCK_UNKNOWN = "unsafe_stock_unknown"
ERROR_UNSAFE_ZERO_BLOCKED = "unsafe_zero_blocked"


class StockSyncRateLimiter(Protocol):
    async def wait(self, seconds: float = 0.0) -> None:
        """Pause between WB calls; inject no-op implementation in unit tests."""


class NoopStockSyncRateLimiter:
    """Explicit test-only limiter; production uses AsyncStockSyncRateLimiter."""

    async def wait(self, seconds: float = 0.0) -> None:
        return


class AsyncStockSyncRateLimiter:
    """Production async pacing between Wildberries stock API calls."""

    async def wait(self, seconds: float = 0.0) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


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
    is_explicit_zero: bool = False


@dataclass(frozen=True, slots=True)
class _BlockedTarget:
    chrt_id: int
    product_id: uuid.UUID | None
    error_code: str


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
    new_lease_until = now + SYNC_LEASE_DURATION
    stmt = (
        update(FbsWarehouseBinding)
        .where(
            FbsWarehouseBinding.id == binding.id,
            or_(
                FbsWarehouseBinding.lease_until.is_(None),
                FbsWarehouseBinding.lease_until <= now,
            ),
        )
        .values(lease_until=new_lease_until)
        .returning(FbsWarehouseBinding.id)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    if result.first() is None:
        return False
    binding.lease_until = new_lease_until
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
        Product.fbs_stock_sync_enabled.is_(True),
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


async def _load_pool_quantities(
    session: AsyncSession,
    binding_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """Ручное распределение пула FBS по этой привязке — источник истины, синк только читает."""
    stmt = select(FbsBindingStockPool.product_id, FbsBindingStockPool.quantity).where(
        FbsBindingStockPool.binding_id == binding_id
    )
    res = await session.execute(stmt)
    return {row.product_id: row.quantity for row in res.all()}


async def _resolve_publish_quantities(
    session: AsyncSession,
    binding: FbsWarehouseBinding,
    products: list[Product],
) -> dict[uuid.UUID, int]:
    """Источник числа для публикации: доля свободного остатка, со страховкой.

    Сам механизм отправки не переписан — он как был событийным, так и остался.
    Поменялось только то, откуда берётся число: у товара с настроенной долей оно
    считается от свободного остатка на этот момент, а не берётся из сохранённого
    распределения.

    Товары без доли продолжают публиковаться по-старому, поэтому выкатка не
    требует, чтобы правило успели настроить всем сразу. И если новая ветка расчёта
    упадёт, публикация не прекращается молча: WB иначе продолжил бы продавать по
    последнему числу, которое у него осталось.
    """
    stored = await _load_pool_quantities(session, binding.id)
    try:
        from app.services.fbs_stock_rule_service import publish_amounts_for_binding

        by_rule = await publish_amounts_for_binding(session, binding, products)
    except Exception:
        logger.exception(
            "fbs stock rule failed for binding %s, falling back to stored pool quantities",
            binding.id,
        )
        return stored
    stored.update(by_rule)
    return stored


def _build_publish_plan(
    products: list[Product],
    pool_quantities: dict[uuid.UUID, int],
    existing_items: dict[int, FbsStockSyncItem],
    product_block_errors: dict[uuid.UUID, str] | None = None,
) -> tuple[list[_PublishTarget], list[_BlockedTarget], list[uuid.UUID], set[int]]:
    """Return safe publish targets, blocked targets, missing chrt ids, and conflicts.

    Pool quantities are read from fbs_binding_stock_pools for this binding.
    If a product is not in the pool, it is not blocked — simply skipped.
    """
    skipped_missing: list[uuid.UUID] = []
    block_errors = product_block_errors or {}
    chrt_to_products: dict[int, list[Product]] = {}
    for product in products:
        if product.wb_chrt_id is None:
            skipped_missing.append(product.id)
            continue
        chrt_to_products.setdefault(int(product.wb_chrt_id), []).append(product)

    conflict_chrts = {chrt for chrt, group in chrt_to_products.items() if len(group) > 1}

    targets_by_chrt: dict[int, _PublishTarget] = {}
    blocked_targets: list[_BlockedTarget] = []
    for chrt_id, group in chrt_to_products.items():
        if chrt_id in conflict_chrts:
            continue
        product = group[0]
        blocked_error = block_errors.get(product.id)
        if blocked_error is not None:
            blocked_targets.append(
                _BlockedTarget(
                    chrt_id=chrt_id,
                    product_id=product.id,
                    error_code=blocked_error,
                )
            )
            continue
        if product.id not in pool_quantities:
            # Нет строки распределения в fbs_binding_stock_pools для этой привязки —
            # это НЕ ошибка, просто админ ещё не выделил количество на этот склад.
            # Товар просто не попадает в targets, никакого blocked_targets/error_code.
            continue
        amount = int(pool_quantities[product.id])
        amount = max(amount, 0)
        # Строка в fbs_binding_stock_pools пишется только через
        # fbs_warehouse_binding_service.set_binding_stock_pool_quantity — само её наличие
        # доказывает осознанное действие администратора, включая amount == 0.
        targets_by_chrt[chrt_id] = _PublishTarget(
            chrt_id=chrt_id,
            amount=amount,
            product_id=product.id,
            is_explicit_zero=(amount == 0),
        )

    _ = existing_items
    return list(targets_by_chrt.values()), blocked_targets, skipped_missing, conflict_chrts


async def _upsert_pending_items(
    session: AsyncSession,
    binding_id: uuid.UUID,
    targets: list[_PublishTarget],
    existing_items: dict[int, FbsStockSyncItem],
) -> dict[int, FbsStockSyncItem]:
    def apply_targets(
        current_items: dict[int, FbsStockSyncItem],
    ) -> dict[int, FbsStockSyncItem]:
        items: dict[int, FbsStockSyncItem] = {}
        for target in targets:
            item = current_items.get(target.chrt_id)
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
        return items

    items = apply_targets(existing_items)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing_items = await _load_existing_sync_items(session, binding_id)
        items = apply_targets(existing_items)
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


async def _mark_blocked_items(
    session: AsyncSession,
    binding_id: uuid.UUID,
    blocked_targets: list[_BlockedTarget],
    existing_items: dict[int, FbsStockSyncItem],
) -> None:
    for target in blocked_targets:
        item = existing_items.get(target.chrt_id)
        if item is None:
            item = FbsStockSyncItem(
                binding_id=binding_id,
                chrt_id=target.chrt_id,
                product_id=target.product_id,
            )
            session.add(item)
            existing_items[target.chrt_id] = item
        else:
            item.product_id = target.product_id
        item.status = STOCK_SYNC_STATUS_ERROR
        item.last_error_code = target.error_code
        item.last_target_amount = None
    if blocked_targets:
        await session.commit()


def _wb_error_code(exc: WildberriesClientError) -> str:
    suffix = f"_{exc.status_code}" if exc.status_code else ""
    return f"wb_{exc.code}{suffix}"


def _marketplace_stocks_url(
    *,
    warehouse_id: int,
    marketplace_api_base: str | None,
) -> str:
    base = (marketplace_api_base or settings.wildberries_marketplace_api_base).rstrip("/")
    return f"{base}{MARKETPLACE_STOCKS_PATH.format(warehouse_id=warehouse_id)}"


def _parse_retry_after_seconds(header_value: str | None) -> float:
    if header_value is None or header_value.strip() == "":
        return DEFAULT_RATE_INTERVAL_SECONDS
    try:
        parsed = float(header_value)
    except ValueError:
        return MAX_429_RETRY_AFTER_SECONDS
    return min(max(parsed, 0.0), MAX_429_RETRY_AFTER_SECONDS)


@dataclass(frozen=True, slots=True)
class _PutBatchOutcome:
    error_code: str | None
    status_code: int | None
    retry_after_seconds: float | None


async def _put_stocks_batch(
    http_client: httpx.AsyncClient,
    *,
    api_token: str,
    warehouse_id: int,
    batch: list[MarketplaceStockAmount],
    marketplace_api_base: str | None,
) -> _PutBatchOutcome:
    url = _marketplace_stocks_url(
        warehouse_id=warehouse_id,
        marketplace_api_base=marketplace_api_base,
    )
    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json",
    }
    payload = {
        "stocks": [{"chrtId": item.chrt_id, "amount": item.amount} for item in batch],
    }
    try:
        response = await http_client.put(url, headers=headers, json=payload, timeout=60.0)
    except httpx.HTTPError:
        return _PutBatchOutcome(
            error_code=_wb_error_code(WildberriesClientError("transport_error")),
            status_code=None,
            retry_after_seconds=None,
        )
    if response.status_code >= 400:
        retry_after: float | None = None
        if response.status_code == 429:
            retry_after = _parse_retry_after_seconds(response.headers.get("Retry-After"))
        return _PutBatchOutcome(
            error_code=_wb_error_code(
                WildberriesClientError(
                    "upstream_error",
                    status_code=response.status_code,
                )
            ),
            status_code=response.status_code,
            retry_after_seconds=retry_after,
        )
    return _PutBatchOutcome(error_code=None, status_code=None, retry_after_seconds=None)


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
        outcome = await _put_stocks_batch(
            http_client,
            api_token=api_token,
            warehouse_id=warehouse_id,
            batch=batch,
            marketplace_api_base=marketplace_api_base,
        )
        if outcome.error_code is None:
            return None
        if outcome.status_code == 429 and not retried_429:
            retried_429 = True
            wait_seconds = outcome.retry_after_seconds or DEFAULT_RATE_INTERVAL_SECONDS
            await rate_limiter.wait(wait_seconds)
            continue
        return outcome.error_code


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
) -> tuple[int, int, str | None]:
    """Returns (confirmed_count, error_count, first_error_code)."""
    if not targets:
        return 0, 0, None

    amounts = [MarketplaceStockAmount(chrt_id=t.chrt_id, amount=t.amount) for t in targets]
    batches = split_marketplace_stocks_batches(amounts)
    confirmed = 0
    errors = 0
    first_error_code: str | None = None

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
            if first_error_code is None:
                first_error_code = put_error
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
            if first_error_code is None:
                first_error_code = err
            for entry in batch:
                item = sync_items[entry.chrt_id]
                item.status = STOCK_SYNC_STATUS_ERROR
                item.last_error_code = err
            errors += len(batch)
            await session.commit()
            continue

        if not _compare_readback(batch, readback):
            if first_error_code is None:
                first_error_code = ERROR_READBACK_MISMATCH
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

    return confirmed, errors, first_error_code


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
    limiter = rate_limiter or AsyncStockSyncRateLimiter()
    binding_id = binding.id

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
        pool_quantities = await _resolve_publish_quantities(session, binding, products)
        product_block_errors: dict[uuid.UUID, str] = {}
        existing_items = await _load_existing_sync_items(session, binding.id)

        targets, blocked_targets, skipped_missing, conflict_chrts = _build_publish_plan(
            products, pool_quantities, existing_items, product_block_errors
        )

        # Zero guard: protect against zero amount without is_explicit_zero flag
        # (should not happen with current code, but defends against future regressions)
        safe_targets: list[_PublishTarget] = []
        zero_guard_blocked: list[_BlockedTarget] = []
        for t in targets:
            if t.amount == 0 and not t.is_explicit_zero:
                zero_guard_blocked.append(
                    _BlockedTarget(
                        chrt_id=t.chrt_id,
                        product_id=t.product_id,
                        error_code=ERROR_UNSAFE_ZERO_BLOCKED,
                    )
                )
                continue
            safe_targets.append(t)
        targets = safe_targets
        if zero_guard_blocked:
            blocked_targets = blocked_targets + zero_guard_blocked

        result.skipped_missing_chrt_id = skipped_missing

        chrt_to_product_ids: dict[int, list[uuid.UUID]] = {}
        for product in products:
            if product.wb_chrt_id is not None:
                chrt_to_product_ids.setdefault(int(product.wb_chrt_id), []).append(product.id)
        if conflict_chrts:
            await _mark_conflict_items(
                session,
                binding.id,
                conflict_chrts,
                chrt_to_product_ids,
                existing_items,
            )
            result.conflicts = len(conflict_chrts)
        if blocked_targets:
            await _mark_blocked_items(session, binding.id, blocked_targets, existing_items)

        publish_targets = [t for t in targets if t.chrt_id not in conflict_chrts]
        result.products_targeted = len(publish_targets)
        result.products_zeroed = 0

        sync_items = await _upsert_pending_items(
            session, binding.id, publish_targets, existing_items
        )

        confirmed, errors, publish_error_code = await _publish_batches(
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
        blocked_error_count = len(blocked_targets)
        result.errors = errors + result.conflicts + blocked_error_count
        result.bindings_processed = 1

        if errors > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_ERROR
            binding.last_error_code = publish_error_code
        elif blocked_error_count > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_ERROR
            binding.last_error_code = blocked_targets[0].error_code
        elif result.conflicts > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_CONFLICT
            binding.last_error_code = ERROR_DUPLICATE_CHRT
        elif not publish_targets:
            # Nothing was actually sent to Wildberries (e.g. no distribution set for this
            # binding yet) — do not report "confirmed", it would be misleading.
            binding.last_sync_status = STOCK_SYNC_STATUS_NOTHING_TO_PUBLISH
            binding.last_error_code = None
        else:
            binding.last_sync_status = STOCK_SYNC_STATUS_CONFIRMED
            binding.last_error_code = None
        binding.last_sync_at = _utcnow()
        await session.commit()
    finally:
        transaction = session.get_transaction()
        if transaction is not None:
            await session.rollback()
        await session.execute(
            update(FbsWarehouseBinding)
            .where(FbsWarehouseBinding.id == binding_id)
            .values(lease_until=None)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
        binding.lease_until = None

    return result


async def publish_explicit_zero_for_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    binding: FbsWarehouseBinding,
    http_client: httpx.AsyncClient,
    *,
    rate_limiter: StockSyncRateLimiter | None = None,
    marketplace_api_base: str | None = None,
) -> FbsStockSyncResult:
    """Explicitly publish zero for every chrt_id currently tracked on this binding.

    Called once when stock_sync_enabled is switched from True to False (operator
    deliberately turns publication off) — WB must not keep selling against a stale
    positive number forever. This is a DELIBERATE zero (operator action), not the
    "unsafe zero" the regular sync path protects against, so it bypasses the
    stock_sync_enabled early-return in sync_binding_stocks entirely.
    """
    limiter = rate_limiter or AsyncStockSyncRateLimiter()
    binding_id = binding.id

    if binding.tenant_id != tenant_id or binding.seller_id != seller_id:
        raise FbsStockSyncError(ERROR_BINDING_MISMATCH)
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsStockSyncError(ERROR_SELLER_NOT_FOUND)

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

        existing_items = await _load_existing_sync_items(session, binding.id)
        if not existing_items:
            result.bindings_processed = 1
            return result

        targets = [
            _PublishTarget(
                chrt_id=chrt_id,
                amount=0,
                product_id=item.product_id,
                is_explicit_zero=True,
            )
            for chrt_id, item in existing_items.items()
        ]

        # Mark pending immediately so the screen shows "not yet confirmed" while
        # the WB round-trip is in flight.
        for item in existing_items.values():
            item.last_target_amount = 0
            item.status = STOCK_SYNC_STATUS_PENDING
            item.last_error_code = None
        await session.commit()

        confirmed, errors, publish_error_code = await _publish_batches(
            session,
            binding=binding,
            targets=targets,
            sync_items=existing_items,
            http_client=http_client,
            api_token=api_token,
            rate_limiter=limiter,
            marketplace_api_base=marketplace_api_base,
        )

        result.bindings_processed = 1
        result.products_targeted = len(targets)
        result.products_confirmed = confirmed
        result.products_zeroed = confirmed
        result.errors = errors

        if errors > 0:
            binding.last_sync_status = STOCK_SYNC_STATUS_ERROR
            binding.last_error_code = publish_error_code
        else:
            binding.last_sync_status = STOCK_SYNC_STATUS_CONFIRMED
            binding.last_error_code = None
        binding.last_sync_at = _utcnow()
        await session.commit()
    finally:
        transaction = session.get_transaction()
        if transaction is not None:
            await session.rollback()
        await session.execute(
            update(FbsWarehouseBinding)
            .where(FbsWarehouseBinding.id == binding_id)
            .values(lease_until=None)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
        binding.lease_until = None

    return result


_ZERO_PUBLISH_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


async def _run_explicit_zero_publish_fresh_session(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> None:
    """Runs publish_explicit_zero_for_binding in its own session/http client — safe to
    fire after the caller's request-scoped session has already closed."""
    from app.db.session import SessionLocal

    try:
        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            binding = await session.get(FbsWarehouseBinding, binding_id)
            if binding is None:
                return
            await publish_explicit_zero_for_binding(
                session, tenant_id, seller_id, binding, http_client
            )
    except Exception:
        logger.exception(
            "explicit zero publish failed for binding %s (seller %s, tenant %s)",
            binding_id,
            seller_id,
            tenant_id,
        )


def schedule_explicit_zero_publish(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> None:
    """Fire-and-forget explicit zero publish for one binding (operator turned the
    stock-sync toggle off). Runs on the current running event loop — safe to call from
    inside a FastAPI request handler, since the ASGI server process keeps that loop
    alive after the response is sent."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "explicit zero publish skipped for binding %s: no running event loop",
            binding_id,
        )
        return
    task = loop.create_task(
        _run_explicit_zero_publish_fresh_session(tenant_id, seller_id, binding_id)
    )
    _ZERO_PUBLISH_BACKGROUND_TASKS.add(task)
    task.add_done_callback(_ZERO_PUBLISH_BACKGROUND_TASKS.discard)


async def drain_zero_publish_background_tasks() -> None:
    """Wait for in-process explicit-zero-publish tasks — call from test teardown so
    assertions don't race a fire-and-forget task still in flight."""
    while _ZERO_PUBLISH_BACKGROUND_TASKS:
        tasks = tuple(_ZERO_PUBLISH_BACKGROUND_TASKS)
        await asyncio.gather(*tasks, return_exceptions=True)
