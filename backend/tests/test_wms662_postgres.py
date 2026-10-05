"""WMS-662 real independent workers; run serially on the dedicated PostgreSQL DB."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections import Counter

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.exc import PendingRollbackError

from app.db.session import SessionLocal, engine
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrder
from app.models.fbs_packing_box import FbsPackingBox, FbsPackingBoxItem
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_shipment_service as shipment
from app.services import inventory_service as inventory
from app.services.fbs_picking_service import manual_pick_product
from app.services.marketplace_provider import MarketplaceProviderError, OzonMarketplaceProvider
from tests.test_wms662_observed_handoff import (
    OzonCards,
    assert_completed,
    assert_no_shipment,
    checkpoint,
    external,
    saved,
    seed,
    shipped,
    sync,
)
from tests.test_wms662_observed_handoff import (
    fake_credentials_and_no_network as fake_credentials_and_no_network,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        engine.dialect.name != "postgresql", reason="real row locks require dedicated PostgreSQL"
    ),
]


@pytest.fixture(autouse=True)
def only_dedicated_database():
    if engine.dialect.name == "postgresql":
        assert str(engine.url) == "postgresql+asyncpg://wms_test@127.0.0.1:55462/wms_test_662"
        assert not os.environ.get("PYTEST_XDIST_WORKER"), "No xdist on a shared PG database"


@pytest_asyncio.fixture(autouse=True)
async def release_pg_pool_before_loop_closes(db_session):
    yield
    await db_session.close()
    await engine.dispose()


async def identity():
    async with SessionLocal() as session:
        row = (
            await session.execute(
                text(
                    "select current_database(), current_user, "
                    "inet_server_addr()::text, inet_server_port()"
                )
            )
        ).one()
        assert tuple(row) == ("wms_test_662", "wms_test", "127.0.0.1/32", 55462)


async def ordinary_ready(session, case):
    """Actual existing assembly/box records, not a preflight stub."""
    from app.models.fbs_order import FbsOrderProduct

    for order in case.orders:
        positions = list(
            await session.scalars(
                select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id)
            )
        )
        physical = WarehouseBox(
            tenant_id=case.tenant.id,
            warehouse_id=case.warehouse.id,
            internal_barcode=f"662-{order.id}",
        )
        session.add(physical)
        await session.flush()
        box = FbsPackingBox(
            tenant_id=case.tenant.id,
            supply_id=case.supply.id,
            warehouse_box_id=physical.id,
            box_number=1,
        )
        session.add(box)
        await session.flush()
        for position in positions:
            session.add(
                FbsPackingBoxItem(
                    tenant_id=case.tenant.id,
                    box_id=box.id,
                    fbs_order_id=order.id,
                    order_product_id=position.id,
                )
            )
    await checkpoint(session, case)


class OrdinaryCards(OzonCards):
    """The ordinary button may read its already existing handoff documents."""

    async def call(self, *, client_id, api_key, path, payload):
        if path in {
            "/v2/posting/fbs/act/get-barcode",
            "/v2/posting/fbs/act/get-pdf",
            "/v2/posting/fbs/act/get-barcode/text",
        }:
            self.endpoint_calls.append((path, dict(payload)))
            return {}  # Optional document data absent; never print or store a synthetic QR.
        return await super().call(client_id=client_id, api_key=api_key, path=path, payload=payload)


async def normal_button(case, api):
    async with (
        SessionLocal() as session,
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(599))) as http,
    ):
        await shipment.deliver_supply(
            session,
            case.tenant.id,
            case.supply.id,
            http,
            idempotency_key="wms662-approved",
            actor_user_id=None,
            ozon_provider=OzonMarketplaceProvider(transport=api),
        )


async def test_c9_two_pollers_and_normal_button(db_session):
    await identity()
    case = await seed(db_session, "ozon")
    await ordinary_ready(db_session, case)
    barrier = asyncio.Barrier(3)
    apis = [external(case), external(case), OrdinaryCards(case)]
    arrived = set()
    for index, api in enumerate(apis):

        async def wait_once(index=index):
            if index not in arrived:
                arrived.add(index)
                await asyncio.wait_for(barrier.wait(), 5)

        api.before_reply = wait_once
    results = await asyncio.wait_for(
        asyncio.gather(
            sync(case, apis[0]),
            sync(case, apis[1]),
            normal_button(case, apis[2]),
            return_exceptions=True,
        ),
        20,
    )
    assert arrived == {0, 1, 2}, "all three real workers must reach the external read barrier"
    assert not [r for r in results if isinstance(r, BaseException)], results
    state = await saved(case)
    assert_completed(case, state)
    assert len(state.ledgers) == 1
    assert len([m for m in state.moves if m.movement_type == "fbs_shipment"]) == 1
    assert len(state.facts) == 1
    assert Counter(c.service_code for c in state.charges) == {"fbs_order": 1, "packing": 1}
    before_ids = {m.id for m in state.moves}
    await sync(case, external(case))
    assert {m.id for m in (await saved(case)).moves} == before_ids


@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c12_cancel_wins_over_inflight_old_positive(db_session, marketplace):
    await identity()
    case = await seed(db_session, marketplace)
    api = external(case)
    waiting, release = asyncio.Event(), asyncio.Event()

    async def pause():
        waiting.set()
        await asyncio.wait_for(release.wait(), 5)

    api.before_reply = pause
    task = asyncio.create_task(sync(case, api))
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        # A real separate cancellation sync commits while the old positive response is in flight.
        cancel = external(
            case, ("cancel", "canceled") if marketplace == "wb" else ("cancelled", None)
        )
        await asyncio.wait_for(sync(case, cancel), 3)
        before = await saved(case)
        release.set()
        await asyncio.wait_for(task, 5)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    after = await saved(case)
    assert after.orders[case.orders[0].id].status == "cancelled"
    assert after.stock == before.stock
    assert after.reserves == before.reserves
    assert after.position_reserves == before.position_reserves
    assert {m.id for m in after.moves} == {m.id for m in before.moves}


async def test_c17_pick_transfer_cap_and_neighbour_during_http(db_session):
    await identity()
    case = await seed(db_session, "wb", count=2)
    actor = User(
        tenant_id=case.tenant.id,
        email="isolated-662@example.invalid",
        password_hash="not-a-login",
        role="fulfillment_admin",
    )
    second = StorageLocation(
        tenant_id=case.tenant.id, warehouse_id=case.warehouse.id, code="B-02", barcode="WMS662-B02"
    )
    binding = FbsWarehouseBinding(
        tenant_id=case.tenant.id,
        seller_id=case.seller.id,
        marketplace="wb",
        wb_warehouse_id=11,
        wms_warehouse_id=case.warehouse.id,
    )
    db_session.add_all([actor, second, binding])
    await db_session.flush()
    pool = FbsBindingStockPool(
        tenant_id=case.tenant.id,
        binding_id=binding.id,
        product_id=case.products[0].id,
        quantity=7,
        units_configured=True,
    )
    db_session.add(pool)
    await db_session.commit()
    initial = await saved(case)
    await inventory.apply_stock_transfer(
        db_session,
        case.tenant.id,
        from_storage_location_id=case.location.id,
        to_storage_location_id=second.id,
        product_id=case.products[0].id,
        quantity=2,
        actor_user_id=actor.id,
    )
    await db_session.commit()
    await manual_pick_product(
        db_session,
        case.tenant.id,
        case.supply.id,
        location_id=second.id,
        product_id=case.products[0].id,
        order_id=case.orders[0].id,
        idempotency_key="662-pick",
        actor=actor,
    )
    await db_session.commit()
    before = await saved(case)
    assert before.stock == initial.stock
    assert shipped(before, case.products[0]) == 0
    api = external(case, ("confirm", "waiting"))
    waiting, release = asyncio.Event(), asyncio.Event()

    async def pause():
        waiting.set()
        await asyncio.wait_for(release.wait(), 5)

    api.before_reply = pause
    poller = asyncio.create_task(sync(case, api))
    try:
        await asyncio.wait_for(waiting.wait(), 5)
        # The same seller/warehouse/supply can make progress while I/O is paused.
        neighbour_api = external(case, ("confirm", "waiting"))
        neighbour_api.rows[case.orders[1].wb_order_id]["supplierStatus"] = "cancel"
        await asyncio.wait_for(sync(case, neighbour_api), 3)
        async with SessionLocal() as independent:
            await independent.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            await independent.scalar(
                select(FbsSupply).where(FbsSupply.id == case.supply.id).with_for_update()
            )
            cap = await independent.get(FbsBindingStockPool, pool.id)
            assert cap.quantity == 7
            await independent.commit()
        release.set()
        await asyncio.wait_for(poller, 5)
    finally:
        release.set()
        if not poller.done():
            poller.cancel()
        await asyncio.gather(poller, return_exceptions=True)
    after = await saved(case)
    assert after.stock == initial.stock
    assert after.orders[case.orders[1].id].status == "cancelled"
    # Finish through the real local half of an ordinary WB handoff, then observe it again.
    async with SessionLocal() as worker:
        from app.services.fbs_shipment_source_service import (
            FbsShipmentSourceRequest,
            plan_fbs_shipment_sources,
        )
        from app.services.fbs_supply_reconcile_service import (
            create_pending_deliver_operation,
            request_hash_for_deliver,
        )

        supply = await worker.get(FbsSupply, case.supply.id)
        order = await worker.get(FbsOrder, case.orders[0].id)
        op = await create_pending_deliver_operation(
            worker,
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            local_supply_id=case.supply.id,
            idempotency_key="662-normal",
            request_hash=request_hash_for_deliver(
                supply_id=case.supply.id, confirmed_preflight_version=None
            ),
            confirmed_preflight_version=None,
        )
        plan = await plan_fbs_shipment_sources(
            worker,
            tenant_id=case.tenant.id,
            supply_warehouse_id=case.warehouse.id,
            requests=[
                FbsShipmentSourceRequest(
                    fbs_order_id=order.id, product_id=order.product_id, quantity=1
                )
            ],
        )
        await shipment._persist_confirmed_delivery(
            worker, supply, [order], op, None, source_plan=plan
        )
    await sync(case, external(case))
    final = await saved(case)
    assert shipped(final, case.products[0]) == 1
    assert final.stock[case.products[0].id] == initial.stock[case.products[0].id] - 1
    async with SessionLocal() as reader:
        assert (await reader.get(FbsBindingStockPool, pool.id)).quantity == 7


class InjectedCrash(RuntimeError):
    pass


@pytest.mark.parametrize("boundary", ["movement", "ledger", "reserve"])
@pytest.mark.parametrize("entry", ["observed", "normal_checkpoint"])
async def test_c10_local_crash_atomic_and_restart(db_session, boundary, entry):
    await identity()
    case = await seed(db_session, "ozon")
    if entry == "normal_checkpoint":
        await ordinary_ready(db_session, case)
    before = await saved(case)
    api = external(case) if entry == "observed" else OrdinaryCards(case)
    run = sync if entry == "observed" else normal_button
    hit = []

    def fail_at_sql(conn, cursor, statement, parameters, context, executemany):
        sql = statement.lower()
        target = (
            (boundary == "movement" and sql.startswith("insert into inventory_movements"))
            or (
                boundary == "ledger"
                and sql.startswith("update fbs_shipment_reversal_ledger")
                and "shipment_movement_id" in sql
            )
            or (
                boundary == "reserve"
                and sql.startswith("delete from fbs_order_product_reservations")
            )
        )
        if target and not hit:
            hit.append(statement)
            raise InjectedCrash(boundary)

    event.listen(engine.sync_engine, "before_cursor_execute", fail_at_sql)
    try:
        with contextlib.suppress(InjectedCrash, PendingRollbackError):
            await run(case, api)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_at_sql)
    state = await saved(case)
    assert hit, f"proved external handoff never reached real {boundary} persistence boundary"
    assert_no_shipment(before, state)
    assert state.position_reserves == before.position_reserves
    assert state.operations, "external evidence must survive the failed local transaction"
    # Simulate a dead/restarted worker; no in-memory response is available anymore.
    api.failure = MarketplaceProviderError("ozon", 503) if entry == "observed" else None
    with contextlib.suppress(MarketplaceProviderError):
        await run(case, api)
    assert_completed(case, await saved(case))
    api.failure = None
    first = await saved(case)
    await run(case, api)
    assert {m.id for m in (await saved(case)).moves} == {m.id for m in first.moves}
