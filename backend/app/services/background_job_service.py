from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.inventory_movement import InventoryMovement
from app.services import wildberries_sync_service as wb_sync

logger = logging.getLogger(__name__)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_FAILED = "failed"

JOB_TYPE_MOVEMENTS_DIGEST = "movements_digest"
JOB_TYPE_WILDBERRIES_CARDS_SYNC = "wildberries_cards_sync"
JOB_TYPE_WILDBERRIES_SUPPLIES_SYNC = "wildberries_supplies_sync"
JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC = "wildberries_marketplace_orders_sync"
JOB_TYPE_FBS_STOCK_SYNC = "fbs_stock_sync"
JOB_TYPE_STORAGE_MEASUREMENT_REBUILD = "storage_measurement_rebuild"


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
    """WB cards list (first page) using seller token from DB; separate DB session."""
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
                result = await wb_sync.sync_cards_list_first_page(
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
            logger.exception("wildberries sync job failed: %s", exc)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = str(exc)
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def run_wildberries_supplies_sync_job(job_id: uuid.UUID) -> None:
    """WB FBW supplies list (first page) using supplies token from DB."""
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
                result = await wb_sync.sync_supplies_list_first_page(
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
