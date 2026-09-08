"""WMS-277: existing WB catalogue import scheduled without stock operations."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
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
from app.services import wildberries_product_sync_service as sync
from app.services.integration_fernet import encrypt_secret


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

    entry = celery_app.conf.beat_schedule["wb-catalog-hourly"]
    assert entry["task"] == run_wb_catalog_hourly_sync_task.name
    assert entry["schedule"].minute == {17}
    assert entry["schedule"].hour == set(range(24))


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

    calls = []

    def upstream(request: httpx.Request) -> httpx.Response:
        assert opened == 0  # All enumeration/token sessions ended before HTTP.
        calls.append(request.headers["Authorization"])
        if calls[-1] == "bad":
            return httpx.Response(401, json={"error": "synthetic"})
        return httpx.Response(200, json={"cards": [{
            "nmID": 277, "vendorCode": "SAME-SKU", "title": "Synthetic",
            "sizes": [{"chrtID": 277, "techSize": "0", "skus": ["SAME-BAR"]}],
        }]})

    monkeypatch.setattr(sync, "SessionLocal", tracked_session)
    monkeypatch.setattr(sync.httpx, "AsyncClient", partial(
        httpx.AsyncClient, transport=httpx.MockTransport(upstream),
    ))
    summary = await sync.run_wb_products_sync_all_sellers()
    assert summary["sellers_total"] == 3
    assert summary["sellers_ok"] == 2 and summary["sellers_failed"] == 1
    assert sorted(calls) == ["bad", "first", "second"]
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
    job = BackgroundJob(tenant_id=tenant.id, job_type="wildberries_cards_sync",
                        status=job_status, payload_json={"seller_id": str(seller.id)})
    db_session.add(job)
    await db_session.commit()
    calls = []

    def upstream(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"cards": []})

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
    assert summary["sellers_ok"] == 1 and len(calls) == 1


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
