"""Periodic FBS order polling for all sellers with a marketplace WB token."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.marketplace_account import MarketplaceAccount
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.warehouse import Warehouse
from app.services.fbs_cancellation_service import FbsCancellationError, sync_seller_order_statuses
from app.services.fbs_stock_sync_service import FbsStockSyncError, sync_binding_stocks
from app.services.fbs_tracking_service import FbsTrackingError, sync_in_delivery_supplies
from app.services.fbs_warehouse_binding_service import is_auto_fbs_wms_warehouse
from app.services.marketplace_provider import (
    MarketplaceBackoff,
    MarketplaceProviderError,
    provider_error_message,
)
from app.services.marketplace_seller_lock_service import marketplace_seller_lock
from app.services.wb_marketplace_orders_service import (
    WbMarketplaceOrdersError,
    sync_seller_orders,
)

logger = logging.getLogger(__name__)
_MARKETPLACE_BACKOFF = MarketplaceBackoff()


@dataclass(frozen=True)
class SellerPollTarget:
    tenant_id: uuid.UUID
    seller_id: uuid.UUID
    marketplace: str = "wb"


@dataclass(frozen=True)
class FbsAutopollCycleResult:
    sellers_polled: int
    orders_upserted: int
    orders_created: int
    statuses_updated: int
    seller_errors: int
    stocks_bindings_processed: int = 0
    stock_errors: int = 0
    marketplace_breakdown: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class SellerStockSyncResult:
    bindings_processed: int = 0
    products_targeted: int = 0
    products_confirmed: int = 0
    products_zeroed: int = 0
    conflicts: int = 0
    errors: int = 0
    binding_errors: int = 0


def _marketplace_bucket(
    breakdown: dict[str, dict[str, int]],
    marketplace: str,
) -> dict[str, int]:
    return breakdown.setdefault(
        marketplace,
        {
            "pairs": 0,
            "successful_pairs": 0,
            "orders_upserted": 0,
            "orders_created": 0,
            "statuses_updated": 0,
            "bindings_processed": 0,
            "errors": 0,
            "backoff_skips": 0,
        },
    )


def _record_provider_backoff(error: MarketplaceProviderError) -> None:
    if error.status_code != 429:
        return
    retry_after = error.payload.get("retry_after_seconds", 60)
    delay = float(retry_after) if isinstance(retry_after, (int, float)) else 60.0
    _MARKETPLACE_BACKOFF.record_rate_limit(
        error.marketplace,
        retry_after_seconds=delay,
    )


async def list_sellers_with_marketplace_token(
    session: AsyncSession,
) -> list[SellerPollTarget]:
    stmt = (
        select(Seller.tenant_id, Seller.id)
        .join(
            SellerWildberriesCredentials,
            SellerWildberriesCredentials.seller_id == Seller.id,
        )
        .where(
            or_(
                SellerWildberriesCredentials.marketplace_token_encrypted.isnot(None),
                SellerWildberriesCredentials.content_token_encrypted.isnot(None),
            )
        )
        .order_by(Seller.tenant_id, Seller.id)
    )
    rows = (await session.execute(stmt)).all()
    return [SellerPollTarget(tenant_id=row[0], seller_id=row[1]) for row in rows]


async def list_marketplace_poll_targets(
    session: AsyncSession,
) -> list[SellerPollTarget]:
    """Return active seller/provider pairs; one provider never owns another's cycle."""
    targets = await list_sellers_with_marketplace_token(session)
    ozon_stmt = (
        select(
            MarketplaceAccount.tenant_id,
            MarketplaceAccount.seller_id,
            MarketplaceAccount.marketplace,
        )
        .where(
            MarketplaceAccount.marketplace == "ozon",
            MarketplaceAccount.is_active.is_(True),
            MarketplaceAccount.external_account_id.isnot(None),
            MarketplaceAccount.secret_encrypted.isnot(None),
        )
        .order_by(
            MarketplaceAccount.tenant_id,
            MarketplaceAccount.seller_id,
            MarketplaceAccount.marketplace,
        )
    )
    targets.extend(
        SellerPollTarget(tenant_id=row[0], seller_id=row[1], marketplace=row[2])
        for row in (await session.execute(ozon_stmt)).all()
    )
    return sorted(
        targets,
        key=lambda target: (str(target.tenant_id), str(target.seller_id), target.marketplace),
    )


async def list_active_stock_sync_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    wb_warehouse_id: int | None = None,
) -> list[FbsWarehouseBinding]:
    stmt = (
        select(FbsWarehouseBinding, Warehouse)
        .join(Warehouse, Warehouse.id == FbsWarehouseBinding.wms_warehouse_id)
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.is_active.is_(True),
            FbsWarehouseBinding.stock_sync_enabled.is_(True),
            Warehouse.tenant_id == tenant_id,
        )
        .order_by(FbsWarehouseBinding.wb_warehouse_id.asc())
    )
    if wb_warehouse_id is not None:
        stmt = stmt.where(FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id)
    rows = list((await session.execute(stmt)).all())
    return [binding for binding, warehouse in rows if not is_auto_fbs_wms_warehouse(warehouse)]


async def sync_seller_stocks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    *,
    wb_warehouse_id: int | None = None,
) -> SellerStockSyncResult:
    """Run stock reconciliation for all active+enabled bindings of one seller."""
    bindings = await list_active_stock_sync_bindings(
        session,
        tenant_id,
        seller_id,
        wb_warehouse_id=wb_warehouse_id,
    )
    result = SellerStockSyncResult()
    for binding in bindings:
        binding_id = binding.id
        binding_wb_warehouse_id = binding.wb_warehouse_id
        try:
            binding_result = await sync_binding_stocks(
                session,
                tenant_id,
                seller_id,
                binding,
                http_client,
            )
            if binding_result.skipped_busy:
                logger.warning(
                    "fbs stock sync skipped busy binding %s seller %s wb_warehouse %s",
                    binding_id,
                    seller_id,
                    binding_wb_warehouse_id,
                )
                continue
            result.bindings_processed += binding_result.bindings_processed
            result.products_targeted += binding_result.products_targeted
            result.products_confirmed += binding_result.products_confirmed
            result.products_zeroed += binding_result.products_zeroed
            result.conflicts += binding_result.conflicts
            result.errors += binding_result.errors
            if binding_result.errors or binding_result.error_code:
                result.binding_errors += 1
        except FbsStockSyncError as exc:
            result.binding_errors += 1
            logger.warning(
                "fbs stock sync binding failed seller %s wb_warehouse %s: %s",
                seller_id,
                binding_wb_warehouse_id,
                exc.code,
            )
        except Exception:
            result.binding_errors += 1
            logger.exception(
                "fbs stock sync binding failed seller %s wb_warehouse %s",
                seller_id,
                binding_wb_warehouse_id,
            )
    return result


async def get_binding_stock_sync_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
) -> tuple[FbsWarehouseBinding, list[FbsStockSyncItem]]:
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
    )
    binding = (await session.execute(stmt)).scalar_one_or_none()
    if binding is None:
        raise FbsStockSyncError("binding_not_found")
    items_stmt = (
        select(FbsStockSyncItem)
        .where(FbsStockSyncItem.binding_id == binding.id)
        .order_by(FbsStockSyncItem.chrt_id.asc())
    )
    items = list((await session.execute(items_stmt)).scalars().all())
    return binding, items


async def poll_fbs_orders_for_seller(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
    *,
    sync_stocks_after_orders: bool = False,
    include_history: bool = False,
) -> dict[str, int]:
    result = await sync_seller_orders(
        session,
        target.tenant_id,
        target.seller_id,
        http_client,
        include_history=include_history,
    )
    stock_result = SellerStockSyncResult()
    if sync_stocks_after_orders:
        stock_result = await sync_seller_stocks(
            session,
            target.tenant_id,
            target.seller_id,
            http_client,
        )
    return {
        "orders_upserted": int(result.get("orders_upserted", 0)),
        "orders_created": int(result.get("orders_created", 0)),
        "statuses_updated": int(result.get("statuses_updated", 0)),
        "stocks_bindings_processed": stock_result.bindings_processed,
        "stock_errors": stock_result.errors + stock_result.binding_errors,
    }


async def poll_marketplace_orders_for_target(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
    *,
    include_history: bool = False,
) -> dict[str, int]:
    if target.marketplace == "wb":
        return await poll_fbs_orders_for_seller(
            session,
            target,
            http_client,
            include_history=include_history,
        )
    # Live Ozon traffic is intentionally disabled while the account returns 403/code 7.
    # The Ozon lane injects the fake transport into this boundary for contract/e2e runs.
    raise MarketplaceProviderError("ozon", 403, {"code": 7})


MARKING_SYNC_BATCH_SIZE = 100


async def sync_marking_statuses_for_assembling_supplies(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> int:
    from app.services.fbs_marking_service import (
        FbsMarkingError,
        _notify_supply_marking_update,
        _sync_order_meta_from_wb,
        list_order_markings,
        require_marketplace_token,
    )
    from app.services.wildberries_errors import WildberriesClientError
    from app.services.wildberries_fbs_client import fetch_marketplace_orders_meta_batch

    stmt = (
        select(FbsOrder)
        .join(FbsSupply, FbsOrder.supply_id == FbsSupply.id)
        .where(
            FbsOrder.tenant_id == target.tenant_id,
            FbsOrder.seller_id == target.seller_id,
            FbsSupply.status == FBS_SUPPLY_STATUS_ASSEMBLING,
        )
        .order_by(FbsOrder.created_at_wb.asc(), FbsOrder.id.asc())
    )
    orders = list((await session.execute(stmt)).scalars().all())
    if not orders:
        return 0
    token = await require_marketplace_token(session, target.tenant_id, target.seller_id)
    synced = 0
    unique_wb_order_ids = list(dict.fromkeys(int(order.wb_order_id) for order in orders))
    for start in range(0, len(unique_wb_order_ids), MARKING_SYNC_BATCH_SIZE):
        wb_order_ids = unique_wb_order_ids[start : start + MARKING_SYNC_BATCH_SIZE]
        try:
            meta_batch = await fetch_marketplace_orders_meta_batch(
                http_client, api_token=token, order_ids=wb_order_ids
            )
        except (FbsMarkingError, WildberriesClientError) as exc:
            logger.warning(
                "fbs autopoll marking batch skipped (%s orders): %s", len(wb_order_ids), exc
            )
            continue
        rows_by_wb_order_id = {row.order_id: [row] for row in meta_batch}
        for order in orders:
            if int(order.wb_order_id) not in wb_order_ids:
                continue
            if not await list_order_markings(session, target.tenant_id, order.id):
                continue
            returned_rows = rows_by_wb_order_id.get(int(order.wb_order_id), [])
            try:
                await _sync_order_meta_from_wb(
                    session, order, http_client, token,
                    meta_batch=returned_rows,
                )
                # A partial WB batch must clear a stale positive verdict, but it
                # must not look like a successful local sync: there is no fresh
                # timestamp, derived packaging update, or success counter.
                if not returned_rows:
                    logger.warning("fbs autopoll marking response missed order %s", order.id)
                    continue
                await _notify_supply_marking_update(session, target.tenant_id, order.id)
                synced += 1
            except (FbsMarkingError, WildberriesClientError) as exc:
                logger.warning("fbs autopoll marking sync skipped order %s: %s", order.id, exc)
    return synced


async def sync_fbs_order_statuses_for_seller(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> int:
    updated = await sync_seller_order_statuses(
        session,
        target.tenant_id,
        target.seller_id,
        http_client,
    )
    await sync_marking_statuses_for_assembling_supplies(session, target, http_client)
    try:
        await sync_in_delivery_supplies(
            session,
            target.tenant_id,
            target.seller_id,
            http_client,
        )
    except FbsTrackingError as exc:
        logger.warning(
            "fbs autopoll tracking sync skipped seller %s: %s",
            target.seller_id,
            exc.code,
        )
    return updated


async def sync_marketplace_order_statuses_for_target(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> int:
    if target.marketplace == "wb":
        return await sync_fbs_order_statuses_for_seller(session, target, http_client)
    raise MarketplaceProviderError("ozon", 403, {"code": 7})


async def sync_marketplace_stocks_for_target(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> SellerStockSyncResult:
    if target.marketplace == "wb":
        return await sync_seller_stocks(
            session,
            target.tenant_id,
            target.seller_id,
            http_client,
        )
    raise MarketplaceProviderError("ozon", 403, {"code": 7})


async def poll_fbs_orders_all_sellers(
    *, include_history: bool = False
) -> FbsAutopollCycleResult:
    async with SessionLocal() as session:
        targets = await list_marketplace_poll_targets(session)

    sellers_polled = 0
    orders_upserted = 0
    orders_created = 0
    statuses_updated = 0
    seller_errors = 0
    stocks_bindings_processed = 0
    stock_errors = 0
    marketplace_breakdown: dict[str, dict[str, int]] = {}

    logger.info("fbs autopoll orders: starting cycle for %s seller/provider pairs", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            bucket = _marketplace_bucket(marketplace_breakdown, target.marketplace)
            bucket["pairs"] += 1
            if _MARKETPLACE_BACKOFF.remaining_seconds(target.marketplace) > 0:
                bucket["backoff_skips"] += 1
                logger.info(
                    "fbs autopoll orders skipped provider backoff marketplace %s",
                    target.marketplace,
                )
                continue
            try:
                async with (
                    SessionLocal() as session,
                    marketplace_seller_lock(
                        session,
                        target.seller_id,
                        target.marketplace,
                    ) as provider_lock_acquired,
                ):
                    if not provider_lock_acquired:
                        logger.info(
                            "fbs autopoll orders skipped busy seller %s marketplace %s",
                            target.seller_id,
                            target.marketplace,
                        )
                        continue
                    stats = await poll_marketplace_orders_for_target(
                        session,
                        target,
                        http_client,
                        include_history=include_history,
                    )
            except MarketplaceProviderError as exc:
                _record_provider_backoff(exc)
                seller_errors += 1
                bucket["errors"] += 1
                log = logger.warning if exc.is_account_blocked else logger.error
                log(
                    "fbs autopoll orders failed for seller %s marketplace %s "
                    "(tenant %s): %s",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                    provider_error_message(exc),
                )
                continue
            except WbMarketplaceOrdersError as exc:
                seller_errors += 1
                bucket["errors"] += 1
                logger.error(
                    "fbs autopoll orders failed for seller %s marketplace %s "
                    "(tenant %s): %s",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                    exc.code,
                )
                continue
            except Exception:
                seller_errors += 1
                bucket["errors"] += 1
                logger.exception(
                    "fbs autopoll orders failed for seller %s marketplace %s (tenant %s)",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            bucket["successful_pairs"] += 1
            orders_upserted += stats["orders_upserted"]
            orders_created += stats["orders_created"]
            statuses_updated += stats["statuses_updated"]
            stocks_bindings_processed += stats["stocks_bindings_processed"]
            stock_errors += stats["stock_errors"]
            bucket["orders_upserted"] += stats["orders_upserted"]
            bucket["orders_created"] += stats["orders_created"]
            bucket["statuses_updated"] += stats["statuses_updated"]
            bucket["bindings_processed"] += stats["stocks_bindings_processed"]

    logger.info(
        "fbs autopoll orders done: sellers=%s upserted=%s created=%s statuses=%s "
        "stocks_bindings=%s stock_errors=%s errors=%s marketplace=%s",
        sellers_polled,
        orders_upserted,
        orders_created,
        statuses_updated,
        stocks_bindings_processed,
        stock_errors,
        seller_errors,
        marketplace_breakdown,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=orders_upserted,
        orders_created=orders_created,
        statuses_updated=statuses_updated,
        seller_errors=seller_errors,
        stocks_bindings_processed=stocks_bindings_processed,
        stock_errors=stock_errors,
        marketplace_breakdown=marketplace_breakdown,
    )


async def reconcile_fbs_orders_all_sellers() -> FbsAutopollCycleResult:
    """Rare full-history reconciliation; frequent polling reads only new orders."""
    return await poll_fbs_orders_all_sellers(include_history=True)


async def sync_fbs_order_statuses_all_sellers() -> FbsAutopollCycleResult:
    async with SessionLocal() as session:
        targets = await list_marketplace_poll_targets(session)

    sellers_polled = 0
    statuses_updated = 0
    seller_errors = 0
    marketplace_breakdown: dict[str, dict[str, int]] = {}

    logger.info("fbs autopoll statuses: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            bucket = _marketplace_bucket(marketplace_breakdown, target.marketplace)
            bucket["pairs"] += 1
            if _MARKETPLACE_BACKOFF.remaining_seconds(target.marketplace) > 0:
                bucket["backoff_skips"] += 1
                continue
            try:
                async with (
                    SessionLocal() as session,
                    marketplace_seller_lock(
                        session,
                        target.seller_id,
                        target.marketplace,
                    ) as provider_lock_acquired,
                ):
                    if not provider_lock_acquired:
                        logger.info(
                            "fbs autopoll statuses skipped busy seller %s marketplace %s",
                            target.seller_id,
                            target.marketplace,
                        )
                        continue
                    updated = await sync_marketplace_order_statuses_for_target(
                        session, target, http_client
                    )
                    await session.commit()
            except MarketplaceProviderError as exc:
                _record_provider_backoff(exc)
                seller_errors += 1
                bucket["errors"] += 1
                log = logger.warning if exc.is_account_blocked else logger.error
                log(
                    "fbs autopoll statuses failed for seller %s marketplace %s "
                    "(tenant %s): %s",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                    provider_error_message(exc),
                )
                continue
            except (WbMarketplaceOrdersError, FbsCancellationError) as exc:
                seller_errors += 1
                bucket["errors"] += 1
                logger.error(
                    "fbs autopoll statuses failed for seller %s marketplace %s "
                    "(tenant %s): %s",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                    exc.code,
                )
                continue
            except Exception:
                seller_errors += 1
                bucket["errors"] += 1
                logger.exception(
                    "fbs autopoll statuses failed for seller %s (tenant %s)",
                    target.seller_id,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            statuses_updated += updated
            bucket["successful_pairs"] += 1
            bucket["statuses_updated"] += updated

    logger.info(
        "fbs autopoll statuses done: sellers=%s statuses=%s errors=%s marketplace=%s",
        sellers_polled,
        statuses_updated,
        seller_errors,
        marketplace_breakdown,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=0,
        orders_created=0,
        statuses_updated=statuses_updated,
        seller_errors=seller_errors,
        marketplace_breakdown=marketplace_breakdown,
    )


async def reconcile_fbs_stocks_all_sellers() -> FbsAutopollCycleResult:
    """Safety net: republish FBS availability for every seller, movement events or not.

    Publication is normally event-driven (see `fbs_stock_publish_service`), but an event
    can be lost — a worker restart, a failed WB call, a movement written outside the
    usual services. Without this sweep the cabinet would keep selling a stale number,
    so the cost of a periodic full pass is worth paying.
    """
    async with SessionLocal() as session:
        targets = await list_marketplace_poll_targets(session)

    sellers_polled = 0
    bindings_processed = 0
    seller_errors = 0
    stock_errors = 0
    marketplace_breakdown: dict[str, dict[str, int]] = {}

    logger.info("fbs stock reconcile: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            bucket = _marketplace_bucket(marketplace_breakdown, target.marketplace)
            bucket["pairs"] += 1
            if _MARKETPLACE_BACKOFF.remaining_seconds(target.marketplace) > 0:
                bucket["backoff_skips"] += 1
                continue
            try:
                async with (
                    SessionLocal() as session,
                    marketplace_seller_lock(
                        session,
                        target.seller_id,
                        target.marketplace,
                    ) as provider_lock_acquired,
                ):
                    if not provider_lock_acquired:
                        logger.info(
                            "fbs stock reconcile skipped busy seller %s marketplace %s",
                            target.seller_id,
                            target.marketplace,
                        )
                        continue
                    result = await sync_marketplace_stocks_for_target(
                        session,
                        target,
                        http_client,
                    )
                    await session.commit()
            except MarketplaceProviderError as exc:
                _record_provider_backoff(exc)
                seller_errors += 1
                bucket["errors"] += 1
                log = logger.warning if exc.is_account_blocked else logger.error
                log(
                    "fbs stock reconcile failed for seller %s marketplace %s "
                    "(tenant %s): %s",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                    provider_error_message(exc),
                )
                continue
            except Exception:
                seller_errors += 1
                bucket["errors"] += 1
                logger.exception(
                    "fbs stock reconcile failed for seller %s marketplace %s "
                    "(tenant %s)",
                    target.seller_id,
                    target.marketplace,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            bindings_processed += result.bindings_processed
            stock_errors += result.binding_errors
            bucket["successful_pairs"] += 1
            bucket["bindings_processed"] += result.bindings_processed
            bucket["errors"] += result.binding_errors

    logger.info(
        "fbs stock reconcile done: sellers=%s bindings=%s stock_errors=%s "
        "errors=%s marketplace=%s",
        sellers_polled,
        bindings_processed,
        stock_errors,
        seller_errors,
        marketplace_breakdown,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=0,
        orders_created=0,
        statuses_updated=0,
        seller_errors=seller_errors,
        stocks_bindings_processed=bindings_processed,
        stock_errors=stock_errors,
        marketplace_breakdown=marketplace_breakdown,
    )
