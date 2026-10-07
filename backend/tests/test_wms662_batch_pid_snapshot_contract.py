"""Actual BatchSchedule lifecycle with controlled PID/pg_stat_activity boundaries."""

import ast
import asyncio
import subprocess
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, select, text
from sqlalchemy.dialects import postgresql


def source_bytes(name):
    path = Path(__file__).with_name(name)
    if path.exists():
        return path.read_bytes()
    root = Path(__file__).resolve().parents[2]
    return subprocess.check_output(["git", "show", f"HEAD:backend/tests/{name}"], cwd=root)


def actual_schedule(observer):
    source = ast.parse(source_bytes("test_wms662_batch_handoff_lock_order.py"))
    helpers = ast.parse(source_bytes("test_wms662_cancellation_lock_order.py"))
    nodes = [node for node in helpers.body
             if isinstance(node, ast.FunctionDef) and node.name in {"resource", "sqlstate"}]
    nodes += [node for node in source.body
              if isinstance(node, ast.ClassDef) and node.name == "BatchSchedule"]
    assert len(nodes) == 3, "extract the actual class and its exact two native SQL helpers"
    role = ContextVar("controlled_batch_writer", default=None)
    namespace = {"asyncio": asyncio, "role": role, "text": text, "postgresql": postgresql,
                 "SessionLocal": lambda: observer}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "actual_batch_schedule", "exec"),
         namespace)
    return namespace["BatchSchedule"](), role


class ObserverBoundary:
    def __init__(self):
        self.poll = 0
        self.parameters = []
        self.before_poll = lambda: None
        self.reply = lambda: []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, statement, parameters=None):
        if "pg_stat_clear_snapshot" in str(statement):
            self.before_poll()
            return SimpleNamespace(all=lambda: [])
        assert "pg_blocking_pids" in str(statement)
        queried = dict(parameters)
        self.parameters.append(queried)
        # A controlled native observer reply contains only the requested PIDs.
        rows = [row for row in self.reply() if row[0] in queried.values()]
        self.poll += 1
        return SimpleNamespace(all=lambda: rows)


def writer(schedule, role, name, pid, *, locked_select=False):
    driver = SimpleNamespace(get_server_pid=lambda: pid)
    connection = SimpleNamespace(connection=SimpleNamespace(driver_connection=driver))
    table = Table("products", MetaData(), Column("id", Integer, primary_key=True))
    clause = select(table.c.id).with_for_update() if locked_select else table.update().values(id=1)
    token = role.set(name)
    try:
        schedule.before(connection, clause, (), {}, {})
    finally:
        role.reset(token)


async def await_release(schedule, task):
    waiter = asyncio.create_task(schedule.release.wait())
    try:
        done, _ = await asyncio.wait((waiter, task), return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            await task  # propagate the actual observer's failure rather than hang
        assert schedule.release.is_set(), "actual observer must prove a wait before release"
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


@pytest.mark.asyncio
async def test_first_proven_wait_writer_snapshot_survives_later_pooled_pid_reuse():
    observer = ObserverBoundary()
    schedule, role = actual_schedule(observer)
    writer(schedule, role, "batch", 101, locked_select=True)
    writer(schedule, role, "ordinary", 202)
    at_release = []
    native_release = schedule.release.set

    def record_release():
        if not at_release:
            at_release.append(dict(schedule.pids))
        native_release()

    schedule.release.set = record_release

    def advance_before_real_wait():
        if observer.poll == 1:
            assert not schedule.wait_seen and not schedule.release.is_set()
            writer(schedule, role, "batch", 219)
            writer(schedule, role, "ordinary", 209)

    observer.before_poll = advance_before_real_wait
    observer.reply = lambda: ([(101, [], "initial batch"), (202, [], "initial ordinary")]
                              if observer.poll == 0 else
                              [(219, [], "seller lock"), (209, [219], "reversal-ledger INSERT")])
    task = asyncio.create_task(schedule.observe())
    try:
        await await_release(schedule, task)
        assert schedule.wait_seen
        assert observer.parameters[:2] == [
            {"batch": 101, "ordinary": 202}, {"batch": 219, "ordinary": 209},
        ]
        assert at_release == [{"batch": 219, "ordinary": 209}], (
            "the writer evidence must be captured at the first proven wait, before release"
        )
        assert schedule.wait_queries == [
            (219, [], "seller lock"), (209, [219], "reversal-ledger INSERT"),
        ]
        writer(schedule, role, "ordinary", 219)
        print(f"First wait={at_release}; later exposed pids={schedule.pids}")
        assert schedule.pids == at_release[0], (
            "first proven concurrent writer snapshot must survive later pooled PID reuse"
        )
        assert len(set(schedule.pids.values())) == 2
    finally:
        schedule.finished.set()
        await task


@pytest.mark.asyncio
async def test_live_cycle_observation_after_pid_change_uses_current_writer_connections():
    observer = ObserverBoundary()
    schedule, role = actual_schedule(observer)
    writer(schedule, role, "batch", 219)
    writer(schedule, role, "ordinary", 209)

    def reply():
        if observer.poll == 0:
            return [(219, [], "seller lock"), (209, [219], "first INSERT wait")]
        schedule.finished.set()
        return [(301, [302], "current batch wait"), (302, [301], "current ordinary wait")]

    observer.reply = reply
    task = asyncio.create_task(schedule.observe())
    try:
        await await_release(schedule, task)
        assert schedule.wait_seen and not schedule.cycle_seen
        writer(schedule, role, "batch", 301, locked_select=True)
        writer(schedule, role, "ordinary", 302)
        await task
        print(f"Current observer parameters={observer.parameters}; cycle={schedule.cycle_seen}")
        assert observer.parameters[-1] == {"batch": 301, "ordinary": 302}, (
            "cycle observation must query live connections, not frozen historical writers"
        )
        assert schedule.cycle_seen, "the actual observer still detects a current mutual wait"
        assert schedule.wait_queries == [
            (219, [], "seller lock"), (209, [219], "first INSERT wait"),
        ], "later cycles must not replace the first wait evidence"
    finally:
        schedule.finished.set()
        await task
