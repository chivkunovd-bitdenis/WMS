from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
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
JOB_TYPE_MARKING_LABEL_TAPE = "marking_label_tape"

# A print worker that dies after claiming a job must not leave the operator's
# idempotent request permanently stuck.  A repeated request republishes the
# same job and can reclaim it only after this lease has elapsed.
MARKING_LABEL_TAPE_RUNNING_LEASE = timedelta(minutes=15)
MARKING_LABEL_TAPE_HEARTBEAT_INTERVAL_SECONDS = 60.0


async def _reusable_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    job_type: str,
    idempotency_key: str,
) -> BackgroundJob | None:
    statuses = [JOB_STATUS_PENDING, JOB_STATUS_RUNNING]
    if job_type == JOB_TYPE_MARKING_LABEL_TAPE:
        statuses.append(JOB_STATUS_DONE)
    existing = await session.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == job_type,
            BackgroundJob.idempotency_key == idempotency_key,
            BackgroundJob.status.in_(statuses),
        )
        .with_for_update()
    )
    if existing is None or existing.status != JOB_STATUS_DONE:
        return existing

    from app.models.fbs_print_asset import (
        PRINT_ASSET_KIND_LABEL_TAPE,
        PRINT_ASSET_STATUS_READY,
        FbsPrintAsset,
    )

    asset_id_raw = (existing.result_json or {}).get("asset_id")
    try:
        asset_id = uuid.UUID(str(asset_id_raw))
    except (TypeError, ValueError):
        asset_id = None
    asset = await session.get(FbsPrintAsset, asset_id) if asset_id is not None else None
    now = datetime.now(UTC)
    if (
        asset is not None
        and asset.tenant_id == tenant_id
        and asset.kind == PRINT_ASSET_KIND_LABEL_TAPE
        and asset.status == PRINT_ASSET_STATUS_READY
        and asset.storage_path is not None
        and asset.expires_at is not None
        and asset.expires_at > now
    ):
        return existing

    # The completed job remains an audit record, but an expired or unavailable
    # artifact must not reserve the deterministic request key forever.
    existing.idempotency_key = None
    await session.commit()
    return None


async def create_pending_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    job_type: str,
    payload_json: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> BackgroundJob:
    if idempotency_key:
        existing = await _reusable_job(session, tenant_id, job_type, idempotency_key)
        if existing is not None:
            existing.__dict__["created_by_call"] = False
            return existing
    job = BackgroundJob(
        tenant_id=tenant_id,
        job_type=job_type,
        status=JOB_STATUS_PENDING,
        payload_json=payload_json,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    job.__dict__["created_by_call"] = True
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_key:
            existing = await _reusable_job(session, tenant_id, job_type, idempotency_key)
            if existing is not None:
                existing.__dict__["created_by_call"] = False
                return existing
        raise
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


def should_enqueue_marking_label_tape_job(job: BackgroundJob) -> bool:
    """Every active tape job is safe to publish again; DB claiming is single-flight."""
    return job.status in (JOB_STATUS_PENDING, JOB_STATUS_RUNNING)


async def _claim_marking_label_tape_job(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> datetime | None:
    now = datetime.now(UTC)
    stale_before = now - MARKING_LABEL_TAPE_RUNNING_LEASE
    claimed = await session.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id == job_id,
            or_(
                BackgroundJob.status == JOB_STATUS_PENDING,
                and_(
                    BackgroundJob.status == JOB_STATUS_RUNNING,
                    or_(
                        BackgroundJob.started_at.is_(None),
                        BackgroundJob.started_at <= stale_before,
                    ),
                ),
            ),
        )
        .values(status=JOB_STATUS_RUNNING, started_at=now)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
        return None
    return now


async def _refresh_marking_label_tape_lease(
    job_id: uuid.UUID,
    expected_started_at: datetime,
) -> datetime | None:
    """Extend a print lease only while this worker still owns its claim."""
    refreshed_at = datetime.now(UTC)
    async with SessionLocal() as heartbeat_session:
        refreshed = await heartbeat_session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status == JOB_STATUS_RUNNING,
                BackgroundJob.started_at == expected_started_at,
            )
            .values(started_at=refreshed_at)
            .execution_options(synchronize_session=False)
        )
        await heartbeat_session.commit()
    if not isinstance(refreshed, CursorResult) or refreshed.rowcount != 1:
        return None
    return refreshed_at


async def _maintain_marking_label_tape_lease(
    job_id: uuid.UUID,
    claimed_at: datetime,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
) -> None:
    """Keep a long PDF build from looking abandoned to duplicate deliveries."""
    current_heartbeat = claimed_at
    while not stop.is_set():
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=MARKING_LABEL_TAPE_HEARTBEAT_INTERVAL_SECONDS,
            )
        except TimeoutError:
            try:
                refreshed_at = await _refresh_marking_label_tape_lease(
                    job_id,
                    current_heartbeat,
                )
            except Exception:
                logger.exception("marking label tape heartbeat failed: %s", job_id)
                lease_lost.set()
                return
            if refreshed_at is None:
                logger.error("marking label tape lease lost: %s", job_id)
                lease_lost.set()
                return
            current_heartbeat = refreshed_at


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
            stmt = (
                select(InventoryMovement.movement_type, func.count(InventoryMovement.id))
                .where(InventoryMovement.tenant_id == job.tenant_id)
                .group_by(InventoryMovement.movement_type)
            )
            res = await session.execute(stmt)
            rows = list(res.all())
            by_type: dict[str, int] = {str(mt): int(c) for mt, c in rows}
            total = sum(by_type.values())
            result: dict[str, Any] = {
                "movement_counts_by_type": by_type,
                "total_movements": total,
            }
            job.status = JOB_STATUS_DONE
            job.result_json = result
            job.error_message = None
        except Exception as exc:
            logger.exception("background job failed: %s", exc)
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


async def run_marking_label_tape_job(job_id: uuid.UUID) -> None:
    from datetime import timedelta

    from app.models.fbs_print_asset import (
        PRINT_ASSET_KIND_LABEL_TAPE,
        PRINT_ASSET_STATUS_READY,
        FbsPrintAsset,
    )
    from app.models.marking_code import MarkingCode
    from app.services.fbs_print_asset_storage import (
        label_tape_relative_path,
        save_pdf,
        sha256_checksum,
    )
    from app.services.marking_code_service import build_label_artifact_tape_pdf

    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            return
        claimed_at = await _claim_marking_label_tape_job(session, job_id)
        if claimed_at is None:
            return
        await session.refresh(job)
        heartbeat_stop = asyncio.Event()
        lease_lost = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            _maintain_marking_label_tape_lease(
                job_id,
                claimed_at,
                heartbeat_stop,
                lease_lost,
            )
        )
        try:
            payload = job.payload_json or {}
            ids = [uuid.UUID(str(value)) for value in payload.get("code_ids", [])]
            pdf = await build_label_artifact_tape_pdf(
                session,
                job.tenant_id,
                ids,
                page_width_mm=payload.get("page_width_mm"),
                page_height_mm=payload.get("page_height_mm"),
            )
            heartbeat_stop.set()
            await heartbeat_task
            if lease_lost.is_set():
                raise RuntimeError("marking_label_tape_lease_lost")
            code = await session.get(MarkingCode, ids[0])
            if code is None:
                raise ValueError("seller_not_found")
            asset = FbsPrintAsset(
                tenant_id=job.tenant_id,
                seller_id=code.seller_id,
                kind=PRINT_ASSET_KIND_LABEL_TAPE,
                status=PRINT_ASSET_STATUS_READY,
                content_type="application/pdf",
                expires_at=datetime.now(UTC) + timedelta(hours=12),
            )
            session.add(asset)
            await session.flush()
            asset.storage_path = save_pdf(label_tape_relative_path(asset.id), pdf)
            asset.checksum = sha256_checksum(pdf)
            job.result_json = {"asset_id": str(asset.id)}
            job.status = JOB_STATUS_DONE
            job.error_message = None
        except Exception as exc:
            logger.exception("marking label tape job failed: %s", job_id)
            job.status = JOB_STATUS_FAILED
            job.result_json = None
            job.error_message = str(exc)
        finally:
            heartbeat_stop.set()
            await heartbeat_task
        job.finished_at = datetime.now(UTC)
        await session.commit()


async def purge_expired_label_tape_assets() -> int:
    """Remove expired label-tape files while retaining their audit rows."""
    from app.models.fbs_print_asset import PRINT_ASSET_KIND_LABEL_TAPE, FbsPrintAsset
    from app.services.fbs_print_asset_storage import delete_stored_asset

    removed = 0
    async with SessionLocal() as session:
        result = await session.execute(
            select(FbsPrintAsset).where(
                FbsPrintAsset.kind == PRINT_ASSET_KIND_LABEL_TAPE,
                FbsPrintAsset.expires_at.is_not(None),
                FbsPrintAsset.expires_at <= datetime.now(UTC),
                FbsPrintAsset.storage_path.is_not(None),
            )
        )
        for asset in result.scalars().all():
            if asset.storage_path:
                delete_stored_asset(asset.storage_path)
            asset.storage_path = None
            removed += 1
        await session.commit()
    return removed
