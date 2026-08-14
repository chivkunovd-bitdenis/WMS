"""Periodic FBS order polling for all sellers with a marketplace WB token."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.fbs_cancellation_service import FbsCancellationError, sync_seller_order_statuses
from app.services.fbs_stock_sync_service import FbsStockSyncError, sync_binding_stocks
from app.services.fbs_tracking_service import FbsTrackingError, sync_in_delivery_supplies
from app.services.fbs_wb_seller_lock_service import wb_seller_lock
from app.services.wb_marketplace_orders_service import (
    WbMarketplaceOrdersError,
    sync_seller_orders,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SellerPollTarget:
    tenant_id: uuid.UUID
    seller_id: uuid.UUID


@dataclass(frozen=True)
class FbsAutopollCycleResult:
    sellers_polled: int
    orders_upserted: int
    orders_created: int
    statuses_updated: int
    seller_errors: int
    stocks_bindings_processed: int = 0
    stock_errors: int = 0


@dataclass
class SellerStockSyncResult:
    bindings_processed: int = 0
    products_targeted: int = 0
    products_confirmed: int = 0
    products_zeroed: int = 0
    conflicts: int = 0
    errors: int = 0
    binding_errors: int = 0


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


async def list_active_stock_sync_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    wb_warehouse_id: int | None = None,
) -> list[FbsWarehouseBinding]:
    stmt = (
        select(FbsWarehouseBinding)
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.is_active.is_(True),
            FbsWarehouseBinding.stock_sync_enabled.is_(True),
        )
        .order_by(FbsWarehouseBinding.wb_warehouse_id.asc())
    )
    if wb_warehouse_id is not None:
        stmt = stmt.where(FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id)
    return list((await session.execute(stmt)).scalars().all())


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
) -> dict[str, int]:
    result = await sync_seller_orders(
        session,
        target.tenant_id,
        target.seller_id,
        http_client,
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


MARKING_SYNC_BATCH_SIZE = 100


async def sync_marking_statuses_for_assembling_supplies(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> int:
    from app.services.fbs_marking_service import (
        FbsMarkingError,
        sync_order_marking_statuses,
    )

    stmt = (
        select(FbsOrder.id)
        .join(FbsSupply, FbsOrder.supply_id == FbsSupply.id)
        .where(
            FbsOrder.tenant_id == target.tenant_id,
            FbsOrder.seller_id == target.seller_id,
            FbsSupply.status == FBS_SUPPLY_STATUS_ASSEMBLING,
        )
        .order_by(FbsOrder.created_at_wb.asc(), FbsOrder.id.asc())
        .limit(MARKING_SYNC_BATCH_SIZE)
    )
    order_ids = [row[0] for row in (await session.execute(stmt)).all()]
    synced = 0
    for order_id in order_ids:
        try:
            await sync_order_marking_statuses(session, target.tenant_id, order_id, http_client)
            synced += 1
        except FbsMarkingError as exc:
            logger.warning(
                "fbs autopoll marking sync skipped order %s: %s",
                order_id,
                exc.code,
            )
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


async def poll_fbs_orders_all_sellers() -> FbsAutopollCycleResult:
    async with SessionLocal() as session:
        targets = await list_sellers_with_marketplace_token(session)

    sellers_polled = 0
    orders_upserted = 0
    orders_created = 0
    statuses_updated = 0
    seller_errors = 0
    stocks_bindings_processed = 0
    stock_errors = 0

    logger.info("fbs autopoll orders: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            try:
                async with (
                    SessionLocal() as session,
                    wb_seller_lock(session, target.seller_id) as wb_lock_acquired,
                ):
                    if not wb_lock_acquired:
                        logger.info(
                            "fbs autopoll orders skipped busy seller %s",
                            target.seller_id,
                        )
                        continue
                    stats = await poll_fbs_orders_for_seller(session, target, http_client)
            except WbMarketplaceOrdersError as exc:
                seller_errors += 1
                logger.error(
                    "fbs autopoll orders failed for seller %s (tenant %s): %s",
                    target.seller_id,
                    target.tenant_id,
                    exc.code,
                )
                continue
            except Exception:
                seller_errors += 1
                logger.exception(
                    "fbs autopoll orders failed for seller %s (tenant %s)",
                    target.seller_id,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            orders_upserted += stats["orders_upserted"]
            orders_created += stats["orders_created"]
            statuses_updated += stats["statuses_updated"]
            stocks_bindings_processed += stats["stocks_bindings_processed"]
            stock_errors += stats["stock_errors"]

    logger.info(
        "fbs autopoll orders done: sellers=%s upserted=%s created=%s statuses=%s "
        "stocks_bindings=%s stock_errors=%s errors=%s",
        sellers_polled,
        orders_upserted,
        orders_created,
        statuses_updated,
        stocks_bindings_processed,
        stock_errors,
        seller_errors,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=orders_upserted,
        orders_created=orders_created,
        statuses_updated=statuses_updated,
        seller_errors=seller_errors,
        stocks_bindings_processed=stocks_bindings_processed,
        stock_errors=stock_errors,
    )


async def sync_fbs_order_statuses_all_sellers() -> FbsAutopollCycleResult:
    async with SessionLocal() as session:
        targets = await list_sellers_with_marketplace_token(session)

    sellers_polled = 0
    statuses_updated = 0
    seller_errors = 0

    logger.info("fbs autopoll statuses: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            try:
                async with (
                    SessionLocal() as session,
                    wb_seller_lock(session, target.seller_id) as wb_lock_acquired,
                ):
                    if not wb_lock_acquired:
                        logger.info(
                            "fbs autopoll statuses skipped busy seller %s",
                            target.seller_id,
                        )
                        continue
                    updated = await sync_fbs_order_statuses_for_seller(
                        session, target, http_client
                    )
                    await session.commit()
            except (WbMarketplaceOrdersError, FbsCancellationError) as exc:
                seller_errors += 1
                logger.error(
                    "fbs autopoll statuses failed for seller %s (tenant %s): %s",
                    target.seller_id,
                    target.tenant_id,
                    exc.code,
                )
                continue
            except Exception:
                seller_errors += 1
                logger.exception(
                    "fbs autopoll statuses failed for seller %s (tenant %s)",
                    target.seller_id,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            statuses_updated += updated

    logger.info(
        "fbs autopoll statuses done: sellers=%s statuses=%s errors=%s",
        sellers_polled,
        statuses_updated,
        seller_errors,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=0,
        orders_created=0,
        statuses_updated=statuses_updated,
        seller_errors=seller_errors,
    )


async def reconcile_fbs_stocks_all_sellers() -> FbsAutopollCycleResult:
    """Safety net: republish FBS availability for every seller, movement events or not.

    Publication is normally event-driven (see `fbs_stock_publish_service`), but an event
    can be lost — a worker restart, a failed WB call, a movement written outside the
    usual services. Without this sweep the cabinet would keep selling a stale number,
    so the cost of a periodic full pass is worth paying.
    """
    async with SessionLocal() as session:
        targets = await list_sellers_with_marketplace_token(session)

    sellers_polled = 0
    bindings_processed = 0
    seller_errors = 0
    stock_errors = 0

    logger.info("fbs stock reconcile: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            try:
                async with (
                    SessionLocal() as session,
                    wb_seller_lock(session, target.seller_id) as wb_lock_acquired,
                ):
                    if not wb_lock_acquired:
                        logger.info(
                            "fbs stock reconcile skipped busy seller %s",
                            target.seller_id,
                        )
                        continue
                    result = await sync_seller_stocks(
                        session,
                        target.tenant_id,
                        target.seller_id,
                        http_client,
                    )
                    await session.commit()
            except Exception:
                seller_errors += 1
                logger.exception(
                    "fbs stock reconcile failed for seller %s (tenant %s)",
                    target.seller_id,
                    target.tenant_id,
                )
                continue

            sellers_polled += 1
            bindings_processed += result.bindings_processed
            stock_errors += result.binding_errors

    logger.info(
        "fbs stock reconcile done: sellers=%s bindings=%s stock_errors=%s errors=%s",
        sellers_polled,
        bindings_processed,
        stock_errors,
        seller_errors,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=0,
        orders_created=0,
        statuses_updated=0,
        seller_errors=seller_errors,
        stocks_bindings_processed=bindings_processed,
        stock_errors=stock_errors,
    )
