"""WMS-615 durable catalog job leases, claims and WB entrypoint collision."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.background_job import BackgroundJob
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.seller_ozon_imported_card import SellerOzonImportedCard
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.tenant import Tenant
from app.services import background_job_service as jobs
from app.services import ozon_product_import_service as ozon_import
from app.services import ozon_provider_factory
from app.services import wildberries_product_sync_service as wb_product_sync
from app.services.integration_fernet import encrypt_secret
from app.services.wildberries_credentials_service import SKIP, patch_seller_tokens
from app.tasks.background_jobs import run_wildberries_cards_sync_task


async def _seller() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionLocal() as session:
        tenant = Tenant(name="Catalog lease", slug=f"catalog-lease-{uuid.uuid4().hex[:8]}")
        seller = Seller(tenant=tenant, name="Seller")
        session.add_all([tenant, seller])
        await session.commit()
        return tenant.id, seller.id


def _wb_card(nm_id: int) -> dict[str, object]:
    return {
        "nmID": nm_id,
        "vendorCode": f"vendor-{nm_id}",
        "title": f"WB {nm_id}",
        "sizes": [
            {
                "chrtID": nm_id * 100,
                "techSize": "M",
                "skus": [f"barcode-{nm_id}"],
            }
        ],
    }


def _ozon_card(product_id: str) -> dict[str, object]:
    return {
        "id": product_id,
        "sku": f"sku-{product_id}",
        "offer_id": f"offer-{product_id}",
        "name": f"Ozon {product_id}",
    }


async def _save_wb_key(tenant_id: uuid.UUID, seller_id: uuid.UUID, key: str) -> None:
    async with SessionLocal() as session:
        row = await patch_seller_tokens(
            session,
            tenant_id,
            seller_id,
            content_api_token=key,
            supplies_api_token=SKIP,
        )
        assert row is not None


async def _save_ozon_key(
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    *,
    client_id: str,
    api_key: str,
) -> None:
    async with SessionLocal() as session:
        account = await session.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
                MarketplaceAccount.account_slot == "primary",
            )
        )
        now = datetime.now(UTC)
        if account is None:
            account = MarketplaceAccount(
                tenant_id=tenant_id,
                seller_id=seller_id,
                marketplace="ozon",
                account_slot="primary",
            )
            session.add(account)
        account.external_account_id = client_id
        account.secret_encrypted = encrypt_secret(api_key)
        account.is_active = True
        account.validation_status = "valid"
        account.credentials_updated_at = now
        await session.commit()


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

    async def slow_sync(session, actual_tenant_id, actual_seller_id, http_client, **_kwargs):
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
async def test_expired_worker_cannot_overwrite_replacement_snapshot_or_product(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id = await _seller()
    await _save_wb_key(tenant_id, seller_id, "old-lease-key")
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="operator-name",
            sku_code="operator-sku",
            wb_nm_id=101,
            wb_chrt_id=10100,
            wb_barcode="barcode-101",
        )
        session.add(product)
        await session.commit()
        product_id = product.id
        old_job, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        old_job_id = old_job.id

    old_fetch_started = asyncio.Event()
    release_old_fetch = asyncio.Event()
    fetch_count = 0

    async def fetch_cards(_client, *, api_token):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            assert api_token == "old-lease-key"
            old_fetch_started.set()
            await release_old_fetch.wait()
            return [_wb_card(101)], False
        return [_wb_card(202)], False

    monkeypatch.setattr(wb_product_sync, "fetch_all_cards", fetch_cards)
    old_worker = asyncio.create_task(jobs.run_wildberries_cards_sync_job(old_job_id))
    await old_fetch_started.wait()

    monkeypatch.setattr(jobs, "CATALOG_SYNC_JOB_LEASE", timedelta(0))
    async with SessionLocal() as session:
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        replacement_id = replacement.id
    await jobs.run_wildberries_cards_sync_job(replacement_id)
    release_old_fetch.set()
    await old_worker

    async with SessionLocal() as session:
        old = await session.get(BackgroundJob, old_job_id)
        replacement = await session.get(BackgroundJob, replacement_id)
        imported_ids = set(
            await session.scalars(
                select(SellerWildberriesImportedCard.nm_id).where(
                    SellerWildberriesImportedCard.seller_id == seller_id
                )
            )
        )
        stored_product = await session.get(Product, product_id)
        assert old is not None
        assert old.status == jobs.JOB_STATUS_FAILED
        assert old.error_message == "catalog_job_lease_expired"
        assert old.result_json is None
        assert replacement is not None and replacement.status == jobs.JOB_STATUS_DONE
        assert imported_ids == {202}
        assert stored_product is not None and stored_product.name == "operator-name"


@pytest.mark.asyncio
async def test_wb_key_change_replaces_running_generation_and_discards_old_response(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id = await _seller()
    await _save_wb_key(tenant_id, seller_id, "wb-key-v1")
    async with SessionLocal() as session:
        old_job, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        old_job_id = old_job.id

    old_fetch_started = asyncio.Event()
    release_old_fetch = asyncio.Event()

    async def fetch_cards(_client, *, api_token):
        if api_token == "wb-key-v1":
            old_fetch_started.set()
            await release_old_fetch.wait()
            return [_wb_card(301)], False
        assert api_token == "wb-key-v2"
        return [_wb_card(302)], False

    monkeypatch.setattr(wb_product_sync, "fetch_all_cards", fetch_cards)
    old_worker = asyncio.create_task(jobs.run_wildberries_cards_sync_job(old_job_id))
    await old_fetch_started.wait()
    await _save_wb_key(tenant_id, seller_id, "wb-key-v2")
    async with SessionLocal() as session:
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert created
        replacement_id = replacement.id
    await jobs.run_wildberries_cards_sync_job(replacement_id)
    release_old_fetch.set()
    await old_worker

    async with SessionLocal() as session:
        old = await session.get(BackgroundJob, old_job_id)
        replacement = await session.get(BackgroundJob, replacement_id)
        imported_ids = set(
            await session.scalars(
                select(SellerWildberriesImportedCard.nm_id).where(
                    SellerWildberriesImportedCard.seller_id == seller_id
                )
            )
        )
        assert old is not None
        assert old.status == jobs.JOB_STATUS_FAILED
        assert old.error_message == "catalog_job_credentials_changed"
        assert old.result_json is None
        assert replacement is not None and replacement.status == jobs.JOB_STATUS_DONE
        assert imported_ids == {302}


@pytest.mark.asyncio
async def test_wb_supplies_only_change_does_not_invalidate_catalog_generation(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id = await _seller()
    await _save_wb_key(tenant_id, seller_id, "wb-content-key")
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
        generation = (job.payload_json or {})["credentials_generation"]

    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()

    async def fetch_cards(_client, *, api_token):
        assert api_token == "wb-content-key"
        fetch_started.set()
        await release_fetch.wait()
        return [_wb_card(401)], False

    monkeypatch.setattr(wb_product_sync, "fetch_all_cards", fetch_cards)
    worker = asyncio.create_task(jobs.run_wildberries_cards_sync_job(job_id))
    await fetch_started.wait()
    async with SessionLocal() as session:
        row = await patch_seller_tokens(
            session,
            tenant_id,
            seller_id,
            content_api_token=SKIP,
            supplies_api_token="wb-supplies-only",
        )
        assert row is not None
        same, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_SELLER_WB_CATALOG_SYNC,
            marketplace="wildberries",
        )
        assert not created
        assert same.id == job_id
        assert (same.payload_json or {})["credentials_generation"] == generation
    release_fetch.set()
    await worker

    async with SessionLocal() as session:
        stored = await session.get(BackgroundJob, job_id)
        imported = await session.scalar(
            select(SellerWildberriesImportedCard).where(
                SellerWildberriesImportedCard.seller_id == seller_id,
                SellerWildberriesImportedCard.nm_id == 401,
            )
        )
        assert stored is not None
        assert stored.status == jobs.JOB_STATUS_DONE
        assert stored.finished_at is not None
        assert imported is not None


@pytest.mark.asyncio
async def test_ozon_disconnect_terminalizes_running_job_and_allows_immediate_restart(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, seller_id = await _seller()
    await _save_ozon_key(
        tenant_id, seller_id, client_id="disconnect-client", api_key="disconnect-key"
    )
    async with SessionLocal() as session:
        old_job, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_OZON_CATALOG_SYNC,
            marketplace="ozon",
        )
        assert created
        old_job_id = old_job.id

    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    fetch_count = 0

    async def fetch_cards(_provider, *, client_id, api_key):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            assert (client_id, api_key) == ("disconnect-client", "disconnect-key")
            fetch_started.set()
            await release_fetch.wait()
            return [_ozon_card("stale-disconnected")]
        assert (client_id, api_key) == ("reconnected-client", "reconnected-key")
        return [_ozon_card("fresh-reconnected")]

    monkeypatch.setattr(ozon_import, "fetch_product_cards", fetch_cards)
    monkeypatch.setattr(ozon_provider_factory, "build_ozon_provider", lambda: object())
    old_worker = asyncio.create_task(jobs.run_ozon_catalog_sync_job(old_job_id))
    await fetch_started.wait()
    async with SessionLocal() as session:
        account = await session.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
            )
        )
        assert account is not None
        account.external_account_id = None
        account.secret_encrypted = None
        account.is_active = False
        account.validation_status = "not_configured"
        account.credentials_updated_at = None
        await session.commit()
    release_fetch.set()
    await old_worker

    async with SessionLocal() as session:
        old = await session.get(BackgroundJob, old_job_id)
        account = await session.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
            )
        )
        stale_snapshot_count = await session.scalar(
            select(func.count(SellerOzonImportedCard.id)).where(
                SellerOzonImportedCard.seller_id == seller_id
            )
        )
        assert old is not None
        assert old.status == jobs.JOB_STATUS_FAILED
        assert old.error_message == "catalog_job_credentials_changed"
        assert old.finished_at is not None
        assert old.result_json is None
        assert account is not None and not account.is_active
        assert stale_snapshot_count == 0

    await _save_ozon_key(
        tenant_id,
        seller_id,
        client_id="reconnected-client",
        api_key="reconnected-key",
    )
    async with SessionLocal() as session:
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_OZON_CATALOG_SYNC,
            marketplace="ozon",
        )
        assert created
        replacement_id = replacement.id
    await jobs.run_ozon_catalog_sync_job(replacement_id)

    async with SessionLocal() as session:
        replacement = await session.get(BackgroundJob, replacement_id)
        imported_ids = set(
            await session.scalars(
                select(SellerOzonImportedCard.ozon_product_id).where(
                    SellerOzonImportedCard.seller_id == seller_id
                )
            )
        )
        assert replacement is not None
        assert replacement.status == jobs.JOB_STATUS_DONE
        assert imported_ids == {"fresh-reconnected"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("replacement_reason", "expected_error"),
    [
        ("credentials", "catalog_job_credentials_changed"),
        ("lease", "catalog_job_lease_expired"),
    ],
)
async def test_ozon_replacement_fences_old_snapshot_and_link_updates(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    replacement_reason: str,
    expected_error: str,
) -> None:
    tenant_id, seller_id = await _seller()
    await _save_ozon_key(tenant_id, seller_id, client_id="client-v1", api_key="ozon-key-v1")
    async with SessionLocal() as session:
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="linked product",
            sku_code="linked-product",
        )
        session.add(product)
        await session.flush()
        link = ProductMarketplaceLink(
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product.id,
            marketplace="ozon",
            external_sku="sku-old",
        )
        session.add(link)
        await session.commit()
        link_id = link.id
        old_job, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_OZON_CATALOG_SYNC,
            marketplace="ozon",
        )
        assert created
        old_job_id = old_job.id

    old_fetch_started = asyncio.Event()
    release_old_fetch = asyncio.Event()
    fetch_count = 0

    async def fetch_cards(_provider, *, client_id, api_key):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count == 1:
            assert (client_id, api_key) == ("client-v1", "ozon-key-v1")
            old_fetch_started.set()
            await release_old_fetch.wait()
            return [
                {
                    **_ozon_card("old-product"),
                    "sku": "sku-old",
                }
            ]
        expected_credentials = (
            ("client-v2", "ozon-key-v2")
            if replacement_reason == "credentials"
            else ("client-v1", "ozon-key-v1")
        )
        assert (client_id, api_key) == expected_credentials
        return [_ozon_card("new-product")]

    monkeypatch.setattr(ozon_import, "fetch_product_cards", fetch_cards)
    monkeypatch.setattr(ozon_provider_factory, "build_ozon_provider", lambda: object())
    old_worker = asyncio.create_task(jobs.run_ozon_catalog_sync_job(old_job_id))
    await old_fetch_started.wait()
    if replacement_reason == "credentials":
        await _save_ozon_key(tenant_id, seller_id, client_id="client-v2", api_key="ozon-key-v2")
    else:
        monkeypatch.setattr(jobs, "CATALOG_SYNC_JOB_LEASE", timedelta(0))
    async with SessionLocal() as session:
        replacement, created = await jobs.create_or_get_seller_catalog_sync_job(
            session,
            tenant_id,
            seller_id,
            job_type=jobs.JOB_TYPE_OZON_CATALOG_SYNC,
            marketplace="ozon",
        )
        assert created
        replacement_id = replacement.id
    await jobs.run_ozon_catalog_sync_job(replacement_id)
    release_old_fetch.set()
    await old_worker

    async with SessionLocal() as session:
        old = await session.get(BackgroundJob, old_job_id)
        replacement = await session.get(BackgroundJob, replacement_id)
        imported_ids = set(
            await session.scalars(
                select(SellerOzonImportedCard.ozon_product_id).where(
                    SellerOzonImportedCard.seller_id == seller_id
                )
            )
        )
        stored_link = await session.get(ProductMarketplaceLink, link_id)
        account = await session.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
            )
        )
        assert old is not None
        assert old.status == jobs.JOB_STATUS_FAILED
        assert old.error_message == expected_error
        assert old.result_json is None
        assert replacement is not None and replacement.status == jobs.JOB_STATUS_DONE
        assert imported_ids == {"new-product"}
        assert stored_link is not None and stored_link.external_product_id is None
        assert account is not None and account.last_synced_at is not None
        assert account.last_sync_error_code is None


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
