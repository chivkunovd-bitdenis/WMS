"""Periodic FBS order polling for all sellers with a marketplace WB token."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.services.fbs_cancellation_service import FbsCancellationError, sync_seller_order_statuses
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


async def list_sellers_with_marketplace_token(
    session: AsyncSession,
) -> list[SellerPollTarget]:
    stmt = (
        select(Seller.tenant_id, Seller.id)
        .join(
            SellerWildberriesCredentials,
            SellerWildberriesCredentials.seller_id == Seller.id,
        )
        .where(SellerWildberriesCredentials.marketplace_token_encrypted.isnot(None))
        .order_by(Seller.tenant_id, Seller.id)
    )
    rows = (await session.execute(stmt)).all()
    return [SellerPollTarget(tenant_id=row[0], seller_id=row[1]) for row in rows]


async def poll_fbs_orders_for_seller(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> dict[str, int]:
    result = await sync_seller_orders(
        session,
        target.tenant_id,
        target.seller_id,
        http_client,
    )
    return {
        "orders_upserted": int(result.get("orders_upserted", 0)),
        "orders_created": int(result.get("orders_created", 0)),
        "statuses_updated": int(result.get("statuses_updated", 0)),
    }


async def sync_fbs_order_statuses_for_seller(
    session: AsyncSession,
    target: SellerPollTarget,
    http_client: httpx.AsyncClient,
) -> int:
    return await sync_seller_order_statuses(
        session,
        target.tenant_id,
        target.seller_id,
        http_client,
    )


async def poll_fbs_orders_all_sellers() -> FbsAutopollCycleResult:
    async with SessionLocal() as session:
        targets = await list_sellers_with_marketplace_token(session)

    sellers_polled = 0
    orders_upserted = 0
    orders_created = 0
    statuses_updated = 0
    seller_errors = 0

    logger.info("fbs autopoll orders: starting cycle for %s sellers", len(targets))

    async with httpx.AsyncClient() as http_client:
        for target in targets:
            try:
                async with SessionLocal() as session:
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

    logger.info(
        "fbs autopoll orders done: sellers=%s upserted=%s created=%s statuses=%s errors=%s",
        sellers_polled,
        orders_upserted,
        orders_created,
        statuses_updated,
        seller_errors,
    )
    return FbsAutopollCycleResult(
        sellers_polled=sellers_polled,
        orders_upserted=orders_upserted,
        orders_created=orders_created,
        statuses_updated=statuses_updated,
        seller_errors=seller_errors,
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
                async with SessionLocal() as session:
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
