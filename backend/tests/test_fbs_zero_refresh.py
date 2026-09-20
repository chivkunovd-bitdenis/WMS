"""WMS-483: persisted ten-minute WB zero refresh through actual PUT/readback."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.inventory_balance import InventoryBalance
from app.services import fbs_stock_sync_service as sync
from app.services.fbs_stock_rule_service import publish_amounts_for_binding
from tests.test_fbs_stock_sync import (
    _client,
    _configure_rule_amount,
    _MockStocksTransport,
    _product,
    _seed_binding,
)


@pytest.fixture(autouse=True)
def no_live_zero_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "schedule_binding_zero_refresh", lambda *_args: None)


async def _run(session, ctx, transport, *, zero_refresh_only=False):
    async with _client(transport) as client:
        return await sync.sync_binding_stocks(
            session, ctx.tenant.id, ctx.seller.id, ctx.binding, client,
            rate_limiter=sync.NoopStockSyncRateLimiter(),
            marketplace_api_base="https://wb-mock.test", zero_refresh_only=zero_refresh_only,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("units", [False, True])
async def test_zero_without_history_refreshes_after_ten_minutes_and_stops_on_restock(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, units: bool,
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    monkeypatch.setattr(sync, "_utcnow", lambda: now)
    ctx = await _seed_binding(db_session)
    ctx.binding.served = False
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="zero-refresh", fbs_percent=100,
    )
    product.fbs_units_mode = units
    db_session.add(product)
    await _configure_rule_amount(db_session, ctx, product, 5 if units else 0)
    pool = FbsBindingStockPool(
        tenant_id=ctx.tenant.id, binding_id=ctx.binding.id, product_id=product.id, quantity=0,
    )
    if units:
        db_session.add(pool)
        await db_session.commit()
    transport = _MockStocksTransport()
    assert (await _run(db_session, ctx, transport)).products_confirmed == 1
    for minutes, expected in [(5, 1), (10, 2), (15, 2), (20, 3)]:
        now = datetime(2026, 9, 20, tzinfo=UTC) + timedelta(minutes=minutes)
        for item in list((await db_session.scalars(select(FbsStockSyncItem))).all()):
            await db_session.refresh(item)
        transport.stored[483] = 9
        await _run(db_session, ctx, transport)
        assert len(transport.put_calls) == expected
        if minutes % 10 == 0:
            assert transport.stored[483] == 0
    assert [[entry.amount for entry in batch] for batch in transport.put_calls] == [[0]] * 3
    if units:
        pool.quantity = 5
    else:
        balance = (await db_session.scalars(select(InventoryBalance))).one()
        balance.quantity = 5
    await db_session.commit()
    assert (await _run(db_session, ctx, transport)).products_confirmed == 1
    assert transport.put_calls[-1][0].amount == 5
    now += timedelta(minutes=10)
    await _run(db_session, ctx, transport)
    assert transport.put_calls[-1][0].amount == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [
    "disabled_product", "zero_percent", "no_rule", "missing_units", "binding_off",
    "binding_inactive", "rounding", "zero_binding_percent", "missing_binding_percent",
])
async def test_unmanaged_and_rounding_zero_never_enter_refresh(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, kind: str,
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    monkeypatch.setattr(sync, "_utcnow", lambda: now)
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="excluded", fbs_percent=100,
    )
    db_session.add(product)
    await _configure_rule_amount(db_session, ctx, product, 1 if kind == "rounding" else 0)
    if kind == "disabled_product":
        product.fbs_stock_sync_enabled = False
    elif kind == "zero_percent":
        product.fbs_percent = 0
    elif kind == "no_rule":
        product.fbs_percent = None
    elif kind == "missing_units":
        product.fbs_units_mode = True
    elif kind == "binding_off":
        ctx.binding.stock_sync_enabled = False
    elif kind == "binding_inactive":
        ctx.binding.is_active = False
    elif kind == "rounding":
        product.fbs_percent = 10
    else:
        product.fbs_same_everywhere = False
        if kind == "zero_binding_percent":
            db_session.add(FbsBindingStockPool(
                tenant_id=ctx.tenant.id, binding_id=ctx.binding.id,
                product_id=product.id, quantity=0, percent=0,
            ))
    await db_session.commit()
    transport = _MockStocksTransport()
    for _ in range(3):
        await _run(db_session, ctx, transport)
        now += timedelta(minutes=10)
    assert transport.put_attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["refused", "mismatch", "lost_response"])
async def test_zero_failure_readback_and_next_cycle_retry(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    monkeypatch.setattr(sync, "_utcnow", lambda: now)
    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="failure", fbs_percent=100,
    )
    db_session.add(product)
    await db_session.commit()
    transport = _MockStocksTransport()
    await _run(db_session, ctx, transport)
    now += timedelta(minutes=10)
    if failure == "refused":
        transport._put_status_sequence = [500]
    elif failure == "mismatch":
        transport._readback_overrides = {483: 4}
    else:
        original = transport.handler

        def lost_response(request):
            response = original(request)
            if request.method == "PUT":
                raise httpx.ReadTimeout("response lost", request=request)
            return response

        transport.handler = lost_response
    result = await _run(db_session, ctx, transport)
    item = (await db_session.scalars(select(FbsStockSyncItem))).one()
    if failure == "lost_response":
        assert result.products_confirmed == 1
        assert item.status == "confirmed"
        assert len(transport.post_calls) == 2
        return
    assert result.errors == 1
    assert item.status == "error"
    assert item.last_confirmed_amount == 0
    transport._readback_overrides = {}
    now += timedelta(minutes=5)
    result = await _run(db_session, ctx, transport)
    assert result.products_confirmed == 1
    assert transport.put_attempts == 3
    assert item.status == "confirmed"


@pytest.mark.asyncio
async def test_zero_eligibility_is_wb_only(db_session: AsyncSession) -> None:
    ctx = await _seed_binding(db_session)
    ctx.binding.marketplace = "ozon"
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="ozon", fbs_percent=100,
    )
    db_session.add(product)
    await db_session.commit()
    eligible = set()
    assert await publish_amounts_for_binding(
        db_session, ctx.binding, [product], refresh_zero_product_ids=eligible,
    ) == {product.id: 0}
    assert eligible == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("event_kind", ["movement", "reserve", "operator_zero"])
async def test_committed_events_publish_first_zero_immediately(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, event_kind: str,
) -> None:
    import uuid
    from types import SimpleNamespace

    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.services import fbs_stock_publish_service as publisher
    from app.services.fbs_stock_rule_service import FbsRule, set_rule_for_products
    from app.services.inventory_service import (
        record_movement_and_adjust_balance,
        update_fbs_order_reservation,
    )

    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="event", fbs_percent=100,
    )
    db_session.add(product)
    await _configure_rule_amount(db_session, ctx, product, 1)
    transport = _MockStocksTransport()
    # First zero must also work without any prior positive publication.
    async def publish(tenant_id, seller_id):
        async with SessionLocal() as session:
            binding = await session.get(FbsWarehouseBinding, ctx.binding.id)
            await _run(session, SimpleNamespace(
                tenant=ctx.tenant, seller=ctx.seller, binding=binding,
            ), transport)

    monkeypatch.setattr(publisher, "publish_seller_stocks_now", publish)
    monkeypatch.setattr(publisher.settings, "celery_broker_url", None)
    if event_kind == "movement":
        balance = (await db_session.scalars(select(InventoryBalance))).one()
        balance.quantity_unpacked = 1
        await db_session.flush()
        await record_movement_and_adjust_balance(
            db_session, tenant_id=ctx.tenant.id, product_id=product.id,
            storage_location_id=balance.storage_location_id, quantity_delta=-1,
            movement_type="write_off", actor_user_id=None,
        )
    elif event_kind == "reserve":
        order = FbsOrder(
            id=uuid.uuid4(), tenant_id=ctx.tenant.id, seller_id=ctx.seller.id,
            product_id=product.id, wb_order_id=483, wb_warehouse_id=ctx.binding.wb_warehouse_id,
            warehouse_id=ctx.warehouse.id, created_at_wb=datetime.now(UTC),
            deadline_at=datetime.now(UTC), mapping_status="mapped", status="new",
            reserve_status="reserved",
        )
        db_session.add(order)
        await db_session.flush()
        await update_fbs_order_reservation(db_session, order, reserve=True)
    else:
        await set_rule_for_products(
            db_session, ctx.tenant.id, [product.id],
            FbsRule(publish=True, same_everywhere=True, percent=0, units_mode=True,
                    units_by_warehouse={ctx.binding.wb_warehouse_id: 0}),
            updated_by=None,
        )
    if event_kind != "operator_zero":
        assert transport.put_calls == []
        await db_session.commit()
    await publisher.drain_background_stock_publish_tasks()
    assert [[entry.amount for entry in batch] for batch in transport.put_calls] == [[0]]
    assert transport.post_calls == [[483]]
    if event_kind == "reserve":
        await update_fbs_order_reservation(db_session, order, reserve=False)
        await db_session.commit()
        await publisher.drain_background_stock_publish_tasks()
        assert transport.put_calls[-1][0].amount == 1


@pytest.mark.asyncio
async def test_concurrent_zero_refresh_uses_binding_lease(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from types import SimpleNamespace

    from app.db.session import SessionLocal
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding

    ctx = await _seed_binding(db_session)
    product = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="concurrent", fbs_percent=100,
    )
    db_session.add(product)
    await db_session.commit()
    entered, release = asyncio.Event(), asyncio.Event()
    transport = _MockStocksTransport()
    original = transport.handler

    async def delayed(request):
        if request.method == "PUT":
            entered.set()
            await release.wait()
        return original(request)

    transport.handler = delayed
    first = asyncio.create_task(_run(db_session, ctx, transport))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        async with SessionLocal() as session:
            binding = await session.get(FbsWarehouseBinding, ctx.binding.id)
            concurrent = await _run(session, SimpleNamespace(
                tenant=ctx.tenant, seller=ctx.seller, binding=binding,
            ), transport)
            assert concurrent.skipped_busy
    finally:
        release.set()
        await first
    assert transport.put_attempts == 1
    monkeypatch.setattr(sync, "_utcnow", lambda: datetime.now(UTC) + timedelta(minutes=11))
    await _run(db_session, ctx, transport)
    assert transport.put_attempts == 2


@pytest.mark.asyncio
async def test_same_chrt_in_other_seller_targets_only_its_binding(db_session: AsyncSession) -> None:
    contexts = [await _seed_binding(db_session, wb_warehouse_id=483001),
                await _seed_binding(db_session, wb_warehouse_id=483002)]
    products = []
    for index, ctx in enumerate(contexts):
        product = _product(
            tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
            sku_suffix=f"seller-{index}", fbs_percent=100,
        )
        products.append(product)
        db_session.add(product)
    await db_session.commit()
    transport = _MockStocksTransport()
    original = transport.handler
    paths = []

    def record(request):
        paths.append(request.url.path)
        return original(request)

    transport.handler = record
    for index, ctx in enumerate(contexts):
        assert (await _run(db_session, ctx, transport)).products_confirmed == 1
        item = (await db_session.scalars(select(FbsStockSyncItem).where(
            FbsStockSyncItem.binding_id == ctx.binding.id,
        ))).one()
        assert item.product_id == products[index].id
    assert paths == ["/api/v3/stocks/483001"] * 2 + ["/api/v3/stocks/483002"] * 2


@pytest.mark.asyncio
async def test_eta_refresh_at_ten_minutes_after_off_phase_event_and_duplicate_delivery(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = datetime(2026, 9, 20, tzinfo=UTC)
    now = origin + timedelta(minutes=1)
    monkeypatch.setattr(sync, "_utcnow", lambda: now)
    scheduled = []
    monkeypatch.setattr(sync, "schedule_binding_zero_refresh", lambda *args: scheduled.append(args))
    ctx = await _seed_binding(db_session)
    zero = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="phase-zero", fbs_percent=100,
    )
    positive = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=484,
        sku_suffix="phase-positive", fbs_percent=100,
    )
    db_session.add_all([zero, positive])
    await _configure_rule_amount(db_session, ctx, positive, 5)
    transport = _MockStocksTransport()
    await _run(db_session, ctx, transport)
    assert scheduled == [(ctx.tenant.id, ctx.seller.id, ctx.binding.id,
                          origin + timedelta(minutes=11))]
    for minute in [5, 10]:
        now = origin + timedelta(minutes=minute)
        await _run(db_session, ctx, transport)
        assert [entry.chrt_id for entry in transport.put_calls[-1]] == [484]
    assert len(scheduled) == 1
    now = origin + timedelta(minutes=11)
    await _run(db_session, ctx, transport, zero_refresh_only=True)
    assert [entry.chrt_id for entry in transport.put_calls[-1]] == [483]
    assert scheduled[-1][-1] == origin + timedelta(minutes=21)
    calls = transport.put_attempts
    for minute in [11, 12, 15, 20]:
        now = origin + timedelta(minutes=minute)
        await _run(db_session, ctx, transport, zero_refresh_only=True)
    assert transport.put_attempts == calls
    assert len(scheduled) == 2
    # Lost ETA after a restart is recovered by the unchanged general cycle.
    now = origin + timedelta(minutes=25)
    await _run(db_session, ctx, transport)
    assert transport.stored[483] == 0
    assert scheduled[-1][-1] == origin + timedelta(minutes=35)
    zero.fbs_stock_sync_enabled = False
    await db_session.commit()
    now = origin + timedelta(minutes=35)
    await _run(db_session, ctx, transport, zero_refresh_only=True)
    assert len(scheduled) == 3
    assert transport.put_attempts == calls + 1


def test_zero_scheduler_uses_broker_eta(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    from app.services import fbs_zero_refresh_service as refresh
    from app.tasks.background_jobs import run_fbs_zero_refresh_task

    calls = []
    monkeypatch.setattr(refresh.settings, "celery_broker_url", "memory://")
    monkeypatch.setattr(
        run_fbs_zero_refresh_task, "apply_async", lambda **kwargs: calls.append(kwargs),
    )
    ids = [uuid.uuid4() for _ in range(3)]
    due = datetime.now(UTC) + timedelta(minutes=10)
    refresh.schedule_binding_zero_refresh(*ids, due)
    assert calls == [{"args": [str(identifier) for identifier in ids], "eta": due}]


@pytest.mark.asyncio
async def test_delayed_worker_recalculates_current_rules_and_publishes_only_zero(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import fbs_zero_refresh_service as refresh

    ctx = await _seed_binding(db_session)
    zero = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=483,
        sku_suffix="worker-zero", fbs_percent=100,
    )
    positive = _product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, chrt_id=484,
        sku_suffix="worker-positive", fbs_percent=100,
    )
    db_session.add_all([zero, positive])
    await _configure_rule_amount(db_session, ctx, positive, 5)
    transport = _MockStocksTransport()
    client_type = httpx.AsyncClient
    monkeypatch.setattr(refresh.httpx, "AsyncClient", lambda: client_type(
        transport=httpx.MockTransport(transport.handler),
    ))
    await refresh.refresh_binding_zero_stocks(ctx.tenant.id, ctx.seller.id, ctx.binding.id)
    assert [[entry.chrt_id for entry in batch] for batch in transport.put_calls] == [[483]]
    zero.fbs_stock_sync_enabled = False
    await db_session.commit()
    monkeypatch.setattr(sync, "_utcnow", lambda: datetime.now(UTC) + timedelta(minutes=11))
    await refresh.refresh_binding_zero_stocks(ctx.tenant.id, ctx.seller.id, ctx.binding.id)
    assert transport.put_attempts == 1
