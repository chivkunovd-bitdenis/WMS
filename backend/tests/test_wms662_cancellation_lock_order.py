"""F6: distinct orders, shared seller/product, real concurrent PostgreSQL paths.

Run serially against the dedicated loopback wms_test_662_f6 database. Only
marketplace I/O is fake. SQLAlchemy events pause *after* an actual row lock,
then release cancellation when handoff attempts that same resource.
Unlike a two-party barrier after both first locks, this schedule also works
after either consistent lock order is implemented: the second worker waits
in PostgreSQL while the first commits. No sleeps decide the interleaving.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from contextvars import ContextVar
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.dialects import postgresql
from test_wms662_approve_scope_race import ApproveRaceTransport, normal_handoff, ready_order
from test_wms662_observed_handoff import (
    OzonCards,
    fake_credentials_and_no_network,  # noqa: F401 -- synthetic credentials, HTTP forbidden
    saved,
    seed,
    shipped,
    sync,
)

from app.db.session import SessionLocal, engine
from app.models.billing import BillingLedgerEntry, BillingTariffVersion
from app.services import fbs_cancellation_service as cancellation
from app.services import ozon_fbs_sync_service as ozon_sync
from app.services.billing_ledger_service import record_operational_charge

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        engine.dialect.name != "postgresql", reason="F6 needs real PostgreSQL locks"
    ),
]
worker_role: ContextVar[str | None] = ContextVar("wms662_f6_worker", default=None)


@pytest_asyncio.fixture(autouse=True)
async def dedicated_pg(db_session):
    # conftest already rejects remote/non-test URLs. Further isolate this suite
    # from the other tester/developer databases; never run it with xdist.
    assert engine.url.host == "127.0.0.1"
    assert engine.url.database == "wms_test_662_f6"
    assert engine.url.port == 55466
    import os

    assert not os.environ.get("PYTEST_XDIST_WORKER")
    async with SessionLocal() as reader:
        identity = (
            await reader.execute(
                text(
                    "select current_database(), current_user, "
                    "inet_server_addr()::text, inet_server_port()"
                )
            )
        ).one()
        assert tuple(identity) == ("wms_test_662_f6", "wms_test", "127.0.0.1/32", 55466)
    yield
    await db_session.close()
    await engine.dispose()


def resource(clause):
    """Inspect the executed Select, including its real PostgreSQL lock mode."""
    if getattr(clause, "_for_update_arg", None) is None:
        return None
    sql = str(clause.compile(dialect=postgresql.dialect()))
    for table in ("products", "sellers"):
        if f"\nFROM {table}\n" in sql or f"\nFROM {table} " in sql:
            assert "FOR UPDATE" in sql or "FOR NO KEY UPDATE" in sql, sql
            return table
    return None


def sqlstate(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if code := getattr(exc, "sqlstate", None):
            return code
        exc = getattr(exc, "orig", None) or exc.__cause__ or exc.__context__
    return None


class LockSchedule:
    def __init__(self):
        self.held = asyncio.Event()
        self.release = asyncio.Event()
        self.first_resource = None
        self.trace = []
        self.errors = []
        self.pids = {}
        self.contended = False
        self.barrier_errors = []

    def before(self, conn, clause, multiparams, params, options):
        role, table = worker_role.get(), resource(clause)
        if role is None or table is None:
            return
        self.pids[role] = conn.connection.driver_connection.get_server_pid()
        self.trace.append((role, "attempt", table, self.pids[role]))
        if role == "handoff" and table == self.first_resource:
            # On c36 handoff already holds product and now requests seller.
            # With consistent order it requests the resource held by cancellation
            # first, allowing ordinary PostgreSQL serialization instead.
            self.contended = True
            self.release.set()

    def after(self, conn, clause, multiparams, params, options, result):
        role, table = worker_role.get(), resource(clause)
        if role is None or table is None:
            return
        self.trace.append((role, "acquired", table, self.pids[role]))
        if role == "cancel" and self.first_resource is None:
            self.first_resource = table
            self.held.set()

            async def pause(raw_connection):
                try:
                    await asyncio.wait_for(self.release.wait(), 5)
                except TimeoutError:
                    # reverse_fbs_order_billing can swallow this exception;
                    # never let that become a false business RED or PASS.
                    self.barrier_errors.append(role)
                    raise

            conn.connection.dbapi_connection.run_async(pause)

    def commit(self, conn):
        if role := worker_role.get():
            self.trace.append(
                (role, "COMMIT", None, conn.connection.driver_connection.get_server_pid())
            )

    def rollback(self, conn):
        if role := worker_role.get():
            self.trace.append(
                (role, "ROLLBACK", None, conn.connection.driver_connection.get_server_pid())
            )

    def error(self, context):
        if role := worker_role.get():
            # Capture even errors swallowed by a billing savepoint handler.
            self.errors.append((role, sqlstate(context.original_exception)))

    def install(self):
        for name, callback in self.listeners():
            event.listen(engine.sync_engine, name, callback)

    def remove(self):
        for name, callback in self.listeners():
            event.remove(engine.sync_engine, name, callback)

    def listeners(self):
        return (
            ("before_execute", self.before),
            ("after_execute", self.after),
            ("commit", self.commit),
            ("rollback", self.rollback),
            ("handle_error", self.error),
        )

    def hierarchy(self):
        """First acquisition of each resource, separated by outer transaction."""
        orders = {"handoff": [], "cancel": []}
        pending = {}
        for role, action, table, pid in self.trace:
            # A fake HTTP callback opens a real independent reader. Its
            # rollback must not erase locks still held by the writer.
            key = (role, pid)
            transaction = pending.setdefault(key, [])
            if action == "acquired" and table not in transaction:
                transaction.append(table)
            if action in {"COMMIT", "ROLLBACK"}:
                if len(transaction) == 2:
                    orders[role].append(tuple(transaction))
                pending[key] = []
        return orders


async def cancel(case, order_id, entry):
    async with SessionLocal() as writer:
        order = await cancellation._lock_order(writer, case.tenant.id, order_id)
        if entry == "local":
            await cancellation._finish_local_cancellation(
                writer,
                case.tenant.id,
                order,
                actor_user_id=None,
            )
        else:
            await writer.refresh(order, attribute_names=["product_positions"])
            await ozon_sync._apply_status(writer, order, "cancelled", None)
        await writer.commit()


async def headers(case):
    async with SessionLocal() as reader:
        return [
            dict(row._mapping)
            for row in await reader.execute(
                select(BillingLedgerEntry.__table__)
                .where(
                    BillingLedgerEntry.tenant_id == case.tenant.id,
                )
                .order_by(BillingLedgerEntry.id)
            )
        ]


def order_entries(ledger, order_id):
    charges = {
        row["id"]
        for row in ledger
        if row["source_type"] == "fbs_order" and row["source_id"] == order_id
    }
    # Reversals have source_type=billing_reversal/source_id=original charge,
    # while reversal_of_id is the stable link back to this order's charge.
    return [row for row in ledger if row["id"] in charges or row["reversal_of_id"] in charges]


@pytest.mark.parametrize("handoff_entry", ["normal", "observed"])
@pytest.mark.parametrize("cancel_entry", ["local", "observed_status"])
async def test_f6_cancel_and_distinct_order_handoff_commit_without_loss_or_duplicate(
    db_session,
    handoff_entry,
    cancel_entry,
):
    case = await seed(db_session, "ozon", count=2)
    handed, cancelled = case.orders
    # B has no shared supply/order lock with A. Exclude B from the poller's
    # external-ID batch as well; the observed worker must genuinely lock A only.
    cancelled.supply_id = None
    cancelled.external_order_id = None
    # Ozon stock identity belongs to product_positions. A nullable legacy
    # primary pointer must not accidentally serialize this race through the
    # status audit's product FK KEY SHARE before the explicit seller lock.
    # Keep the real mapped position/reservation: both orders still consume P.
    cancelled.product_id = None
    assert cancelled.product_positions[0].product_id == handed.product_positions[0].product_id
    for code, rate in (("fbs_order", 1000), ("packing", 800)):
        db_session.add(
            BillingTariffVersion(
                tenant_id=case.tenant.id,
                seller_id=case.seller.id,
                service_code=code,
                unit="item",
                amount=rate,
                valid_from=date(2020, 1, 1),
            )
        )
    await db_session.commit()
    # Existing legacy assembly charges for B make swallowed reversal failures
    # observable as money loss, rather than merely a successful status commit.
    for code in ("fbs_order", "packing"):
        await record_operational_charge(
            db_session,
            tenant_id=case.tenant.id,
            seller_id=case.seller.id,
            source_type="fbs_order",
            source_id=cancelled.id,
            source="fbs",
            service_code=code,
            quantity=Decimal(1),
            occurred_at=datetime.now(UTC),
            performer_id=None,
        )
    await db_session.commit()
    initial_headers = await headers(case)
    assert sum(row["amount"] for row in initial_headers) == 1800
    case.orders = [handed]
    await ready_order(db_session, case, handed, 1)
    before = await saved(case)
    assert handed.id != cancelled.id and before.orders[cancelled.id].supply_id is None
    assert before.position_reserves[case.products[0].id] == 2

    async def no_change():
        pass

    api = ApproveRaceTransport(case, no_change) if handoff_entry == "normal" else OzonCards(case)

    async def handoff():
        if handoff_entry == "normal":
            await normal_handoff(case, api)
        else:
            await sync(case, api)

    async def worker(role, operation):
        token = worker_role.set(role)
        try:
            return await operation()
        finally:
            worker_role.reset(token)

    schedule = LockSchedule()
    tasks = []
    schedule.install()
    try:
        tasks.append(
            asyncio.create_task(
                worker(
                    "cancel",
                    lambda: cancel(case, cancelled.id, cancel_entry),
                )
            )
        )
        # A premature exception is not reported as an environmental barrier timeout.
        held_wait = asyncio.create_task(schedule.held.wait())
        try:
            done, _ = await asyncio.wait(
                [tasks[0], held_wait],
                timeout=5,
                return_when=asyncio.FIRST_COMPLETED,
            )
            assert done, f"HARNESS: cancellation did not reach first lock; {schedule.trace}"
            if tasks[0] in done:
                await tasks[0]
                pytest.fail(
                    f"HARNESS: cancellation completed without product/seller lock; {schedule.trace}"
                )
        finally:
            held_wait.cancel()
            await asyncio.gather(held_wait, return_exceptions=True)
        tasks.append(asyncio.create_task(worker("handoff", handoff)))
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                20,
            )
        except TimeoutError:
            pytest.fail(f"HARNESS timeout is not F6 RED: {schedule.trace}; {schedule.errors}")
    finally:
        schedule.release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        schedule.remove()

    final = await saved(case)
    ledger = await headers(case)
    balances = {
        str(oid): sum(row["amount"] or 0 for row in order_entries(ledger, oid))
        for oid in (handed.id, cancelled.id)
    }
    diagnostics = (
        f"trace={schedule.trace}; sqlstates={schedule.errors}; results={results}; "
        f"stock={final.stock}; reserves={final.position_reserves}; "
        f"A_status={final.orders[handed.id].status}; "
        f"B_status={final.orders[cancelled.id].status}; balances={balances}"
    )
    assert not schedule.barrier_errors, f"HARNESS swallowed barrier timeout: {diagnostics}"
    assert schedule.contended, f"HARNESS: handoff never requested the held resource; {diagnostics}"
    assert set(schedule.pids) == {"handoff", "cancel"}
    assert len(set(schedule.pids.values())) == 2, "must use independent PostgreSQL backends"
    assert not [code for _, code in schedule.errors if code in {"57014", "55P03"}], (
        f"HARNESS statement/lock timeout is not a business deadlock: {diagnostics}"
    )
    assert not [result for result in results if isinstance(result, TimeoutError)], (
        f"HARNESS barrier timeout is not F6 RED: {diagnostics}"
    )
    assert not schedule.errors, (
        f"F6: both operations must finish without 40P01 or SQL error; {diagnostics}"
    )
    assert not [result for result in results if isinstance(result, BaseException)], diagnostics
    hierarchy = schedule.hierarchy()
    # hierarchy() records only transactions acquiring BOTH resources. Handoff
    # must retain its known trace; cancellation may omit Seller entirely.
    # Reject opposed edges wherever both resources are actually acquired.
    assert hierarchy["handoff"], diagnostics
    assert len(set(hierarchy["handoff"] + hierarchy["cancel"])) == 1, (
        f"F6: opposed product/seller lock edges inside outer transactions: {hierarchy}"
    )
    product = case.products[0]
    assert shipped(final, product) == 1
    assert final.stock[product.id] == before.stock[product.id] - 1
    assert final.reserves == {} and final.position_reserves == {}
    assert all(position.reserved_quantity == 0 for position in final.positions)
    assert final.orders[handed.id].status == "in_delivery"
    assert final.orders[cancelled.id].status == "cancelled"
    assert final.orders[cancelled.id].supply_id is None
    assert final.supply.delivered_at is not None
    assert final.ledgers[handed.id].shipment_movement_id is not None
    assert (
        cancelled.id not in final.ledgers
        or final.ledgers[cancelled.id].shipment_movement_id is None
    )
    assert len([move for move in final.moves if move.movement_type == "fbs_shipment"]) == 1
    assert [
        row for row in ledger if row["id"] in {r["id"] for r in initial_headers}
    ] == initial_headers
    by_order = {oid: order_entries(ledger, oid) for oid in (handed.id, cancelled.id)}
    assert sum(row["amount"] for row in by_order[handed.id]) == 1800
    assert Counter(row["service_code"] for row in by_order[handed.id]) == {
        "fbs_order": 1,
        "packing": 1,
    }
    assert sum(row["amount"] for row in by_order[cancelled.id]) == 0
    assert {
        row["reversal_of_id"] for row in by_order[cancelled.id] if row["entry_type"] == "reversal"
    } == {row["id"] for row in initial_headers}
    assert len(by_order[cancelled.id]) == 4
    calls = list(api.endpoint_calls)
    await handoff()
    await cancel(case, cancelled.id, cancel_entry)
    repeated = await saved(case)
    assert await headers(case) == ledger, "retry must neither lose nor duplicate money"
    assert repeated.stock == final.stock
    assert repeated.reserves == final.reserves
    assert repeated.position_reserves == final.position_reserves
    assert {move.id for move in repeated.moves} == {move.id for move in final.moves}
    assert {fact.id for fact in repeated.facts} == {fact.id for fact in final.facts}
    assert {operation.id for operation in repeated.operations} == {
        operation.id for operation in final.operations
    }
    if handoff_entry == "normal":
        assert api.endpoint_calls == calls, "retry must not repeat external handoff"
