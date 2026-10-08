"""WMS-277: existing WB catalogue import scheduled without stock operations."""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import partial

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.tenant import Tenant
from app.services import background_job_service as jobs
from app.services import wildberries_product_sync_service as sync
from app.services.integration_fernet import encrypt_secret
from app.services.wildberries_credentials_service import SKIP, patch_seller_tokens


async def seller_with_token(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, token: str | None,
) -> Seller:
    seller = Seller(tenant_id=tenant_id, name=name)
    session.add(seller)
    await session.flush()
    session.add(SellerWildberriesCredentials(
        seller_id=seller.id,
        content_token_encrypted=encrypt_secret(token) if token else token,
        marketplace_scope_ok=False,
    ))
    await session.commit()
    return seller


def test_hourly_schedule_uses_existing_task_executor() -> None:
    from app.tasks.background_jobs import run_wb_catalog_hourly_sync_task

    # WMS-689 stops automatic full scans, while retaining the existing executor
    # for an explicit operator request and all unrelated periodic operations.
    assert "wb-catalog-hourly" not in celery_app.conf.beat_schedule
    registered = celery_app.tasks[run_wb_catalog_hourly_sync_task.name]
    assert registered.run == run_wb_catalog_hourly_sync_task.run
    assert set(celery_app.conf.beat_schedule) == {
        "developer-requests-sync", "withdrawal-poll", "wb-mp-warehouses-daily",
        "marking-low-stock", "fbs-orders-autopoll", "fbs-orders-full-reconcile",
        "fbs-order-statuses-autopoll", "fbs-marking-verdicts-autopoll",
        "fbs-stock-reconcile", "billing-storage-daily",
    }


@pytest.mark.asyncio
async def test_connected_sellers_isolated_and_http_has_no_open_read_session(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenants = [Tenant(name=f"277-{i}", slug=f"277-{i}") for i in range(2)]
    db_session.add_all(tenants)
    await db_session.commit()
    await seller_with_token(db_session, tenants[0].id, "A failure", "bad")
    first = await seller_with_token(db_session, tenants[0].id, "B success", "first")
    second = await seller_with_token(db_session, tenants[1].id, "C success", "second")
    await seller_with_token(db_session, tenants[0].id, "Disconnected", None)
    await seller_with_token(db_session, tenants[0].id, "Empty", "")
    # WMS-548 R5, R10: обе уже подключённые (до задачи) — их единственная
    # карточка уже выбрана (есть Product с её nmID), поэтому проход обновляет
    # её как раньше, а не пропускает как невыбранную.
    await sync.upsert_products_from_wb_cards(db_session, first.tenant_id, first.id, [{
        "nmID": 277, "vendorCode": "SAME-SKU", "title": "Synthetic (placeholder)",
        "sizes": [{"chrtID": 277, "techSize": "0", "skus": ["SAME-BAR"]}],
    }])
    await sync.upsert_products_from_wb_cards(db_session, second.tenant_id, second.id, [{
        "nmID": 277, "vendorCode": "SAME-SKU", "title": "Synthetic (placeholder)",
        "sizes": [{"chrtID": 277, "techSize": "0", "skus": ["SAME-BAR"]}],
    }])
    await db_session.commit()
    opened = 0

    @asynccontextmanager
    async def tracked_session():
        nonlocal opened
        async with SessionLocal() as session:
            opened += 1
            try:
                yield session
            finally:
                opened -= 1

    calls: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        assert opened == 0  # All enumeration/token sessions ended before HTTP.
        calls.append(request)
        token = request.headers["Authorization"]
        if request.url.path == "/content/v2/get/cards/list":
            if token == "bad":
                return httpx.Response(401, json={"error": "synthetic"})
            return httpx.Response(200, json={"cards": [{
                "nmID": 277, "vendorCode": "SAME-SKU", "title": "Synthetic",
                "sizes": [{"chrtID": 277, "techSize": "0", "skus": ["SAME-BAR"]}],
            }]})
        if request.url.path == "/content/v2/object/parent/all":
            assert token in {"first", "second"}
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/content/v2/object/all":
            assert token in {"first", "second"}
            assert request.url.params == {"limit": "1000", "offset": "0"}
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected WB request: {request.method} {request.url}")

    monkeypatch.setattr(sync, "SessionLocal", tracked_session)
    monkeypatch.setattr(sync.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync.run_wb_products_sync_all_sellers()
    assert summary["sellers_total"] == 3
    assert summary["sellers_ok"] == 2 and summary["sellers_failed"] == 1
    card_calls = [
        request for request in calls if request.url.path == "/content/v2/get/cards/list"
    ]
    parent_calls = [
        request for request in calls if request.url.path == "/content/v2/object/parent/all"
    ]
    subject_calls = [
        request for request in calls if request.url.path == "/content/v2/object/all"
    ]
    # Each connected seller gets exactly one card-list request under its own
    # token. Category reads are additional WMS-658 evidence requests, never a
    # replacement for card selection and never authorized as the failed seller.
    assert sorted(request.headers["Authorization"] for request in card_calls) == [
        "bad", "first", "second"
    ]
    assert sorted(request.headers["Authorization"] for request in parent_calls) == [
        "first", "second"
    ]
    assert sorted(request.headers["Authorization"] for request in subject_calls) == [
        "first", "second"
    ]
    products = list((await db_session.scalars(select(Product))).all())
    assert {(p.tenant_id, p.seller_id) for p in products} == {
        (first.tenant_id, first.id), (second.tenant_id, second.id),
    }
    assert all(not p.fbs_stock_sync_enabled for p in products)
    assert await db_session.scalar(select(func.count(SellerWildberriesImportedCard.id))) == 2
    assert await db_session.scalar(select(func.count(InventoryBalance.id))) == 0
    assert await db_session.scalar(select(func.count(InventoryMovement.id))) == 0
    # The next hour updates those same rows, including equal SKUs in two tenants.
    await db_session.commit()
    repeated = await sync.run_wb_products_sync_all_sellers()
    assert repeated["sellers_ok"] == 2
    assert all(item["products_created"] == 0 for item in repeated["ok"])
    assert await db_session.scalar(select(func.count(Product.id))) == 2
    assert await db_session.scalar(select(func.count(SellerWildberriesImportedCard.id))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("job_status", ["pending", "running"])
async def test_active_manual_job_skipped_then_terminal_job_allows_import(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, job_status: str,
) -> None:
    tenant = Tenant(name="277 manual", slug="277-manual")
    db_session.add(tenant)
    await db_session.commit()
    seller = await seller_with_token(db_session, tenant.id, "Manual", "synthetic")
    job, created = await jobs.create_or_get_seller_catalog_sync_job(
        db_session,
        tenant.id,
        seller.id,
        job_type=jobs.JOB_TYPE_WILDBERRIES_CARDS_SYNC,
        marketplace="wildberries",
    )
    assert created
    if job_status == "running":
        job.status = jobs.JOB_STATUS_RUNNING
        job.started_at = datetime.now(UTC)
        await db_session.commit()
    calls: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/content/v2/get/cards/list":
            return httpx.Response(200, json={"cards": []})
        if request.url.path in {
            "/content/v2/object/parent/all",
            "/content/v2/object/all",
        }:
            return httpx.Response(200, json={"data": []})
        raise AssertionError(f"unexpected WB request: {request.method} {request.url}")

    monkeypatch.setattr(sync.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync.run_wb_products_sync_all_sellers()
    assert summary["skipped"][0]["reason"] == "manual_sync_active"
    assert not calls
    await db_session.refresh(job)
    assert job.status == job_status  # Scheduler never rewrites manual job state.
    job.status = "failed"
    await db_session.commit()
    summary = await sync.run_wb_products_sync_all_sellers()
    assert summary["sellers_ok"] == 1
    assert [request.url.path for request in calls] == [
        "/content/v2/get/cards/list",
        "/content/v2/object/parent/all",
        "/content/v2/object/all",
    ]
    assert all(request.headers["Authorization"] == "synthetic" for request in calls)


@pytest.mark.asyncio
async def test_disconnect_during_http_discards_response(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = Tenant(name="277 disconnect", slug="277-disconnect")
    db_session.add(tenant)
    await db_session.commit()
    seller = await seller_with_token(db_session, tenant.id, "Disconnect", "synthetic")

    async def upstream(request: httpx.Request) -> httpx.Response:
        async with SessionLocal() as session:
            row = await session.get(SellerWildberriesCredentials, seller.id)
            assert row is not None
            row.content_token_encrypted = None
            await session.commit()
        return httpx.Response(200, json={"cards": [{
            "nmID": 277, "vendorCode": "REMOVED", "sizes": [{"skus": ["REMOVED"]}],
        }]})

    monkeypatch.setattr(sync.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync.run_wb_products_sync_all_sellers()
    assert summary["skipped"][0]["reason"] == "content_token_changed"
    assert await db_session.scalar(select(func.count(Product.id))) == 0
    assert await db_session.scalar(select(func.count(SellerWildberriesImportedCard.id))) == 0


@pytest.mark.asyncio
async def test_scheduled_old_generation_cannot_overwrite_new_foreground_job(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = Tenant(name="615 scheduled fence", slug="615-scheduled-fence")
    db_session.add(tenant)
    await db_session.commit()
    seller = await seller_with_token(db_session, tenant.id, "Scheduled fence", "old-key")
    await sync.upsert_products_from_wb_cards(
        db_session,
        tenant.id,
        seller.id,
        [
            {
                "nmID": 615,
                "vendorCode": "WMS-615",
                "title": "before-sync",
                "sizes": [
                    {"chrtID": 61500, "techSize": "M", "skus": ["barcode-615"]}
                ],
            }
        ],
    )

    old_fetch_started = asyncio.Event()
    release_old_fetch = asyncio.Event()

    async def fetch_cards(_client: object, *, api_token: str):
        if api_token == "old-key":
            old_fetch_started.set()
            await release_old_fetch.wait()
            title = "stale-scheduled"
        else:
            assert api_token == "new-key"
            title = "fresh-foreground"
        return (
            [
                {
                    "nmID": 615,
                    "vendorCode": "WMS-615",
                    "title": title,
                    "sizes": [
                        {
                            "chrtID": 61500,
                            "techSize": "M",
                            "skus": ["barcode-615"],
                        }
                    ],
                }
            ],
            False,
        )

    monkeypatch.setattr(sync, "fetch_all_cards", fetch_cards)
    scheduled = asyncio.create_task(sync.run_wb_products_sync_all_sellers())
    await old_fetch_started.wait()

    async with SessionLocal() as session:
        row = await patch_seller_tokens(
            session,
            tenant.id,
            seller.id,
            content_api_token="new-key",
            supplies_api_token=SKIP,
        )
        assert row is not None
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant.id,
            seller.id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        replacement_id = replacement.id

    await jobs.run_wildberries_cards_sync_job(replacement_id)
    release_old_fetch.set()
    summary = await scheduled

    assert summary["sellers_ok"] == 0
    assert summary["sellers_skipped"] == 1
    assert summary["skipped"][0]["reason"] == "content_token_changed"
    async with SessionLocal() as session:
        product = await session.scalar(
            select(Product).where(
                Product.tenant_id == tenant.id,
                Product.seller_id == seller.id,
                Product.wb_nm_id == 615,
            )
        )
        imported = await session.scalar(
            select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.seller_id == seller.id,
                SellerWildberriesImportedCard.nm_id == 615,
            )
        )
        catalog_jobs = list(
            (
                await session.scalars(
                    select(BackgroundJob)
                    .where(
                        BackgroundJob.tenant_id == tenant.id,
                        BackgroundJob.job_type.in_(jobs.WB_CATALOG_JOB_TYPES),
                        BackgroundJob.payload_json["seller_id"].as_string()
                        == str(seller.id),
                    )
                    .order_by(BackgroundJob.created_at)
                )
            ).all()
        )
        assert product is not None and product.name == "fresh-foreground"
        assert imported is not None and imported.title == "fresh-foreground"
        assert len(catalog_jobs) == 2
        replacement_job = next(job for job in catalog_jobs if job.id == replacement_id)
        old_job = next(job for job in catalog_jobs if job.id != replacement_id)
        assert old_job.status == jobs.JOB_STATUS_FAILED
        assert old_job.error_message == "catalog_job_credentials_changed"
        assert old_job.result_json is None
        assert replacement_job.status == jobs.JOB_STATUS_DONE
