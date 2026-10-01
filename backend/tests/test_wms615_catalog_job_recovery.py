"""WMS-615 durable catalog job leases, claims and WB entrypoint collision."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services import background_job_service as jobs
from app.services import wildberries_product_sync_service as wb_product_sync
from app.tasks.background_jobs import run_wildberries_cards_sync_task


async def _seller() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        tenant = Tenant(name="Catalog lease", slug=f"catalog-lease-{uuid.uuid4().hex[:8]}")
        seller = Seller(tenant=tenant, name="Seller")
        session.add_all([tenant, seller])
        await session.commit()
        return tenant.id, seller.id


@pytest.mark.asyncio
async def test_stale_running_catalog_job_is_failed_and_requeued_once(db_session) -> None:
    tenant_id, seller_id = await _seller()
    stale_started_at = datetime.now(UTC) - jobs.CATALOG_SYNC_JOB_LEASE * 2
    async with SessionLocal() as session:
        stale = BackgroundJob(
            tenant_id=tenant_id,
            job_type=jobs.JOB_TYPE_WILDBERRIES_CARDS_SYNC,
            status=jobs.JOB_STATUS_RUNNING,
            payload_json={"seller_id": str(seller_id)},
            started_at=stale_started_at,
        )
        session.add(stale)
        await session.commit()
        stale_id = stale.id

    async with SessionLocal() as session:
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        assert replacement.id != stale_id
        replacement_id = replacement.id

    async with SessionLocal() as session:
        stale = await session.get(BackgroundJob, stale_id)
        assert stale is not None
        assert stale.status == jobs.JOB_STATUS_FAILED
        assert stale.error_message == "catalog_job_lease_expired"
        assert stale.finished_at is not None
        same, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_WILDBERRIES_CARDS_SYNC,
            marketplace="wildberries",
        )
        assert not created
        assert same.id == replacement_id


@pytest.mark.asyncio
async def test_duplicate_worker_delivery_claims_fresh_job_only_once(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id = await _seller()
    async with SessionLocal() as session:
        job, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        job_id = job.id

    calls = 0

    async def slow_sync(session, actual_tenant_id, actual_seller_id, http_client):
        nonlocal calls
        calls += 1
        assert (actual_tenant_id, actual_seller_id) == (tenant_id, seller_id)
        await asyncio.sleep(0.05)
        return {"cards_received": 0, "cards_saved": 0}

    monkeypatch.setattr(wb_product_sync, "sync_wb_products_for_seller", slow_sync)
    await asyncio.gather(
        jobs.run_wildberries_cards_sync_job(job_id),
        jobs.run_wildberries_cards_sync_job(job_id),
    )

    assert calls == 1
    async with SessionLocal() as session:
        stored = await session.get(BackgroundJob, job_id)
        assert stored is not None
        assert stored.status == jobs.JOB_STATUS_DONE


@pytest.mark.asyncio
async def test_parallel_legacy_and_seller_wb_entrypoints_share_one_active_job(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import wildberries_integration as wb_api

    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Catalog collision {suffix}",
            "slug": f"catalog-collision-{suffix}",
            "admin_email": f"catalog-collision-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    admin_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    created = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Collision seller"}
    )
    assert created.status_code == 201, created.text
    seller_id = uuid.UUID(created.json()["id"])
    email = f"catalog-collision-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": str(seller_id), "email": email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    logged_in = await async_client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert logged_in.status_code == 200, logged_in.text
    seller_headers = {"Authorization": f"Bearer {logged_in.json()['access_token']}"}

    async def credentials(*_args, **_kwargs):
        return "configured-content-token", None

    queued: list[str] = []
    monkeypatch.setattr(wb_api, "get_decrypted_tokens_for_seller", credentials)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://configured")
    monkeypatch.setattr(
        run_wildberries_cards_sync_task,
        "delay",
        lambda job_id: queued.append(job_id),
    )

    legacy, seller_sync = await asyncio.gather(
        async_client.post(
            "/operations/background-jobs/wildberries-cards-sync-self",
            headers=seller_headers,
        ),
        async_client.post(
            "/integrations/wildberries/self/sync-products",
            headers=seller_headers,
        ),
    )
    assert legacy.status_code == seller_sync.status_code == 202
    assert legacy.json()["id"] == seller_sync.json()["id"]
    assert queued == [legacy.json()["id"]]

    # With Celery configured, the API process only publishes the durable job;
    # a normal authenticated read remains independent of the long import.
    me = await async_client.get("/auth/me", headers=seller_headers)
    assert me.status_code == 200, me.text
    async with SessionLocal() as session:
        active_count = await session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.job_type.in_(jobs.WB_CATALOG_JOB_TYPES),
                BackgroundJob.status.in_((jobs.JOB_STATUS_PENDING, jobs.JOB_STATUS_RUNNING)),
                BackgroundJob.payload_json["seller_id"].as_string() == str(seller_id),
            )
        )
        assert active_count == 1
