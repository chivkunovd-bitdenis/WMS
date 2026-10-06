"""Real PG contract: public sync conducts A(P1), B(P2); ordinary C(P2) races.

Three supplies, one seller, three distinct orders. Only A/B enter a real bounded
sync batch; C remains outside it. No conduct helper or business function is mocked.
An event hook pauses sync after its actual Seller lock. A separate PG observer
releases it only when pg_blocking_pids proves the ordinary writer waits for sync,
including implicit FK waits before explicit Product SELECTs. SQL errors are
captured below the billing savepoint's exception handler. Run in one pytest
process on the dedicated wms_test_662_batch database, never the F6 database.
"""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from test_wms662_approve_scope_race import ApproveRaceTransport, normal_handoff, ready_order
from test_wms662_cancellation_lock_order import headers, order_entries, resource, sqlstate
from test_wms662_observed_handoff import (
    OzonCards,
    fake_credentials_and_no_network,  # noqa: F401 -- synthetic credentials, no HTTP
    saved,
    seed,
    shipped,
    sync,
)

from app.db.session import SessionLocal, engine
from app.models.billing import BillingTariffVersion
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.services import inventory_service as inventory
from app.services import ozon_fbs_sync_service as ozon_sync

pytestmark = pytest.mark.asyncio
role: ContextVar[str | None] = ContextVar("wms662_batch_writer", default=None)


@pytest_asyncio.fixture(autouse=True)
async def isolated_pg():
    # Check before db_session's destructive schema setup, and never skip a run
    # accidentally pointed at SQLite or somebody else's test database.
    assert engine.dialect.name == "postgresql", "requires isolated real PostgreSQL"
    assert (engine.url.host, engine.url.port, engine.url.database, engine.url.username) == (
        "127.0.0.1", 55466, "wms_test_662_batch", "wms_test",
    )
    assert not os.environ.get("PYTEST_XDIST_WORKER"), "run serially in one process"
    async with SessionLocal() as reader:
        assert await reader.scalar(text(
            "select count(*) from pg_stat_activity where datname=current_database() "
            "and pid<>pg_backend_pid() and backend_type='client backend'"
        )) == 0, "database must be idle before schema setup"
    yield
    await engine.dispose()


class BatchSchedule:
    def __init__(self):
        self.held = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
        self.pids = {}
        self.trace = []
        self.errors = []
        self.harness_errors = []
        self.wait_seen = False
        self.cycle_seen = False
        self.wait_queries = []

    def before(self, conn, clause, multiparams, params, options):
        worker = role.get()
        if worker is None:
            return
        # Capture the actual writer before ALL DML, including blocking FK checks.
        if getattr(clause, "_for_update_arg", None) is not None or any(
            getattr(clause, flag, False) for flag in ("is_insert", "is_update", "is_delete")
        ):
            pid = conn.connection.driver_connection.get_server_pid()
            # Public sync commits saved observations before the conduct phase;
            # normal handoff also commits its pre-HTTP checkpoint. The writer
            # PID is the connection executing the CURRENT transaction, not the
            # first connection ever used by that public call.
            self.pids[worker] = pid
        if table := resource(clause):
            self.trace.append((worker, "attempt", table, self.pids[worker]))

    def after(self, conn, clause, multiparams, params, options, result):
        worker, table = role.get(), resource(clause)
        if worker is None or table is None:
            return
        self.trace.append((worker, "acquired", table, self.pids[worker]))
        if worker == "batch" and table == "sellers" and not self.held.is_set():
            self.held.set()

            async def pause(raw):
                try:
                    await asyncio.wait_for(self.release.wait(), 8)
                except TimeoutError:
                    self.harness_errors.append("billing swallowed scheduling timeout")
                    raise

            conn.connection.dbapi_connection.run_async(pause)

    def error(self, context):
        if worker := role.get():
            self.errors.append((worker, sqlstate(context.original_exception)))

    def listeners(self):
        return (("before_execute", self.before), ("after_execute", self.after),
                ("handle_error", self.error))

    async def observe(self):
        async with SessionLocal() as observer:
            async with asyncio.timeout(8):
                while not self.finished.is_set():
                    if set(self.pids) == {"batch", "ordinary"}:
                        # pg_stat_activity is cached within the observer's
                        # transaction. Refresh before reading CURRENT writers.
                        await observer.execute(text("select pg_stat_clear_snapshot()"))
                        rows = (await observer.execute(text(
                            "select pid, pg_blocking_pids(pid), query from pg_stat_activity "
                            "where pid in (:batch, :ordinary)"
                        ), self.pids)).all()
                        waits = {pid: blockers for pid, blockers, _ in rows}
                        batch, ordinary = self.pids["batch"], self.pids["ordinary"]
                        if batch in waits.get(ordinary, []):
                            if not self.wait_seen:
                                self.wait_queries = [tuple(row) for row in rows]
                            self.wait_seen = True
                            self.release.set()
                        if (batch in waits.get(ordinary, [])
                                and ordinary in waits.get(batch, [])):
                            self.cycle_seen = True
                    await asyncio.sleep(0.01)  # poll frequency, never releases a barrier


class BatchOrdinaryTransport(ApproveRaceTransport):
    """Keep the ordinary transport's snapshot checks scoped to supply C.

    The reused single-supply fixture expects one operation in the whole tenant;
    a genuine batch necessarily already has operations for A/B as well.
    """

    async def call(self, *, client_id, api_key, path, payload):
        if path != "/v1/carriage/approve":
            return await super().call(client_id=client_id, api_key=api_key,
                                      path=path, payload=payload)
        self.endpoint_calls.append((path, dict(payload)))
        before = await saved(self.case)
        operations = [op for op in before.operations
                      if str(op.local_entity_id) == str(self.case.supply.id)]
        assert len(operations) == 1
        self.snapshot = copy.deepcopy(operations[0].request_summary_json)
        scope = self.snapshot["ozon_handoff_orders"]
        assert set(scope) == {str(self.case.orders[0].id)}
        assert scope[str(self.case.orders[0].id)]["quantities"] == {
            str(self.case.products[0].id): 1,
        }
        assert self.snapshot["ozon_handoff_progress"]["posting_numbers"] == [
            self.case.orders[0].external_order_id,
        ]
        assert not self.approved
        await self.mutate()
        self.approved = True
        return {}


async def tariffs(case):
    async with SessionLocal() as reader:
        return [dict(row._mapping) for row in await reader.execute(
            select(BillingTariffVersion.__table__)
            .where(BillingTariffVersion.tenant_id == case.tenant.id)
            .order_by(BillingTariffVersion.id)
        )]


def business_issues(case, state, ledger, before):
    issues = []

    def check(condition, message):
        if not condition:
            issues.append(message)

    p1, p2 = case.products
    for product, qty in ((p1, 1), (p2, 2)):
        check(shipped(state, product) == qty, f"expense {product.name} must be {qty}")
        check(state.stock[product.id] == before.stock[product.id] - qty,
              f"stock {product.name} must decrease only by {qty}")
    check(state.reserves == {} and state.position_reserves == {}, "all reservations released")
    check(all(p.reserved_quantity == 0 for p in state.positions), "position reserves are zero")
    check(len([m for m in state.moves if m.movement_type == "fbs_shipment"]) == 3,
          "exactly three shipment movements")
    check(len(state.supplies) == 3 and all(s.delivered_at for s in state.supplies),
          "all three original supplies conducted")
    for order in case.orders:
        entries = order_entries(ledger, order.id)
        check(state.orders[order.id].status == "in_delivery", f"{order.external_order_id} status")
        check(order.id in state.ledgers and state.ledgers[order.id].shipment_movement_id,
              f"{order.external_order_id} persisted expense ledger")
        check(sum(row["amount"] or 0 for row in entries) == 1800,
              f"{order.external_order_id} must have money 1800")
        check(Counter(row["service_code"] for row in entries) == {"fbs_order": 1, "packing": 1},
              f"{order.external_order_id} exactly two service charges")
        check(all(row["quantity"] == 1 and row["entry_type"] == "charge" for row in entries),
              f"{order.external_order_id} charge quantities/types")
        facts = [f for f in state.facts if f.source_event_id == order.id
                 and f.operation_code == "fbs_order"]
        check(len(facts) == 1 and facts[0].item_quantity == 1,
              f"{order.external_order_id} one work fact for one item")
    return issues


async def test_public_sync_batch_and_outside_ordinary_handoff_keep_stock_and_money(
    isolated_pg, db_session, monkeypatch,
):
    case = await seed(db_session, "ozon", count=3)
    a, b, c = case.orders
    p1 = case.products[0]
    p2 = Product(tenant_id=case.tenant.id, seller_id=case.seller.id,
                 name="Batch P2", sku_code=f"batch-p2-{case.tenant.id}")
    db_session.add(p2)
    await db_session.flush()
    db_session.add(InventoryBalance(
        tenant_id=case.tenant.id, product_id=p2.id, storage_location_id=case.location.id,
        quantity=12, quantity_unpacked=12, quantity_packed=0,
    ))
    supplies = [case.supply]
    # Production loop sorts supply UUIDs; choose B/C after A without patching it.
    for offset, order in enumerate((b, c), 1):
        supply = FbsSupply(
            id=uuid.UUID(int=case.supply.id.int + offset), tenant_id=case.tenant.id,
            seller_id=case.seller.id, warehouse_id=case.warehouse.id,
            marketplace="ozon", source="wms", name=f"Batch {'B' if offset == 1 else 'C'}",
            status="assembling", delivery_type="warehouse_sc",
        )
        db_session.add(supply)
        await db_session.flush()
        await inventory.update_fbs_order_reservation(db_session, order, reserve=False)
        order.supply_id = supply.id
        order.product_id = p2.id
        order.product_positions[0].product_id = p2.id
        order.product_positions[0].offer_id = p2.sku_code
        await db_session.flush()
        await inventory.update_fbs_order_reservation(db_session, order, reserve=True)
        supplies.append(supply)
    a.status = b.status = "in_delivery"
    a.wb_status = b.wb_status = "delivering"  # no transition/FK audit before conduct
    c.last_wb_sync_at = datetime.now(UTC)
    a.deadline_at = datetime.now(UTC) + timedelta(days=1)
    b.deadline_at = a.deadline_at + timedelta(seconds=1)
    for code, rate in (("fbs_order", 1000), ("packing", 800)):
        db_session.add(BillingTariffVersion(
            tenant_id=case.tenant.id, seller_id=case.seller.id, service_code=code,
            unit="item", amount=rate, valid_from=date(2020, 1, 1),
        ))
    await db_session.commit()
    ccase = SimpleNamespace(**{**vars(case), "supply": supplies[2], "orders": [c],
                              "products": [p2]})
    await ready_order(db_session, ccase, c, 1)
    case.products = [p1, p2]
    before = await saved(case)
    initial_tariffs = await tariffs(case)
    assert before.position_reserves == {p1.id: 1, p2.id: 2}
    assert before.reserves == {} and not before.charges and not before.moves
    assert len({o.supply_id for o in case.orders}) == len({o.id for o in case.orders}) == 3
    monkeypatch.setattr(ozon_sync, "OZON_STATUS_SYNC_BATCH_LIMIT", 2)
    acase = SimpleNamespace(**{**vars(case), "products": [p1], "orders": [a]})
    bcase = SimpleNamespace(**{**vars(case), "products": [p2], "orders": [b]})
    batch_api = OzonCards(acase)
    batch_api.set(bcase, b, "delivering")

    async def no_change():
        pass

    ordinary_api = BatchOrdinaryTransport(ccase, no_change)

    async def worker(name, operation):
        token = role.set(name)
        try:
            return await operation()
        finally:
            role.reset(token)

    schedule = BatchSchedule()
    tasks = []
    observer = None
    for name, callback in schedule.listeners():
        event.listen(engine.sync_engine, name, callback)
    try:
        tasks.append(asyncio.create_task(worker("batch", lambda: sync(case, batch_api))))
        held = asyncio.create_task(schedule.held.wait())
        try:
            done, _ = await asyncio.wait([tasks[0], held], timeout=8,
                                         return_when=asyncio.FIRST_COMPLETED)
            assert done, f"HARNESS: no batch Seller lock; {schedule.trace}"
            if tasks[0] in done:
                await tasks[0]
                pytest.fail(f"HARNESS: batch finished before Seller barrier; {schedule.trace}")
        finally:
            held.cancel()
            await asyncio.gather(held, return_exceptions=True)
        tasks.append(asyncio.create_task(worker(
            "ordinary", lambda: normal_handoff(ccase, ordinary_api),
        )))
        observer = asyncio.create_task(schedule.observe())
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 15)
        schedule.finished.set()
        try:
            await observer
        except TimeoutError:
            pytest.fail(f"HARNESS: observer timeout; pids={schedule.pids}; "
                        f"trace={schedule.trace}; errors={schedule.errors}; "
                        f"wait={schedule.wait_queries}; results={results}; "
                        f"barrier_errors={schedule.harness_errors}")
    finally:
        schedule.release.set()
        schedule.finished.set()
        for task in [*tasks, *([observer] if observer else [])]:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, *([observer] if observer else []), return_exceptions=True)
        for name, callback in schedule.listeners():
            event.remove(engine.sync_engine, name, callback)

    final = await saved(case)
    ledger = await headers(case)
    issues = business_issues(case, final, ledger, before)
    balances = {o.external_order_id: sum(r["amount"] or 0 for r in order_entries(ledger, o.id))
                for o in case.orders}
    diagnostic = (f"writer_pids={schedule.pids}; pg_cycle={schedule.cycle_seen}; "
                  f"actual_wait={schedule.wait_queries}; trace={schedule.trace}; "
                  f"sqlstates={schedule.errors}; results={results}; balances={balances}; "
                  f"stock={final.stock}; reserves={final.position_reserves}; issues={issues}")
    print(f"BATCH PG evidence: {diagnostic}")
    assert not schedule.harness_errors, f"HARNESS: {diagnostic}"
    assert schedule.wait_seen and len(set(schedule.pids.values())) == 2, f"HARNESS: {diagnostic}"
    assert set(batch_api.requested) == {a.external_order_id, b.external_order_id}, diagnostic
    assert c.external_order_id not in batch_api.requested, "C is outside this sync batch"
    assert not [code for _, code in schedule.errors if code in {"57014", "55P03"}], diagnostic
    if any(code == "40P01" for _, code in schedule.errors):
        assert schedule.cycle_seen, (
            f"HARNESS: SQL deadlock without observed mutual wait: {diagnostic}"
        )
    assert await tariffs(case) == initial_tariffs, "handoff must not change tariffs"

    # A first failure must still be followed by real recovery/retry assertions.
    # Keep the original business errors and SQLSTATE; recovery never erases RED.
    await sync(case, batch_api)
    await normal_handoff(ccase, ordinary_api)
    recovered = await saved(case)
    recovered_ledger = await headers(case)
    issues += [f"recovery: {issue}" for issue in business_issues(
        case, recovered, recovered_ledger, before,
    )]
    calls = list(ordinary_api.endpoint_calls)
    await sync(case, batch_api)
    await normal_handoff(ccase, ordinary_api)
    repeated = await saved(case)
    assert await headers(case) == recovered_ledger, "retry must preserve all money rows"
    assert repeated.stock == recovered.stock
    assert repeated.reserves == recovered.reserves
    assert repeated.position_reserves == recovered.position_reserves
    assert {m.id for m in repeated.moves} == {m.id for m in recovered.moves}
    assert {f.id for f in repeated.facts} == {f.id for f in recovered.facts}
    assert {o.id for o in repeated.operations} == {o.id for o in recovered.operations}
    assert ordinary_api.endpoint_calls == calls, "retry must not repeat external handoff"
    assert await tariffs(case) == initial_tariffs
    assert not schedule.errors and not issues and not any(
        isinstance(result, BaseException) for result in results
    ), f"BATCH stock/money contract: {diagnostic}; all_business_issues={issues}"
