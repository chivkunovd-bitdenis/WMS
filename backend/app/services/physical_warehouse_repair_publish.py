"""Recoverable post-commit publication of only repair-affected products/rules."""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.services.fbs_stock_sync_service import sync_binding_stocks
from app.services.marketplace_seller_lock_service import marketplace_seller_lock
from app.services.ozon_fbs_sync_service import sync_ozon_stocks
from app.services.ozon_provider_factory import build_ozon_provider
from app.services.physical_warehouse_repair_service import JOB_TYPE, Row, WarehouseRepairError


async def publish(run_id: uuid.UUID) -> Row:
    async with SessionLocal() as session:
        job = await session.get(BackgroundJob, run_id, with_for_update=True)
        if job is None or job.job_type != JOB_TYPE or job.status != "completed":
            raise WarehouseRepairError("completed_repair_required")
        result = dict(job.result_json or {})
        if result.get("publication") in {"confirmed", "not_needed"}:
            return result
        # Persist before any external call. A lost response is already enough to
        # make rollback unsafe; repeating publication remains recoverable.
        result["publication_started"] = True
        job.result_json = result
        await session.commit()
        products = {uuid.UUID(p) for p in result.get("product_ids", [])}
        tenant_id = job.tenant_id
        target_id = uuid.UUID((job.payload_json or {})["target_id"])
        seller_ids = list((await session.scalars(select(Product.seller_id).where(
            Product.id.in_(products), Product.tenant_id == tenant_id,
        ).distinct())).all())
        bindings = list((await session.scalars(select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id.in_(seller_ids),
            FbsWarehouseBinding.wms_warehouse_id == target_id,
            FbsWarehouseBinding.is_active.is_(True),
            FbsWarehouseBinding.stock_sync_enabled.is_(True),
        ))).all())
        scopes = [(b.id, b.seller_id, b.marketplace) for b in bindings]
    confirmations: list[Row] = []
    for binding_id, seller_id, marketplace in scopes:
        try:
            async with (
                SessionLocal() as session, SessionLocal() as lock_session,
                marketplace_seller_lock(lock_session, seller_id, marketplace,
                                       wait_timeout_sec=30) as acquired,
                httpx.AsyncClient() as http_client,
            ):
                if not acquired:
                    confirmations.append({"binding_id": str(binding_id), "status": "busy"})
                    continue
                binding = await session.get(FbsWarehouseBinding, binding_id)
                if binding is None or binding.wms_warehouse_id != target_id:
                    confirmations.append({"binding_id": str(binding_id), "status": "changed"})
                    continue
                if marketplace == "wb":
                    synced = await sync_binding_stocks(
                        session, tenant_id, seller_id, binding, http_client, product_ids=products,
                    )
                    errors = synced.errors + synced.conflicts + int(synced.skipped_busy)
                    targeted, confirmed = synced.products_targeted, synced.products_confirmed
                elif marketplace == "ozon":
                    ozon = await sync_ozon_stocks(
                        session, tenant_id, seller_id, build_ozon_provider(),
                        product_ids=products, binding_ids={binding_id},
                    )
                    errors = ozon.errors + ozon.conflicts + ozon.binding_errors
                    targeted, confirmed = ozon.products_targeted, ozon.products_confirmed
                else:
                    raise WarehouseRepairError("unsupported_marketplace")
                await session.commit()
                confirmations.append({
                    "binding_id": str(binding_id), "marketplace": marketplace,
                    "targeted": targeted, "confirmed": confirmed,
                    "status": "confirmed" if errors == 0 and targeted == confirmed else "pending",
                })
        except Exception as exc:
            # The provider's own durable sync result carries details. Do not put
            # tokens/request payloads in the repair report or roll back stock.
            confirmations.append({"binding_id": str(binding_id), "status": "pending",
                                  "error_type": type(exc).__name__})
    async with SessionLocal() as session, session.begin():
        job = await session.get(BackgroundJob, run_id, with_for_update=True)
        if job is None or job.status != "completed":
            raise WarehouseRepairError("repair_state_changed")
        result = dict(job.result_json or {})
        result["publication"] = (
            "confirmed" if all(c["status"] == "confirmed" for c in confirmations) else "pending"
        )
        result["publication_results"] = confirmations
        job.result_json = result
    return result
