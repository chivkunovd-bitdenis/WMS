"""WMS-435 — session-scoped seller lock must not leak through the caller's commit.

Bug (etalon 388f389b): wb_seller_lock / marketplace_seller_lock(transaction_scoped=False)
took the advisory lock on the caller's own AsyncSession. When the caller committed inside
the block (link_confirmed_orders_to_wb_supplies, repair_pending_supplies_for_seller,
add_orders_to_existing_supply all do), the connection went back to the pool while still
physically holding the lock; the wrapper's own pg_advisory_unlock then ran on whatever
connection the session picked up next, which almost never was the one holding the lock.
The lock then sat on an orphaned pooled connection for as long as the worker's pool lived
— hours in production (WMS-435 backlog entry, 17.09.2026) — and every operator trying to
create or extend a WB supply for that seller got a permanent "try again in a few seconds".

Fix: marketplace_seller_lock, in session-scoped mode, now takes and releases the lock on
its own private connection (an AsyncSession bound to the caller's engine); the caller's
session is only ever read for its `.bind` and is never queried, committed or rolled back
by the wrapper. Transaction-scoped mode (WB supply creation) is unchanged.

These tests only run against a real PostgreSQL database (WMS_TEST_DATABASE_URL): SQLite
has no advisory locks, and the whole point here is to observe pg_locks and independent
pool connections, which a fake dialect cannot provide. They must run in a single process
(pytest -n 0): every worker under xdist would share one database.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.session import SessionLocal
from app.db.session import engine as app_engine
from app.models.fbs_order import FbsOrder
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_supply_service
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks
from app.services.fbs_stock_sync_service import drain_zero_publish_background_tasks
from app.services.fbs_supply_service import (
    FbsSupplyError,
    add_orders_to_existing_supply,
    create_supply_from_orders,
    repair_pending_supplies_for_seller,
)
from app.services.fbs_wb_seller_lock_service import wb_seller_lock, wb_seller_lock_key
from app.services.marketplace_seller_lock_service import marketplace_seller_lock
from app.services.wb_marketplace_orders_service import link_confirmed_orders_to_wb_supplies
from tests.fbs_seed_helpers import DEFAULT_WB_WAREHOUSE_ID, seed_fbs_warehouse_binding
from tests.test_fbs_supply_from_orders import _create_product as _create_product_http
from tests.test_fbs_supply_from_orders import (
    _create_ready_order,
    _register_ff_admin,
    _setup_seller_with_token,
)
from tests.test_fbs_supply_repair_from_wb import (
    _create_supply_request,
    _patch_lost_response,
    _patch_wb_composition,
    _prepare_order,
)
from tests.test_wb_marketplace_orders_service import (
    _create_confirmed_order,
    _register_tenant_and_seller,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.postgresql_concurrency]


# --------------------------------------------------------------------------
# Shared helpers: pg_locks / try-lock probes from an engine independent of
# whatever session took the lock under test. These are the only oracle for a
# leak (raw pg_locks), plus an independent try-lock to prove a peer can (or
# cannot) take the key — see WMS-435 requirements doc, section 5.
# --------------------------------------------------------------------------


def _classid_objid(lock_key: int) -> tuple[int, int]:
    """Split a signed 64-bit advisory key into pg_locks' classid/objid columns."""
    unsigned = lock_key & 0xFFFFFFFFFFFFFFFF
    return (unsigned >> 32) & 0xFFFFFFFF, unsigned & 0xFFFFFFFF


async def _lock_granted_pids(engine: AsyncEngine, lock_key: int) -> list[int]:
    """pids currently holding (granted=true) the advisory lock for this key."""
    classid, objid = _classid_objid(lock_key)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "select pid from pg_locks where locktype='advisory' "
                    "and classid=:classid and objid=:objid and granted"
                ),
                {"classid": classid, "objid": objid},
            )
        ).all()
    return [row[0] for row in rows]


async def _probe_try_lock(
    engine: AsyncEngine, lock_key: int, *, transaction_scoped: bool
) -> bool:
    """One-shot try-lock from an independent connection; leaves the key as found."""
    async with engine.connect() as conn:
        if transaction_scoped:
            async with conn.begin():
                return bool(
                    await conn.scalar(
                        text("select pg_try_advisory_xact_lock(:k)"), {"k": lock_key}
                    )
                )
        async with conn.begin():
            acquired = bool(
                await conn.scalar(text("select pg_try_advisory_lock(:k)"), {"k": lock_key})
            )
            if acquired:
                await conn.execute(text("select pg_advisory_unlock(:k)"), {"k": lock_key})
        return acquired


async def _warm_pool(engine: AsyncEngine, count: int = 2) -> None:
    """Force `count` distinct physical connections into the pool.

    Without this, a pool that has only ever handed out one physical connection
    will hand the SAME one back right after a commit, and an unlock bug that
    only shows up across two different connections would go unnoticed (WMS-435
    requirements doc, section 5).
    """
    conns = [await engine.connect() for _ in range(count)]
    for conn in conns:
        await conn.close()


async def _hold_session_lock(engine: AsyncEngine, lock_key: int) -> AsyncConnection:
    """Take a session-level advisory lock on a dedicated connection the caller must release."""
    conn = await engine.connect()
    acquired = bool(await conn.scalar(text("select pg_try_advisory_lock(:k)"), {"k": lock_key}))
    if not acquired:
        await conn.close()
        raise AssertionError("setup failure: could not seed the external seller-lock holder")
    return conn


async def _release_session_lock(conn: AsyncConnection, lock_key: int) -> None:
    await conn.execute(text("select pg_advisory_unlock(:k)"), {"k": lock_key})
    await conn.close()


async def _drain_background_locks() -> None:
    """Wait out fire-and-forget stock-publish tasks that also take the seller lock.

    fbs_stock_publish_service schedules a same-process asyncio task (no Celery
    broker in tests) on its own dedicated connection whenever an order's stock
    reservation changes — which every real path under test here does. Left
    undrained, that unrelated, pre-existing background lock use (R4д) can still
    be mid-flight when a test checks pg_locks a moment later, which is a race
    in the test, not a leak in the fix under test.
    """
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("WMS_TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires explicit PostgreSQL test URL; uses advisory locks and pg_locks")
    return url


# --------------------------------------------------------------------------
# C1 — commit inside the block must not strand the lock on the pool.
# --------------------------------------------------------------------------


async def test_c1_commit_inside_block_does_not_leak_the_lock(pg_url: str) -> None:
    engine = create_async_engine(pg_url, pool_size=2, max_overflow=0, pool_timeout=1.0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    try:
        await _warm_pool(engine, 2)
        async with sessions() as session, wb_seller_lock(session, seller_id) as acquired:
            assert acquired is True
            await session.scalar(text("select 1"))
            await session.commit()
            # Still inside the block, after the caller's own commit: a
            # peer from a completely different pool must see it busy in
            # BOTH lock flavours (advisory locks share one key space).
            assert (
                await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False)
                is False
            )
            assert (
                await _probe_try_lock(probe_engine, lock_key, transaction_scoped=True)
                is False
            )
            # Immediately after leaving the block: free.
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False) is True
        )
    finally:
        await engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C2 — rollback + early return, and flush without commit, both release cleanly.
# --------------------------------------------------------------------------


async def test_c2_rollback_and_early_return_and_flush_release_the_lock(pg_url: str) -> None:
    engine = create_async_engine(pg_url, pool_size=2, max_overflow=0, pool_timeout=1.0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    busy_during_return: list[bool] = []

    async def rollback_then_return_from_middle(session: AsyncSession) -> str:
        async with wb_seller_lock(session, seller_id) as acquired:
            assert acquired is True
            await session.scalar(text("select 1"))
            await session.rollback()
            busy_during_return.append(
                await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False)
            )
            return "returned-from-middle"
        return "unreachable"  # pragma: no cover - guarded by the return above

    try:
        await _warm_pool(engine, 2)

        async with sessions() as session:
            outcome = await rollback_then_return_from_middle(session)
        assert outcome == "returned-from-middle"
        assert busy_during_return == [False]
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False) is True
        )

        # Second scenario: a flush with no commit, normal exit from the block.
        async with sessions() as session, wb_seller_lock(session, seller_id) as acquired:
            assert acquired is True
            await session.scalar(text("select 1"))
            await session.flush()
            assert (
                await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False)
                is False
            )
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False) is True
        )
    finally:
        await engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C3 — a DB error inside the block must surface as itself, not as a masking
# unlock failure, and must not leak the lock either.
# --------------------------------------------------------------------------


async def test_c3_db_error_inside_block_propagates_and_releases_lock(pg_url: str) -> None:
    engine = create_async_engine(pg_url, pool_size=2, max_overflow=0, pool_timeout=1.0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    try:
        await _warm_pool(engine, 2)
        async with sessions() as session:
            with pytest.raises(DBAPIError) as excinfo:
                async with wb_seller_lock(session, seller_id) as acquired:
                    assert acquired is True
                    await session.execute(text("select 1/0"))
            # The real division error, never an unlock-time InFailedSqlTransaction.
            assert type(excinfo.value.orig).__name__ == "DivisionByZero"
            # As before the fix: cleaning up the working session's aborted
            # transaction is the caller's job, done after the block (matches
            # sync_seller_orders / repair_pending_supplies_for_seller).
            await session.rollback()
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False) is True
        )
    finally:
        await engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C4 — a plain business exception inside the block, no DB touched afterwards.
# --------------------------------------------------------------------------


async def test_c4_business_exception_inside_block_propagates_and_releases_lock(
    pg_url: str,
) -> None:
    engine = create_async_engine(pg_url, pool_size=2, max_overflow=0, pool_timeout=1.0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    try:
        await _warm_pool(engine, 2)
        async with sessions() as session:
            with pytest.raises(FbsSupplyError) as excinfo:
                async with wb_seller_lock(session, seller_id) as acquired:
                    assert acquired is True
                    raise FbsSupplyError("supply_not_found")
            assert excinfo.value.code == "supply_not_found"
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=False) is True
        )
    finally:
        await engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C5 — a nested try-lock under an external, autopoll-style lock_session must
# fail instantly (no waiting), exactly like today.
# --------------------------------------------------------------------------


async def test_c5_nested_try_lock_under_external_lock_session_does_not_wait(
    pg_url: str,
) -> None:
    engine = create_async_engine(pg_url, pool_size=3, max_overflow=0, pool_timeout=1.0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    try:
        async with (
            sessions() as lock_session,
            sessions() as session,
            marketplace_seller_lock(lock_session, seller_id, "wb") as outer,
        ):
            assert outer is True
            started = time.monotonic()
            async with wb_seller_lock(
                session, seller_id, wait_timeout_sec=0.0
            ) as nested_acquired:
                elapsed = time.monotonic() - started
                assert nested_acquired is False
            # Well under one poll interval (0.25s default): no waiting happened.
            assert elapsed < 0.2
            # External lock released here.
        assert await _lock_granted_pids(probe_engine, lock_key) == []

        async with sessions() as session2, wb_seller_lock(session2, seller_id) as acquired2:
            assert acquired2 is True
        assert await _lock_granted_pids(probe_engine, lock_key) == []
    finally:
        await engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C6 — the real order/supply linking path (link_confirmed_orders_to_wb_supplies).
# --------------------------------------------------------------------------


async def test_c6_link_confirmed_orders_to_wb_supplies_does_not_leak(
    pg_url: str, async_client: AsyncClient
) -> None:
    from app.models.product import Product

    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    wb_supply_id = "WB-GI-WMS435-C6"
    tenant_id, seller_id, warehouse_id, _location_id = await _register_tenant_and_seller(
        async_client
    )
    try:
        async with SessionLocal() as session:
            await seed_fbs_warehouse_binding(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                wms_warehouse_id=warehouse_id,
                wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID,
            )
            product = Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name="WMS-435 product",
                sku_code="WMS435-C6-SKU",
                wb_nm_id=900435,
            )
            session.add(product)
            await session.flush()
            await _create_confirmed_order(
                session,
                tenant_id,
                seller_id,
                warehouse_id,
                product,
                wb_order_id=435001,
                wb_supply_id=wb_supply_id,
            )
            await session.flush()
            await session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if "limit" in request.url.params:
                return httpx.Response(
                    200,
                    json={
                        "supplies": [
                            {"id": wb_supply_id, "name": "WMS-435 supply", "done": False}
                        ],
                        "next": None,
                    },
                )
            return httpx.Response(200, json={"id": wb_supply_id, "done": False})

        transport = httpx.MockTransport(handler)
        lock_key = wb_seller_lock_key(seller_id)

        await _warm_pool(app_engine, 2)
        async with SessionLocal() as session, httpx.AsyncClient(transport=transport) as client:
            result = await link_confirmed_orders_to_wb_supplies(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                http_client=client,
                api_token="wb-test-token",
            )

        assert result["supply_linked_orders"] == 1
        assert result["supply_links_created"] == 1

        async with SessionLocal() as session:
            order = await session.scalar(
                select(FbsOrder).where(FbsOrder.wb_order_id == 435001)
            )
            assert order is not None
            assert order.supply_id is not None

        # The order becoming in_supply schedules an unrelated, pre-existing
        # stock-publish background task on its own lock_session (R4д); let it
        # finish before reading pg_locks so its own short-lived, correct use
        # of the same key cannot be mistaken for a leak from the code under test.
        await _drain_background_locks()
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=True) is True
        )
    finally:
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C7 — the real repair path (repair_pending_supplies_for_seller), reusing the
# exact fixture from test_fbs_supply_repair_from_wb.py::test_autopoll_repairs_pending_supply.
# --------------------------------------------------------------------------


async def test_c7_repair_pending_supplies_for_seller_does_not_leak(
    pg_url: str,
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.settings import settings
    from app.models.fbs_order import FBS_ORDER_STATUS_IN_SUPPLY

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    try:
        headers, tenant_id, order_id = await _prepare_order(
            async_client, monkeypatch, wb_order_id=435002, sku="wms435-c7"
        )
        _patch_lost_response(monkeypatch)
        resp = await _create_supply_request(async_client, headers, order_id)
        assert resp.status_code == 504, resp.text

        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            assert order is not None and order.supply_id is None
            seller_id = order.seller_id

        lock_key = wb_seller_lock_key(seller_id)
        _patch_wb_composition(monkeypatch, [435002])
        await _warm_pool(app_engine, 2)
        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            result = await repair_pending_supplies_for_seller(
                session, tenant_id, seller_id, http_client=http_client
            )
        assert result == {"supplies_scanned": 1, "orders_linked": 1}

        async with SessionLocal() as session:
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            assert order.supply_id is not None
            assert order.status == FBS_ORDER_STATUS_IN_SUPPLY

        await _drain_background_locks()
        assert await _lock_granted_pids(probe_engine, lock_key) == []
        assert (
            await _probe_try_lock(probe_engine, lock_key, transaction_scoped=True) is True
        )
    finally:
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C8 — add_orders_to_existing_supply: honest wait, honest text, no WB call.
# --------------------------------------------------------------------------


async def test_c8_add_orders_waits_then_reports_honest_text_and_no_wb_call(
    pg_url: str, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id_str, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_id = uuid.UUID(seller_id_str)
    product = await _create_product_http(
        async_client, headers, seller_id_str, sku=f"wms435-c8-{suffix[-6:]}"
    )
    initial_order = await _create_ready_order(
        tenant_id, seller_id, uuid.UUID(warehouse_id), uuid.UUID(location_id), product,
        order_id=435101,
    )
    second_order = await _create_ready_order(
        tenant_id, seller_id, uuid.UUID(warehouse_id), uuid.UUID(location_id), product,
        order_id=435102,
    )
    create = await async_client.post(
        "/operations/fbs-supplies/from-orders",
        headers=headers,
        json={
            "name": "WMS-435 C8 target",
            "order_ids": [str(initial_order)],
            "planned_delivery_type": "warehouse_sc",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert create.status_code == 201, create.text
    supply_id = uuid.UUID(create.json()["supply"]["id"])

    # From here on, a real (non-mocked) call to WB must be provably absent.
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", False)
    batch_add_calls: list[list[int]] = []
    reconcile_calls: list[str] = []

    async def counting_batch_add(
        client: object, *, api_token: str, supply_id: str, order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> None:
        batch_add_calls.append(list(order_ids))

    async def counting_reconcile(
        client: object, *, api_token: str, wb_supply_id: str, expected_wb_order_ids: set[int],
    ) -> tuple[str, set[int]]:
        reconcile_calls.append(wb_supply_id)
        from app.models.fbs_wb_operation import WB_OPERATION_STATE_CONFIRMED

        return WB_OPERATION_STATE_CONFIRMED, set(expected_wb_order_ids)

    monkeypatch.setattr(
        "app.services.fbs_supply_service.add_orders_to_marketplace_supply", counting_batch_add
    )
    monkeypatch.setattr(
        "app.services.fbs_supply_service.reconcile_supply_orders", counting_reconcile
    )
    monkeypatch.setattr(fbs_supply_service, "WB_LOCK_WAIT_FOR_OPERATOR_SEC", 2.0)

    holder_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    lock_key = wb_seller_lock_key(seller_id)
    holder_conn = None
    try:
        # The setup above (ready orders, supply creation) schedules its own
        # stock-publish background tasks on the same seller lock (R4д); let
        # them finish before seeding our external holder, or seeding could
        # spuriously fail (or spuriously "succeed" mid-flight).
        await _drain_background_locks()
        holder_conn = await _hold_session_lock(holder_engine, lock_key)

        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            with pytest.raises(FbsSupplyError) as excinfo:
                await add_orders_to_existing_supply(
                    session,
                    tenant_id,
                    supply_id,
                    [second_order],
                    idempotency_key=str(uuid.uuid4()),
                    actor_user_id=None,
                    http_client=http_client,
                )
        assert excinfo.value.code == "operation_in_progress"
        assert excinfo.value.http_status == 503
        assert excinfo.value.retryable is True
        assert excinfo.value.message == (
            "По этому селлеру идёт фоновый обмен с WB — добавление заказов ждало "
            "его 2 с и не дождалось. Повторите попытку позже."
        )
        assert batch_add_calls == []
        assert reconcile_calls == []

        async with SessionLocal() as session:
            order = await session.get(FbsOrder, second_order)
            assert order is not None and order.supply_id is None

        await _release_session_lock(holder_conn, lock_key)
        holder_conn = None
        assert await _lock_granted_pids(probe_engine, lock_key) == []

        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            await add_orders_to_existing_supply(
                session,
                tenant_id,
                supply_id,
                [second_order],
                idempotency_key=str(uuid.uuid4()),
                actor_user_id=None,
                http_client=http_client,
            )
            # The API route commits after a successful call (app/api/fbs_supplies.py);
            # replicate that here since this test calls the service directly.
            await session.commit()
        assert batch_add_calls == [[435102]]
        assert len(reconcile_calls) == 1

        async with SessionLocal() as session:
            order = await session.get(FbsOrder, second_order)
            assert order is not None
            assert order.supply_id == supply_id
        await _drain_background_locks()
    finally:
        if holder_conn is not None:
            await _release_session_lock(holder_conn, lock_key)
        await holder_engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C9 — create_supply_from_orders: honest wait, honest text, no local operation row.
# --------------------------------------------------------------------------


async def test_c9_create_supply_waits_then_reports_honest_text_and_no_operation_row(
    pg_url: str, async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.settings import settings

    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    me = await async_client.get("/auth/me", headers=headers)
    tenant_id = uuid.UUID(me.json()["tenant_id"])
    seller_id_str, warehouse_id, location_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    seller_id = uuid.UUID(seller_id_str)
    product = await _create_product_http(
        async_client, headers, seller_id_str, sku=f"wms435-c9-{suffix[-6:]}"
    )
    order_id = await _create_ready_order(
        tenant_id, seller_id, uuid.UUID(warehouse_id), uuid.UUID(location_id), product,
        order_id=435201,
    )

    monkeypatch.setattr(fbs_supply_service, "WB_LOCK_WAIT_FOR_OPERATOR_SEC", 2.0)
    holder_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    lock_key = wb_seller_lock_key(seller_id)
    holder_conn = None
    try:
        # As in C8: let the setup's own stock-publish background task (R4д)
        # finish before seeding the external holder.
        await _drain_background_locks()
        holder_conn = await _hold_session_lock(holder_engine, lock_key)

        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            with pytest.raises(FbsSupplyError) as excinfo:
                await create_supply_from_orders(
                    session,
                    tenant_id,
                    name="WMS-435 C9",
                    order_ids=[order_id],
                    planned_delivery_type="warehouse_sc",
                    planned_destination=None,
                    idempotency_key=str(uuid.uuid4()),
                    http_client=http_client,
                )
        assert excinfo.value.code == "operation_in_progress"
        assert excinfo.value.http_status == 503
        assert excinfo.value.retryable is True
        assert excinfo.value.message == (
            "По этому селлеру идёт фоновый обмен с WB — создание поставки ждало "
            "его 2 с и не дождалось. Повторите попытку позже."
        )

        async with SessionLocal() as session:
            pending_ops = (
                await session.execute(
                    select(FbsWbOperation).where(FbsWbOperation.seller_id == seller_id)
                )
            ).scalars().all()
            assert list(pending_ops) == []

        await _release_session_lock(holder_conn, lock_key)
        holder_conn = None
        assert await _lock_granted_pids(probe_engine, lock_key) == []

        async with SessionLocal() as session, httpx.AsyncClient() as http_client:
            result = await create_supply_from_orders(
                session,
                tenant_id,
                name="WMS-435 C9 retry",
                order_ids=[order_id],
                planned_delivery_type="warehouse_sc",
                planned_destination=None,
                idempotency_key=str(uuid.uuid4()),
                http_client=http_client,
            )
            # The API route commits after a successful call (app/api/fbs_supplies.py);
            # replicate that here since this test calls the service directly.
            await session.commit()
        assert result.get("id") or result.get("supply", {}).get("id")

        async with SessionLocal() as session:
            confirmed_ops = (
                await session.execute(
                    select(FbsWbOperation).where(FbsWbOperation.seller_id == seller_id)
                )
            ).scalars().all()
            assert len(confirmed_ops) == 1
            assert confirmed_ops[0].state == "confirmed"
    finally:
        if holder_conn is not None:
            await _release_session_lock(holder_conn, lock_key)
        await holder_engine.dispose()
        await probe_engine.dispose()


# --------------------------------------------------------------------------
# C10 — waiting for the lock must not starve a two-slot pool.
# --------------------------------------------------------------------------


async def test_c10_waiting_for_the_lock_does_not_starve_the_pool(pg_url: str) -> None:
    engine = create_async_engine(pg_url, pool_size=2, max_overflow=0, pool_timeout=0.5)
    holder_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    # holder_engine's one connection stays checked out for the whole test (it
    # is the external lock holder); pg_locks must be read through a different
    # engine or this checkout would itself time out waiting for a free slot.
    probe_engine = create_async_engine(pg_url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    seller_id = uuid.uuid4()
    lock_key = wb_seller_lock_key(seller_id)
    holder_conn = None
    try:
        holder_conn = await _hold_session_lock(holder_engine, lock_key)
        holder_pid = await holder_conn.scalar(text("select pg_backend_pid()"))

        async with sessions() as session:
            await session.scalar(text("select 1"))  # the working session holds its one slot

            async def wait_for_lock() -> bool:
                async with wb_seller_lock(
                    session, seller_id, wait_timeout_sec=1.5
                ) as acquired:
                    return acquired

            wait_task = asyncio.create_task(wait_for_lock())
            await asyncio.sleep(0.4)
            assert not wait_task.done()

            # The pool's other slot is still available to an unrelated caller.
            async with sessions() as third:
                assert await third.scalar(text("select 1")) == 1

            acquired = await wait_task
            assert acquired is False

        assert await _lock_granted_pids(probe_engine, lock_key) == [holder_pid]
    finally:
        if holder_conn is not None:
            await _release_session_lock(holder_conn, lock_key)
        await engine.dispose()
        await holder_engine.dispose()
        await probe_engine.dispose()
