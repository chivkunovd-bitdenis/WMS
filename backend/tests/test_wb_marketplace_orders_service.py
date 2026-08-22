"""Tests for WB Marketplace FBS orders service (supply sync via supplies list).

TC-NEW-SUPPLY-SYNC-001 — adoption with supplies list: done=True updates status and name
TC-NEW-SUPPLY-SYNC-002 — adoption uses supplies_dict without individual fetch
TC-NEW-SUPPLY-SYNC-003 — supplies list failure: adoption falls back without exception
TC-NEW-SUPPLY-SYNC-004 — pagination: multiple pages merged into one supplies dict
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FBS_ORDER_STATUS_ASSEMBLING, FbsOrder
from app.models.fbs_stock_pool_debit import FbsStockPoolDebit
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FbsSupply,
)
from app.models.product import Product
from app.services import fbs_autopoll_service
from app.services import wb_marketplace_orders_service as orders_service
from app.services.wb_marketplace_orders_service import link_confirmed_orders_to_wb_supplies
from app.services.wildberries_errors import WildberriesClientError
from app.tasks import background_jobs
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding


class _SqliteConnection:
    dialect = type("Dialect", (), {"name": "sqlite"})()


class _SyncSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def connection(self) -> object:
        return _SqliteConnection()


# TC-NEW-WB-SCHEDULE-001: new/reconcile have independent periods and flights.
def test_wb_order_schedule_and_single_flight_are_per_kind() -> None:
    from app.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert schedule["wb-orders-new"]["schedule"] == 180.0
    assert schedule["wb-orders-reconcile"]["schedule"] == 3600.0
    assert "fbs-orders-autopoll" not in schedule
    assert fbs_autopoll_service._sync_locks is not None
    assert celery_app.conf.task_routes["wms.wb_orders_new"]["queue"] == "wb_sync"
    assert celery_app.conf.task_routes["wms.wb_orders_reconcile"]["queue"] == "wb_sync"


def test_wb_order_dispatch_spreads_each_kind_across_its_interval() -> None:
    targets = [
        fbs_autopoll_service.SellerPollTarget(uuid.uuid4(), uuid.uuid4())
        for _ in range(3)
    ]
    task = Mock()

    background_jobs._dispatch_seller_syncs_evenly(
        task,
        targets,
        interval_seconds=180.0,
    )

    assert task.apply_async.call_args_list == [
        call(
            args=(str(target.tenant_id), str(target.seller_id)),
            countdown=index * 60.0,
        )
        for index, target in enumerate(targets)
    ]

    task.reset_mock()
    background_jobs._dispatch_seller_syncs_evenly(
        task,
        targets,
        interval_seconds=3600.0,
    )
    assert [item.kwargs["countdown"] for item in task.apply_async.call_args_list] == [
        0.0,
        1200.0,
        2400.0,
    ]


def test_wb_order_sync_queue_has_two_worker_slots_in_production() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    compose = compose_path.read_text(encoding="utf-8")
    worker_block = compose.split("\n  wb_sync_worker:", maxsplit=1)[1].split(
        "\n  print_worker:", maxsplit=1
    )[0]

    assert '"--queues=wb_sync"' in worker_block
    assert '"--concurrency=2"' in worker_block


def test_wb_order_tasks_invoke_new_and_reconcile_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    new_job = AsyncMock(return_value=True)
    reconcile_job = AsyncMock(return_value=True)
    monkeypatch.setattr(fbs_autopoll_service, "sync_new_orders_for_seller_job", new_job)
    monkeypatch.setattr(
        fbs_autopoll_service, "reconcile_orders_for_seller_job", reconcile_job
    )

    background_jobs.run_wb_orders_new_task.run(str(tenant_id), str(seller_id))
    background_jobs.run_wb_orders_reconcile_task.run(str(tenant_id), str(seller_id))

    new_job.assert_awaited_once_with(tenant_id, seller_id)
    reconcile_job.assert_awaited_once_with(tenant_id, seller_id)


@pytest.mark.asyncio
async def test_wb_order_flights_allow_new_and_reconcile_together() -> None:
    seller_id = uuid.uuid4()
    async with fbs_autopoll_service.seller_sync_flight(seller_id, "new") as new_acquired:
        async with fbs_autopoll_service.seller_sync_flight(
            seller_id, "reconcile"
        ) as reconcile_acquired:
            assert new_acquired is True
            assert reconcile_acquired is True
        async with fbs_autopoll_service.seller_sync_flight(seller_id, "new") as duplicate:
            assert duplicate is False


@pytest.mark.asyncio
async def test_wb_order_flight_uses_distinct_postgres_keys_per_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

    class _Session:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def connection(self) -> _Connection:
            return _Connection()

        async def scalar(self, statement: object, params: dict[str, object]) -> bool:
            self.calls.append(str(params["lock_key"]))
            return True

    session = _Session()
    monkeypatch.setattr(
        fbs_autopoll_service, "SessionLocal", lambda: _SessionContext(session)
    )
    seller_id = uuid.uuid4()
    async with (
        fbs_autopoll_service.seller_sync_flight(seller_id, "new") as new_acquired,
        fbs_autopoll_service.seller_sync_flight(
            seller_id, "reconcile"
        ) as reconcile_acquired,
    ):
        assert new_acquired and reconcile_acquired
    assert session.calls[0] != session.calls[2]


@pytest.mark.asyncio
async def test_wb_order_jobs_do_not_take_seller_wide_lock_during_http_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    new_sync = AsyncMock(return_value={})
    reconcile_sync = AsyncMock(return_value={})

    monkeypatch.setattr(
        fbs_autopoll_service, "SessionLocal", lambda: _SessionContext(_SyncSession())
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda: _AsyncClientContext())
    monkeypatch.setattr(fbs_autopoll_service, "sync_new_orders_for_seller", new_sync)
    monkeypatch.setattr(
        fbs_autopoll_service, "reconcile_orders_for_seller", reconcile_sync
    )
    monkeypatch.setattr(
        fbs_autopoll_service,
        "wb_seller_lock",
        lambda *_args: (_ for _ in ()).throw(AssertionError("seller-wide lock used")),
    )

    assert await fbs_autopoll_service.sync_new_orders_for_seller_job(tenant_id, seller_id)
    assert await fbs_autopoll_service.reconcile_orders_for_seller_job(tenant_id, seller_id)
    new_sync.assert_awaited_once()
    reconcile_sync.assert_awaited_once()


class _SessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


class _AsyncClientContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class _PoolRowResult:
    def __init__(self, pool: FbsBindingStockPool) -> None:
        self._pool = pool

    def scalar_one_or_none(self) -> FbsBindingStockPool:
        return self._pool


class _LockedPoolTransaction:
    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock

    async def __aenter__(self) -> None:
        await self._lock.acquire()

    async def __aexit__(self, *_args: object) -> None:
        self._lock.release()


class _ConcurrentPoolDebitSession:
    """Minimal session double that models a database row lock for one pool."""

    def __init__(
        self,
        pool: FbsBindingStockPool,
        lock: asyncio.Lock,
        ledger: list[FbsStockPoolDebit],
    ) -> None:
        self._pool = pool
        self._lock = lock
        self._ledger = ledger

    def begin_nested(self) -> _LockedPoolTransaction:
        return _LockedPoolTransaction(self._lock)

    async def execute(self, statement: object) -> _PoolRowResult:
        # The test double serializes only a query that explicitly requests the
        # same row lock PostgreSQL uses in production.
        assert getattr(statement, "_for_update_arg", None) is not None
        return _PoolRowResult(self._pool)

    def add(self, row: FbsStockPoolDebit) -> None:
        self._ledger.append(row)

    async def flush(self) -> None:
        return None


# TC-NEW-WB-SYNC-005: new/reconcile may debit different orders from one pool concurrently.
@pytest.mark.asyncio
async def test_new_and_reconcile_serialize_different_order_debits_on_one_pool() -> None:
    tenant_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    product_id = uuid.uuid4()
    pool = FbsBindingStockPool(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        binding_id=binding_id,
        product_id=product_id,
        quantity=10,
    )
    ledger: list[FbsStockPoolDebit] = []
    row_lock = asyncio.Lock()
    new_session = _ConcurrentPoolDebitSession(pool, row_lock, ledger)
    reconcile_session = _ConcurrentPoolDebitSession(pool, row_lock, ledger)
    new_order = SimpleNamespace(id=uuid.uuid4(), product_id=product_id)
    reconcile_order = SimpleNamespace(id=uuid.uuid4(), product_id=product_id)

    new_result, reconcile_result = await asyncio.gather(
        orders_service._debit_stock_pool_once(  # type: ignore[arg-type]
            new_session, tenant_id, new_order, binding_id, {"debited": 0, "shortfall": 0}
        ),
        orders_service._debit_stock_pool_once(  # type: ignore[arg-type]
            reconcile_session,
            tenant_id,
            reconcile_order,
            binding_id,
            {"debited": 0, "shortfall": 0},
        ),
    )

    assert new_result == {"debited": 1, "shortfall": 0}
    assert reconcile_result == {"debited": 1, "shortfall": 0}
    assert pool.quantity == 8
    assert {row.order_id for row in ledger} == {new_order.id, reconcile_order.id}


# TC-NEW-WB-SYNC-001: new sync uses only /orders/new and performs an idempotent upsert.
@pytest.mark.asyncio
async def test_new_sync_does_not_fetch_paginated_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _SyncSession()
    seller_id = uuid.uuid4()
    new_fetch = AsyncMock(return_value=[{"id": 1}])
    page_fetch = AsyncMock(side_effect=AssertionError("full order list must not be fetched"))
    upsert = AsyncMock(return_value=(object(), False))
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_new", new_fetch)
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "upsert_order_from_wb_row", upsert)

    result = await orders_service.sync_new_orders_for_seller(
        session, uuid.uuid4(), seller_id, object()  # type: ignore[arg-type]
    )

    assert result["orders_received"] == 1
    new_fetch.assert_awaited_once()
    page_fetch.assert_not_awaited()
    upsert.assert_awaited_once()


# TC-NEW-WB-SYNC-004: the existing manual sync remains a full status/supply reconciliation.
@pytest.mark.asyncio
async def test_legacy_manual_sync_keeps_status_and_supply_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SyncSession()
    new_fetch = AsyncMock(return_value=[])
    page_fetch = AsyncMock(return_value=([], None))
    status_sync = AsyncMock(return_value=2)
    supply_link = AsyncMock(return_value={"supply_link_candidates": 1})
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_new", new_fetch)
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "sync_order_statuses", status_sync)
    monkeypatch.setattr(
        orders_service, "link_confirmed_orders_to_wb_supplies", supply_link
    )

    result = await orders_service.sync_seller_orders(
        session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
    )

    new_fetch.assert_awaited_once()
    page_fetch.assert_awaited_once()
    status_sync.assert_awaited_once()
    supply_link.assert_awaited_once()
    assert result["statuses_updated"] == 2
    assert result["supply_link_candidates"] == 1


# TC-NEW-WB-SYNC-002: reconcile consumes all cursors and never reports success after a page error.
@pytest.mark.asyncio
async def test_reconcile_walks_cursor_and_fails_incomplete_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SyncSession()
    pages = [([{"id": 1}], 10), ([{"id": 2}], 20), ([], None)]
    page_fetch = AsyncMock(side_effect=pages)
    upsert = AsyncMock(side_effect=[(object(), True), (object(), False)])
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "upsert_order_from_wb_row", upsert)
    link_supplies = AsyncMock(return_value={})
    monkeypatch.setattr(orders_service, "link_confirmed_orders_to_wb_supplies", link_supplies)

    result = await orders_service.reconcile_orders_for_seller(
        session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
    )

    assert result["orders_received"] == 2
    assert [call.kwargs["next_token"] for call in page_fetch.await_args_list] == [None, 10, 20]
    assert session.commit.await_count == 2

    page_fetch.side_effect = [([{"id": 3}], 10), WildberriesClientError("upstream_error")]
    upsert.side_effect = [(object(), False)]
    with pytest.raises(orders_service.WbMarketplaceOrdersError):
        await orders_service.reconcile_orders_for_seller(
            session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
        )
    assert session.rollback.await_count == 1
    # An incomplete pass must not perform the post-reconciliation supply link.
    # The previous successful run already called it once; the failed run must
    # leave that count unchanged.
    assert link_supplies.await_count == 1


@pytest.mark.asyncio
async def test_reconcile_rejects_a_repeated_next_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SyncSession()
    page_fetch = AsyncMock(side_effect=[([{"id": 1}], 10), ([{"id": 2}], 10)])
    link_supplies = AsyncMock(return_value={})
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(
        orders_service, "upsert_order_from_wb_row", AsyncMock(return_value=(object(), False))
    )
    monkeypatch.setattr(orders_service, "link_confirmed_orders_to_wb_supplies", link_supplies)

    with pytest.raises(orders_service.WbMarketplaceOrdersError) as exc_info:
        await orders_service.reconcile_orders_for_seller(
            session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
        )

    assert exc_info.value.code == "cursor_cycle"
    assert page_fetch.await_count == 2
    assert session.commit.await_count == 1
    assert session.rollback.await_count == 1
    link_supplies.assert_not_awaited()


# TC-NEW-WB-SYNC-003: reconcile does not silently stop at an arbitrary page cap.
@pytest.mark.asyncio
async def test_reconcile_walks_past_ten_pages_and_links_supplies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SyncSession()
    pages: list[tuple[list[dict[str, int]], int | None]] = [
        ([{"id": page}], page + 1) for page in range(11)
    ] + [([], None)]
    page_fetch = AsyncMock(side_effect=pages)
    upsert = AsyncMock(return_value=(object(), False))
    link_supplies = AsyncMock(return_value={"supply_linked_orders": 1})
    monkeypatch.setattr(
        orders_service, "_resolve_marketplace_api_token", AsyncMock(return_value="token")
    )
    monkeypatch.setattr(orders_service, "fetch_marketplace_orders_page", page_fetch)
    monkeypatch.setattr(orders_service, "upsert_order_from_wb_row", upsert)
    monkeypatch.setattr(orders_service, "link_confirmed_orders_to_wb_supplies", link_supplies)

    result = await orders_service.reconcile_orders_for_seller(
        session, uuid.uuid4(), uuid.uuid4(), object()  # type: ignore[arg-type]
    )

    assert result["orders_received"] == 11
    assert page_fetch.await_count == 12
    link_supplies.assert_awaited_once()
    assert result["supply_linked_orders"] == 1


async def _register_tenant_and_seller(
    async_client: AsyncClient,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Register tenant, seller, warehouse, and location."""
    suffix = str(time.time_ns())

    # Register tenant
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Test Org {suffix}",
            "slug": f"test-org-{suffix}",
            "admin_email": f"admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # Get tenant ID from /auth/me
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    # Create seller
    seller_resp = await async_client.post(
        "/sellers",
        headers=headers,
        json={"name": f"Test Seller {suffix}"},
    )
    assert seller_resp.status_code in (200, 201), seller_resp.text
    seller_id = uuid.UUID(seller_resp.json()["id"])

    # Set marketplace token
    token_resp = await async_client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=headers,
        json={"marketplace_api_token": "wb-test-token"},
    )
    assert token_resp.status_code == 200, token_resp.text

    # Create warehouse
    wh_resp = await async_client.post(
        "/warehouses",
        headers=headers,
        json={
            "name": f"Test WH {suffix}",
            "code": f"wh-{uuid.uuid4().hex[:8]}",
        },
    )
    assert wh_resp.status_code in (200, 201), wh_resp.text
    warehouse_id = uuid.UUID(wh_resp.json()["id"])

    # Create location
    loc_resp = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": f"A-{uuid.uuid4().hex[:8]}"},
    )
    assert loc_resp.status_code in (200, 201), loc_resp.text
    location_id = uuid.UUID(loc_resp.json()["id"])

    return tenant_id, seller_id, warehouse_id, location_id


async def _create_confirmed_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    product: Product,
    wb_order_id: int,
    wb_supply_id: str,
) -> FbsOrder:
    """Create a confirmed FbsOrder."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    order = FbsOrder(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_id=wb_order_id,
        wb_supply_id=wb_supply_id,
        wb_nm_id=900000 + wb_order_id,
        supplier_status="confirm",
        status=FBS_ORDER_STATUS_ASSEMBLING,
        wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        cargo_type="1",
        wb_office_id=None,
        created_at_wb=now,
        deadline_at=now + timedelta(hours=120),
        mapping_status="missing",
        reserve_status="no_stock",
        pick_status="not_picked",
        pack_status="not_packed",
        sticker_status="no_sticker",
    )
    session.add(order)
    await session.flush()
    return order


async def _create_product(
    async_client: AsyncClient,
    headers: dict[str, str],
    seller_id: str,
    sku: str,
) -> Product:
    """Create a product through the API."""
    resp = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": f"Product {sku}",
            "sku_code": sku,
            "seller_id": seller_id,
            "wb_barcode": f"BAR-{sku}",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(resp.json()["id"]))
        assert product is not None
        return product


# TC-NEW-SUPPLY-SYNC-001: adoption with supplies list: done=True updates status and name
@pytest.mark.asyncio
async def test_adoption_with_supplies_list_done_true(
    async_client: AsyncClient,
) -> None:
    """Supplies list with done=True: new supply created with done status and real name."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product",
            sku_code="TEST-SKU-001",
            wb_nm_id=900001,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1001,
            wb_supply_id="WB-GI-266355621",
        )
        await session.flush()

        # Mock HTTP client that returns supplies list with done=True and name
        # Individual supply detail fetch should NOT be called
        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint
                return httpx.Response(
                    200,
                    json={
                        "supplies": [
                            {
                                "id": "WB-GI-266355621",
                                "name": "ПИТЕР Поставка 18.08.2026",
                                "done": True,
                            }
                        ],
                        "next": None,
                    },
                )
            # Individual supply detail requests should not be made
            if "/api/v3/supplies/" in request.url.path and "?" not in str(request.url):
                return httpx.Response(500, text="Should not call individual fetch")
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with correct status and name from list
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-266355621",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        assert supply.status == FBS_SUPPLY_STATUS_DONE
        assert supply.name == "ПИТЕР Поставка 18.08.2026"
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1


# TC-NEW-SUPPLY-SYNC-002: adoption uses supplies_dict without individual fetch
@pytest.mark.asyncio
async def test_adoption_uses_supplies_dict_no_individual_fetch(
    async_client: AsyncClient,
) -> None:
    """Adoption gets name and status from pre-fetched supplies dict, not individual request."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 2",
            sku_code="TEST-SKU-002",
            wb_nm_id=900002,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1002,
            wb_supply_id="WB-GI-222333444",
        )
        await session.flush()

        # Mock that tracks which endpoints were called
        call_log: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            call_log.append(path)
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint: return data with name and done=False
                return httpx.Response(
                    200,
                    json={
                        "supplies": [
                            {
                                "id": "WB-GI-222333444",
                                "name": "Supply Name From List",
                                "done": False,
                            }
                        ],
                        "next": None,
                    },
                )
            # Any individual supply detail fetch is an error
            if "/api/v3/supplies/" in path:
                raise AssertionError(
                    f"Individual supply fetch should not be called, but got {path}"
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with name from supplies dict
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-222333444",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        # Should have the name from the supplies list, not from fallback
        assert supply.name == "Supply Name From List"
        assert supply.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1
        # Verify no individual fetch was made
        assert not any("/supplies/" in p for p in call_log if "?" not in p)


# TC-NEW-SUPPLY-SYNC-003: supplies list failure: adoption falls back without exception
@pytest.mark.asyncio
async def test_supplies_list_failure_fallback_no_exception(
    async_client: AsyncClient,
) -> None:
    """When supplies list fails, adoption still works with fallback name and assembling status."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 3",
            sku_code="TEST-SKU-003",
            wb_nm_id=900003,
        )
        session.add(product)
        await session.flush()

        # Create confirmed order
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=1003,
            wb_supply_id="WB-GI-333444555",
        )
        await session.flush()

        # Mock that fails on supplies list but can handle individual requests
        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Supplies list endpoint fails
                return httpx.Response(500, text="WB API Error")
            # Individual fetch would be called as fallback, but we don't need to test it
            # since supplies_dict will be empty
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            # Should not raise an exception even if supplies list fails
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify supply was created with fallback name and assembling status
        stmt = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-333444555",
        )
        res = await session.execute(stmt)
        supply = res.scalar_one()

        # Should have fallback name (since supplies_dict was empty)
        assert supply.name == "WB supply WB-GI-333444555"
        assert supply.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert result["supply_links_created"] == 1
        assert result["supply_linked_orders"] == 1


# TC-NEW-SUPPLY-SYNC-004: pagination: multiple pages merged into one supplies dict
@pytest.mark.asyncio
async def test_supplies_pagination_merged_into_dict(
    async_client: AsyncClient,
) -> None:
    """Multiple pages of supplies list are merged into one dictionary."""
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )

    async with SessionLocal() as session:
        # Setup FBS warehouse binding
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
            wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
        )

        # Create product
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Test Product 4",
            sku_code="TEST-SKU-004",
            wb_nm_id=900004,
        )
        session.add(product)
        await session.flush()

        # Create two confirmed orders with supplies from different pages
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=2001,
            wb_supply_id="WB-GI-PAGE1-001",
        )
        await _create_confirmed_order(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product=product,
            wb_order_id=2002,
            wb_supply_id="WB-GI-PAGE2-002",
        )
        await session.flush()

        # Mock that returns two pages
        page_requests: list[int | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            # Check if this is the supplies list endpoint (query params present)
            if "limit" in request.url.params:
                # Extract next cursor from params
                next_param_raw = request.url.params.get("next")
                next_param: int | None = None
                if next_param_raw is not None:
                    next_param = int(next_param_raw)
                page_requests.append(next_param)

                # WB требует `next` всегда; первая страница — next=0.
                # Раньше тест ждал отсутствия параметра и тем закреплял ошибку,
                # из-за которой боевой WB отвечал 400 IncorrectParameter.
                if next_param in (None, 0):
                    # First page
                    return httpx.Response(
                        200,
                        json={
                            "supplies": [
                                {
                                    "id": "WB-GI-PAGE1-001",
                                    "name": "Page 1 Supply 1",
                                    "done": False,
                                }
                            ],
                            "next": 100,
                        },
                    )
                elif next_param == 100:
                    # Second page
                    return httpx.Response(
                        200,
                        json={
                            "supplies": [
                                {
                                    "id": "WB-GI-PAGE2-002",
                                    "name": "Page 2 Supply 2",
                                    "done": True,
                                }
                            ],
                            "next": None,
                        },
                    )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=http_client,
                api_token="wb-test-token",
            )

        # Verify both supplies were created from merged dict
        stmt1 = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-PAGE1-001",
        )
        res1 = await session.execute(stmt1)
        supply1 = res1.scalar_one()

        stmt2 = select(FbsSupply).where(
            FbsSupply.tenant_id == tenant_id,
            FbsSupply.seller_id == seller_id,
            FbsSupply.wb_supply_id == "WB-GI-PAGE2-002",
        )
        res2 = await session.execute(stmt2)
        supply2 = res2.scalar_one()

        # Verify both supplies have correct names and statuses from pages
        assert supply1.name == "Page 1 Supply 1"
        assert supply1.status == FBS_SUPPLY_STATUS_ASSEMBLING
        assert supply2.name == "Page 2 Supply 2"
        assert supply2.status == FBS_SUPPLY_STATUS_DONE
        assert result["supply_links_created"] == 2
        assert result["supply_linked_orders"] == 2
        # Verify pagination happened (two page requests)
        assert len(page_requests) == 2


@pytest.mark.asyncio
async def test_supplies_page_always_sends_next_param() -> None:
    """WB отвечает 400 IncorrectParameter, если в запросе нет `next`.

    Проверяем сам ЗАПРОС, а не разбор ответа: прошлая версия слала только `limit`,
    все тесты на разборе были зелёными, а на бою список не приходил ни разу.
    """
    from app.services.wildberries_fbs_client import fetch_marketplace_supplies_page

    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"supplies": [], "next": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await fetch_marketplace_supplies_page(client, api_token="t")
        await fetch_marketplace_supplies_page(client, api_token="t", next_cursor=777)

    assert seen[0] == {"limit": "1000", "next": "0"}, "первая страница обязана слать next=0"
    assert seen[1] == {"limit": "1000", "next": "777"}, "курсор обязан уходить в запрос"


@pytest.mark.asyncio
async def test_supplies_pagination_stops_on_empty_page() -> None:
    """WB отдаёт курсор даже когда данные кончились — выходим по пустой странице.

    Раньше признаком конца был только пустой курсор, поэтому цикл честно крутил
    все MAX_SUPPLIES_PAGES страниц на каждого селлера: 10 запросов вместо одного,
    и общий лимитер WB отвечал 429.
    """
    from app.services.wildberries_fbs_client import fetch_marketplace_supplies_page

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, json={
                "supplies": [{"id": "WB-GI-1", "name": "Первая", "done": True}],
                "next": 999,          # курсор есть, хотя данные кончились
            })
        return httpx.Response(200, json={"supplies": [], "next": 1000})

    merged: dict[str, tuple[str | None, bool]] = {}
    cursor: int | None = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for _ in range(10):
            page = await fetch_marketplace_supplies_page(
                client, api_token="t", next_cursor=cursor
            )
            merged.update(page.supplies)
            if not page.supplies or page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert merged == {"WB-GI-1": ("Первая", True)}
    assert len(calls) == 2, f"должно быть 2 запроса, а не {len(calls)} — иначе лимитер WB"
