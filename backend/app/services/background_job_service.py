from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.inventory_movement import InventoryMovement
from app.models.seller import Seller
from app.services import wildberries_sync_service as wb_sync

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"

JOB_TYPE_MOVEMENTS_DIGEST = "movements_digest"
JOB_TYPE_WILDBERRIES_CARDS_SYNC = "wildberries_cards_sync"
JOB_TYPE_SELLER_WB_CATALOG_SYNC = "seller_wb_catalog_sync"
JOB_TYPE_OZON_CATALOG_SYNC = "ozon_catalog_sync"
JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC = "wildberries_supplies_sync"
JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC = "wildberries_marketplace_orders_sync"
JOB_TYPE_FBS_STOCK_SYNC = "fbs_stock_sync"
JOB_TYPE_STORAGE_MEASUREMENT_REBUILD = "storage_measurement_rebuild"
JOB_TYPE_FBS_LABEL_PRINT = "fbs_label_print"

# A catalog import can legitimately take minutes for a large seller.  Two hours
# is deliberately above the measured 55k-card runs, while still recovering a
# row left RUNNING forever when a worker is killed without a final update.
CATALOG_SYNC_JOB_LEASE = timedelta(hours=2)
WB_CATALOG_JOB_TYPES = frozenset(
    {JOB_TYPE_WILDBERRIES_CARDS_SYNC, JOB_TYPE_SELLER_WB_CATALOG_SYNC}
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _catalog_job_is_stale(job: BackgroundJob, *, now: datetime) -> bool:
    lease_started_at = (
        (job.started_at or job.created_at)
        if job.status == JOB_STATUS_RUNNING
        else job.created_at
    )
    return _utc(lease_started_at) <= now - CATALOG_SYNC_JOB_LEASE


async def _claim_catalog_sync_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    allowed_job_types: frozenset[str],
) -> BackgroundJob | None:
    """Atomically claim a pending delivery exactly once.

    Celery may redeliver the same message.  A compare-and-swap UPDATE makes a
    second delivery a no-op even across worker processes; a plain SELECT FOR
    UPDATE would not protect the SQLite test environment and was easier to get
    wrong when the lock scope changed.
    """
    now = datetime.now(UTC)
    claimed = await session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            BackgroundJob.job_type.in_(allowed_job_types),
            BackgroundJob.status == JOB_STATUS_PENDING,
        )
        .values(
            status=JOB_STATUS_RUNNING,
            started_at=now,
            finished_at=None,
            result_json=None,
            error_message=None,
        )
    )
    await session.commit()
    if getattr(claimed, "rowcount", 0) != 1:
        return None
    return await session.get(BackgroundJob, job_id)


async def create_pending_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_type: str,
    payload_json: dict[str, Any] | None = None,
) -> BackgroundJob:
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type=job_type,
        status=JOB_STATUS_PENDING,
        payload_json=payload_json,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def create_or_get_seller_catalog_sync_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    job_type: str,
    marketplace: str,
) -> tuple[BackgroundJob, bool]:
    """Create one active catalog job per seller/marketplace.

    The seller row is the existing durable lock target.  It serialises the
    lookup/create pair on PostgreSQL without introducing a new table or a
    second source of sync state.  A repeated click while a job is pending or
    running receives that same job id and therefore cannot start a duplicate
    full-catalog import.
    """
    locked = await session.execute(
        update(Seller)
        .where(Seller.id == seller_id, Seller.tenant_id == tenant_id)
        .values(name=Seller.name)
    )
    if getattr(locked, "rowcount", 0) != 1:
        raise ValueError("seller_not_found")
    compatible_types = (
        WB_CATALOG_JOB_TYPES if marketplace == "wildberries" else frozenset({job_type})
    )
    active = await session.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type.in_(compatible_types),
            BackgroundJob.status.in_((JOB_STATUS_PENDING, JOB_STATUS_RUNNING)),
            BackgroundJob.payload_json["seller_id"].as_string() == str(seller_id),
        )
        .order_by(BackgroundJob.created_at.desc())
        .limit(1)
    )
    if active is not None:
        now = datetime.now(UTC)
        if not _catalog_job_is_stale(active, now=now):
            await session.commit()
            return active, False
        active.status = JOB_STATUS_FAILED
        active.result_json = None
        active.error_message = "catalog_job_lease_expired"
        active.finished_at = now
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type=job_type,
        status=JOB_STATUS_PENDING,
        payload_json={"seller_id": str(seller_id), "marketplace": marketplace},
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job, True


async def mark_job_dispatch_failed(
    session: AsyncSession, job: BackgroundJob, *, error_code: str
) -> BackgroundJob:
    job.status = JOB_STATUS_FAILED
    job.result_json = None
    job.error_message = error_code
    job.finished_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(job)
    return job


async def get_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
) -> BackgroundJob | None:
    job = await session.get(BackgroundJob, job_id)
    if job is None or job.tenant_id != tenant_id:
        return None
    return job


async def run_movements_digest_job(job_id: uuid.UUID) -> None:
    """Выполняется в фоне после ответа API (отдельная сессия БД)."""
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("background job missing: %s", job_id)
            return
        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            await asyncio.sleep(0.35)
            stmt = select(InventoryMovement.movement_type, func.count(InventoryMovement.id)).where(
                InventoryMovement.tenant_id == job.tenant_id
            ).group_by(InventoryMovement.movement_type)
            res = await session.execute(stmt)
            by_type = {str(mt): int(count) for mt, count in res.all()}
            job.status = JOB_STATUS_DONE
            job.result_json = {
                "movement_counts_by_type": by_type,
                "total_movements": sum(by_type.values()),
            }
            job.error_message = None
        except Exception as exc:
            logger.exception("background job failed: %s", job_id)
            job.status = JOB_STATUS_FAILED
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_storage_measurement_rebuild_job(job_id: uuid.UUID) -> None:
    from datetime import date

    from app.services.storage_measurement_service import rebuild_storage_measurements
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            return
        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            payload = job.payload_json or {}
            year, month = payload.get("year"), payload.get("month")
            period_start = (
                date(year, month, 1)
                if isinstance(year, int) and isinstance(month, int)
                else None
            )
            raw_warehouse = payload.get("warehouse_id")
            warehouse_id = uuid.UUID(raw_warehouse) if isinstance(raw_warehouse, str) else None
            raw_seller = payload.get("seller_id")
            seller_id = uuid.UUID(raw_seller) if isinstance(raw_seller, str) else None
            result = await rebuild_storage_measurements(
                session,
                job.tenant_id,
                period_start=period_start,
                warehouse_id=warehouse_id,
                seller_id=seller_id,
            )
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except Exception as exc:
            logger.exception("storage measurement rebuild failed: %s", job_id)
            await session.rollback()
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.status = JOB_STATUS_FAILED
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_wildberries_cards_sync_job(job_id: uuid.UUID) -> None:
    """WB cards list (all pages) using seller token from DB; separate DB session."""
    async with SessionLocal() as session:
        job = await _claim_catalog_sync_job(
            session,
            job_id,
            allowed_job_types=WB_CATALOG_JOB_TYPES,
        )
        if job is None:
            logger.info("WB catalog job already claimed or unavailable: %s", job_id)
            return
        payload = job.payload_json or {}
        sid_raw = payload.get("seller_id")
        if not sid_raw or not isinstance(sid_raw, str):
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "missing_job_seller_id"
            await session.commit()
            return
        try:
            seller_uuid = uuid.UUID(sid_raw)
        except ValueError:
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "invalid_job_seller_id"
            await session.commit()
            return

        try:
            async with httpx.AsyncClient() as http_client:
                # The legacy entrypoint and the seller entrypoint now perform
                # the same full-snapshot operation.  Besides closing a
                # cross-job-type collision, this preserves WMS-548 semantics:
                # only already selected cards update Product rows.
                from app.services.wildberries_product_sync_service import (
                    sync_wb_products_for_seller,
                )

                result = await sync_wb_products_for_seller(
                    session, job.tenant_id, seller_uuid, http_client
                )
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except wb_sync.WildberriesSyncError as exc:
            logger.warning("wildberries sync job failed: %s", exc.code)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = exc.code
        except Exception as exc:
            logger.exception(
                "wildberries sync job failed job=%s exception_type=%s",
                job_id,
                type(exc).__name__,
            )
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = "wildberries_catalog_failed"
        job.finished_at = datetime.now(UTC)
        await session.commit()


def _safe_ozon_catalog_error(exc: Exception) -> str:
    """Return a public-safe stable code; never persist provider payloads."""
    from app.services.marketplace_provider import MarketplaceProviderError

    if not isinstance(exc, MarketplaceProviderError):
        return "ozon_catalog_failed"
    if exc.code in {"ozon_catalog_invalid_response", "ozon_catalog_incomplete"}:
        return exc.code
    if exc.status_code == 429:
        return "ozon_catalog_rate_limited"
    if exc.status_code in {401, 403}:
        return "ozon_catalog_credentials_rejected"
    return "ozon_catalog_unavailable"


def _ozon_catalog_error_is_retryable(exc: Exception) -> bool:
    from app.services.marketplace_provider import MarketplaceProviderError

    return (
        isinstance(exc, MarketplaceProviderError)
        and exc.code not in {"ozon_catalog_invalid_response", "ozon_catalog_incomplete"}
        and (exc.status_code is None or exc.status_code == 429 or exc.status_code >= 500)
    )


async def run_ozon_catalog_sync_job(job_id: uuid.UUID) -> None:
    """Import one seller's complete Ozon snapshot and publish honest sync state."""
    from app.services.marketplace_account_service import (
        MarketplaceAccountError,
        MarketplaceAccountService,
        SellerNotFound,
    )
    from app.services.ozon_product_import_service import import_ozon_product_cards
    from app.services.ozon_provider_factory import build_ozon_provider

    async with SessionLocal() as session:
        job = await _claim_catalog_sync_job(
            session,
            job_id,
            allowed_job_types=frozenset({JOB_TYPE_OZON_CATALOG_SYNC}),
        )
        if job is None:
            logger.info("Ozon catalog job already claimed or unavailable: %s", job_id)
            return
        tenant_id = job.tenant_id
        payload = job.payload_json or {}
        raw_seller_id = payload.get("seller_id")
        try:
            seller_id = uuid.UUID(raw_seller_id) if isinstance(raw_seller_id, str) else None
        except ValueError:
            seller_id = None
        if seller_id is None:
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "invalid_job_seller_id"
            await session.commit()
            return

        account_service = MarketplaceAccountService(session)
        error: Exception | None = None
        result: Any = None
        try:
            client_id, api_key = await account_service.stored_credentials(
                tenant_id, seller_id
            )
            for attempt in range(3):
                try:
                    result = await import_ozon_product_cards(
                        session,
                        tenant_id,
                        seller_id,
                        build_ozon_provider(),
                        client_id=client_id,
                        api_key=api_key,
                    )
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    await session.rollback()
                    if attempt == 2 or not _ozon_catalog_error_is_retryable(exc):
                        break
                    await asyncio.sleep(0.25 * (2**attempt))
            if error is not None:
                raise error
            assert result is not None
            await account_service.mark_catalog_sync_succeeded(tenant_id, seller_id)
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.status = JOB_STATUS_DONE
            job.result_json = {
                "tenant_id": str(tenant_id),
                "seller_id": str(seller_id),
                "marketplace": "ozon",
                "cards_received": result.cards_read,
                "cards_saved": result.cards_saved,
                "links_created": result.links_created,
                "products_created": result.products_created,
            }
            job.error_message = None
        except (SellerNotFound, MarketplaceAccountError) as exc:
            await session.rollback()
            code = exc.code
            try:
                await MarketplaceAccountService(session).mark_catalog_sync_failed(
                    tenant_id, seller_id, code
                )
            except MarketplaceAccountError:
                await session.rollback()
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = code
        except Exception as exc:
            await session.rollback()
            code = _safe_ozon_catalog_error(exc)
            logger.warning("ozon catalog sync failed job=%s code=%s", job_id, code)
            try:
                await MarketplaceAccountService(session).mark_catalog_sync_failed(
                    tenant_id, seller_id, code
                )
            except MarketplaceAccountError:
                await session.rollback()
            job = await session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = code
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_wildberries_supplies_sync_job(job_id: uuid.UUID) -> None:
    """WB FBW supplies list (all pages) using supplies token from DB."""
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("background job missing: %s", job_id)
            return
        payload = job.payload_json or {}
        sid_raw = payload.get("seller_id")
        if not sid_raw or not isinstance(sid_raw, str):
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "missing_job_seller_id"
            await session.commit()
            return
        try:
            seller_uuid = uuid.UUID(sid_raw)
        except ValueError:
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "invalid_job_seller_id"
            await session.commit()
            return

        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            async with httpx.AsyncClient() as http_client:
                result = await wb_sync.sync_supplies_list(
                    session, job.tenant_id, seller_uuid, http_client
                )
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except wb_sync.WildberriesSyncError as exc:
            logger.warning("wildberries supplies sync job failed: %s", exc.code)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = exc.code
        except Exception as exc:
            logger.exception("wildberries supplies sync job failed: %s", exc)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_wildberries_marketplace_orders_sync_job(job_id: uuid.UUID) -> None:
    """WB Marketplace FBS orders sync per seller (supplies token as marketplace token)."""
    from app.services.wb_marketplace_orders_service import (
        WbMarketplaceOrdersError,
        sync_seller_orders,
    )

    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("background job missing: %s", job_id)
            return
        payload = job.payload_json or {}
        sid_raw = payload.get("seller_id")
        if not sid_raw or not isinstance(sid_raw, str):
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "missing_job_seller_id"
            await session.commit()
            return
        try:
            seller_uuid = uuid.UUID(sid_raw)
        except ValueError:
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "invalid_job_seller_id"
            await session.commit()
            return

        warehouse_uuid: uuid.UUID | None = None
        wh_raw = payload.get("warehouse_id")
        if isinstance(wh_raw, str) and wh_raw.strip():
            try:
                warehouse_uuid = uuid.UUID(wh_raw)
            except ValueError:
                job.status = JOB_STATUS_FAILED
                job.started_at = datetime.now(UTC)
                job.finished_at = datetime.now(UTC)
                job.error_message = "invalid_job_warehouse_id"
                await session.commit()
                return

        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            async with httpx.AsyncClient() as http_client:
                result = await sync_seller_orders(
                    session,
                    job.tenant_id,
                    seller_uuid,
                    http_client,
                    warehouse_id=warehouse_uuid,
                )
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except WbMarketplaceOrdersError as exc:
            logger.warning("wildberries marketplace orders sync failed: %s", exc.code)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            # КРИТ-2 (docs/agent-orders/HANDOFF-POLISH.md, пул 1, п.3): раньше здесь
            # сохранялся голый код (например "wb_upstream_error_401"), и оператор видел
            # на экране шифр вместо причины. exc.message — уже человеческий текст
            # (см. wb_operator_message в wildberries_errors.py).
            job.error_message = exc.message
        except Exception as exc:
            logger.exception("wildberries marketplace orders sync failed: %s", exc)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_fbs_stock_sync_job(job_id: uuid.UUID) -> None:
    """FBS stock reconciliation for one seller (optional single WB warehouse binding)."""
    from app.services.fbs_autopoll_service import sync_seller_stocks

    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            logger.warning("background job missing: %s", job_id)
            return
        payload = job.payload_json or {}
        sid_raw = payload.get("seller_id")
        if not sid_raw or not isinstance(sid_raw, str):
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "missing_job_seller_id"
            await session.commit()
            return
        try:
            seller_uuid = uuid.UUID(sid_raw)
        except ValueError:
            job.status = JOB_STATUS_FAILED
            job.started_at = datetime.now(UTC)
            job.finished_at = datetime.now(UTC)
            job.error_message = "invalid_job_seller_id"
            await session.commit()
            return

        wb_warehouse_id: int | None = None
        wb_raw = payload.get("wb_warehouse_id")
        if isinstance(wb_raw, int):
            wb_warehouse_id = wb_raw
        elif isinstance(wb_raw, str) and wb_raw.strip().isdigit():
            wb_warehouse_id = int(wb_raw)

        job.status = JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await session.commit()
        try:
            from app.services.marketplace_seller_lock_service import marketplace_seller_lock

            async with (
                AsyncSession(bind=session.bind) as lock_session,
                marketplace_seller_lock(
                    lock_session, seller_uuid, "wb", wait_timeout_sec=30,
                ) as acquired,
            ):
                if not acquired:
                    raise RuntimeError("stock_sync_busy")
                async with httpx.AsyncClient() as http_client:
                    result = await sync_seller_stocks(
                        session,
                        job.tenant_id,
                        seller_uuid,
                        http_client,
                        wb_warehouse_id=wb_warehouse_id,
                    )
            job.status = JOB_STATUS_DONE
            job.result_json = {
                "bindings_processed": result.bindings_processed,
                "products_targeted": result.products_targeted,
                "products_confirmed": result.products_confirmed,
                "products_zeroed": result.products_zeroed,
                "conflicts": result.conflicts,
                "errors": result.errors,
                "binding_errors": result.binding_errors,
            }
            job.error_message = None
        except Exception as exc:
            logger.exception("fbs stock sync job failed: %s", exc)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()
