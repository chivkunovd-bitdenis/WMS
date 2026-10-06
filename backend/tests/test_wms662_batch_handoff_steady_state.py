"""One steady-state variant of the frozen 7f62e184 public batch contract.

Only A/B supplier_status and required_meta_json differ before the setup commit.
Reuse helpers/barrier unchanged; SQL diagnostics observe rather than alter locks.
Run serially on an independently owned loopback PostgreSQL cluster, port 55468.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from test_wms662_batch_handoff_lock_order import (
    BatchOrdinaryTransport,
    BillingTariffVersion,
    FbsSupply,
    InventoryBalance,
    OzonCards,
    Product,
    SessionLocal,
    business_issues,
    engine,
    fake_credentials_and_no_network,  # noqa: F401 -- synthetic credentials, no HTTP
    headers,
    inventory,
    normal_handoff,
    order_entries,
    ozon_sync,
    ready_order,
    resource,
    role,
    saved,
    seed,
    sync,
    tariffs,
)
from test_wms662_batch_handoff_lock_order import (
    BatchSchedule as FrozenBatchSchedule,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def isolated_pg():
    assert engine.dialect.name == "postgresql", "requires isolated real PostgreSQL"
    assert (engine.url.host, engine.url.port, engine.url.database, engine.url.username) == (
        "127.0.0.1", 55468, "wms_test_662_steady", "wms_test",
    )
    assert not os.environ.get("PYTEST_XDIST_WORKER"), "run serially in one process"
    async with SessionLocal() as reader:
        assert await reader.scalar(text(
            "select count(*) from pg_stat_activity where datname=current_database() "
            "and pid<>pg_backend_pid() and backend_type='client backend'"
        )) == 0, "database must be idle before schema setup"
    yield
    await engine.dispose()


class BatchSchedule(FrozenBatchSchedule):
    """Add parameter evidence without changing the inherited synchronization."""

    def __init__(self):
        super().__init__()
        self.product_locks = []
        self.order_updates = []

    @staticmethod
    def parameters(clause, multiparams, params):
        values = dict(clause.compile().params)
        for group in multiparams:
            if isinstance(group, dict):
                values.update(group)
        values.update(params)
        return {key: str(value) for key, value in values.items()}

    def before(self, conn, clause, multiparams, params, options):
        super().before(conn, clause, multiparams, params, options)
        worker = role.get()
        if worker is None:
            return
        pid = conn.connection.driver_connection.get_server_pid()
        values = self.parameters(clause, multiparams, params)
        if resource(clause) == "products":
            self.product_locks.append((worker, "attempt", pid, values))
        if (getattr(clause, "is_update", False)
                and getattr(getattr(clause, "table", None), "name", None) == "fbs_orders"):
            self.order_updates.append((worker, "attempt", pid, str(clause), values))

    def after(self, conn, clause, multiparams, params, options, result):
        worker = role.get()
        if worker is not None:
            pid = conn.connection.driver_connection.get_server_pid()
            values = self.parameters(clause, multiparams, params)
            if resource(clause) == "products":
                self.product_locks.append((worker, "acquired", pid, values))
            if (getattr(clause, "is_update", False)
                    and getattr(getattr(clause, "table", None), "name", None) == "fbs_orders"):
                self.order_updates.append((worker, "acquired", pid, str(clause), values))
        super().after(conn, clause, multiparams, params, options, result)


async def test_steady_state_public_sync_batch_and_outside_ordinary_handoff_keep_stock_and_money(
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
    a.supplier_status = b.supplier_status = "delivering"
    a.required_meta_json = []
    b.required_meta_json = []
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
    print(f"STEADY STATE SQL evidence: product_ids={dict(P1=str(p1.id), P2=str(p2.id))}; "
          f"order_ids={dict(A=str(a.id), B=str(b.id), C=str(c.id))}; "
          f"product_locks={schedule.product_locks}; order_updates={schedule.order_updates}")
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
