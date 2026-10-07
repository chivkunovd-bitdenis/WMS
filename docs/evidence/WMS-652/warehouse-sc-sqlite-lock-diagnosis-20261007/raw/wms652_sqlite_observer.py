"""Observation-only pytest plugin. No transaction/provider/test control changes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import weakref
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

_LIMIT = 32 * 1024 * 1024
_events = 0
_bytes = 0
_dropped = 0
_tasks: dict = {}
_connections: dict = {}
_sessions: dict = {}
_counters: dict[int, int] = {}
_statements: dict[int, dict] = {}
_transactions: dict[int, int] = {}
_stream = None
_original_create_task = None


def _number(mapping, value):
    key = id(value)
    previous = mapping.get(key)
    if previous is not None and previous[0]() is value:
        return previous[1]
    number = _counters.get(id(mapping), 0) + 1
    _counters[id(mapping)] = number
    try:
        reference = weakref.ref(value)
    except TypeError:
        reference = lambda: value  # Non-weakrefable pooled DBAPI objects only.
    mapping[key] = (reference, number)
    return number


def _task(task=None):
    try:
        task = task or asyncio.current_task()
    except RuntimeError:
        return None
    if task is None:
        return None
    coro = task.get_coro()
    code = getattr(coro, "cr_code", None)
    return {
        "task": _number(_tasks, task),
        "coroutine": getattr(code, "co_qualname", None),
        "file": Path(code.co_filename).name if code else None,
    }


def _record(kind, **data):
    global _events, _bytes, _dropped
    if _stream is None:
        return
    row = {
        "sequence": _events + 1,
        "utc_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "kind": kind,
        "task": _task(),
        **data,
    }
    encoded = json.dumps(row, separators=(",", ":")) + "\n"
    if _bytes + len(encoded.encode()) > _LIMIT:
        _dropped += 1
        return
    _stream.write(encoded)
    _events += 1
    _bytes += len(encoded.encode())


def _connection(conn):
    return _number(_connections, conn.connection.dbapi_connection)


def _sql_shape(statement):
    # Do not record SQL text, parameters, values, headers, user data or secrets.
    words = statement.lstrip().split(None, 1)
    op = words[0].upper() if words else "EMPTY"
    match = re.search(
        r'\b(?:INTO|UPDATE|FROM|TABLE)\s+["`]?([A-Za-z_][A-Za-z_0-9]*)',
        statement,
        re.IGNORECASE,
    )
    return {
        "operation": op
        if op
        in {
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "DROP",
            "PRAGMA",
            "SAVEPOINT",
            "RELEASE",
            "ROLLBACK",
        }
        else "OTHER",
        "table": match.group(1) if match else None,
    }


def _before_cursor(conn, cursor, statement, parameters, context, executemany):
    entry = {"connection": _connection(conn), **_sql_shape(statement)}
    _statements[id(context)] = entry
    _record("sql-start", **entry, transaction=_transactions.get(entry["connection"]))


def _after_cursor(conn, cursor, statement, parameters, context, executemany):
    entry = _statements.pop(
        id(context), {"connection": _connection(conn), **_sql_shape(statement)}
    )
    _record("sql-complete", **entry, transaction=_transactions.get(entry["connection"]))


def _error(context):
    native = context.original_exception
    connection = (
        _connection(context.connection) if context.connection is not None else None
    )
    tasks = []
    try:
        for task in asyncio.all_tasks():
            tasks.append(
                {
                    **(_task(task) or {}),
                    "done": task.done(),
                    "stack": [
                        {
                            "file": Path(f.f_code.co_filename).name,
                            "function": f.f_code.co_name,
                            "line": f.f_lineno,
                        }
                        for f in task.get_stack(limit=8)
                    ],
                }
            )
    except RuntimeError:
        pass
    _record(
        "native-sql-error",
        connection=connection,
        **_sql_shape(context.statement or ""),
        native_type=type(native).__name__,
        sqlite_errorcode=getattr(native, "sqlite_errorcode", None),
        sqlite_errorname=getattr(native, "sqlite_errorname", None),
        active_transactions=dict(_transactions),
        unfinished_statements=list(_statements.values()),
        tasks=tasks,
    )


def _begin(conn):
    number = _connection(conn)
    _transactions[number] = _events + 1
    _record("connection-begin", connection=number, transaction=_transactions[number])


def _commit(conn):
    _record(
        "connection-commit-start",
        connection=_connection(conn),
        transaction=_transactions.get(_connection(conn)),
    )


def _rollback(conn):
    _record(
        "connection-rollback-start",
        connection=_connection(conn),
        transaction=_transactions.get(_connection(conn)),
    )


def _checkin(dbapi, record):
    number = _number(_connections, dbapi)
    _record(
        "pool-checkin", connection=number, transaction=_transactions.pop(number, None)
    )


def _connect(dbapi, record):
    cursor = dbapi.cursor()
    try:
        cursor.execute("PRAGMA journal_mode")
        journal = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout")
        busy = cursor.fetchone()[0]
    finally:
        cursor.close()
    _record(
        "sqlite-connection-settings",
        connection=_number(_connections, dbapi),
        journal_mode=journal,
        busy_timeout_ms=busy,
    )


def _session_begin(session, transaction, connection):
    _record(
        "session-begin",
        session=_number(_sessions, session),
        connection=_connection(connection),
        transaction=_transactions.get(_connection(connection)),
    )


def _session_end(session, transaction):
    _record(
        "session-transaction-ended",
        session=_number(_sessions, session),
        nested=transaction.nested,
    )


def _session_commit(session):
    _record("session-commit-complete", session=_number(_sessions, session))


def _session_rollback(session):
    _record("session-rollback-complete", session=_number(_sessions, session))


def _session_flush(session, context, instances):
    _record(
        "session-before-flush",
        session=_number(_sessions, session),
        new_count=len(session.new),
        dirty_count=len(session.dirty),
        deleted_count=len(session.deleted),
    )


def _create_task(loop, coro, *args, **kwargs):
    task = _original_create_task(loop, coro, *args, **kwargs)
    code = getattr(coro, "cr_code", None)
    if code and "/app/services/" in code.co_filename:
        _record("service-task-launch", launched=_task(task))
        task.add_done_callback(
            lambda finished: _record(
                "service-task-settled",
                settled=_task(finished),
                canceled=finished.cancelled(),
            )
        )
    return task


def pytest_collection_finish(session):
    global _stream, _original_create_task
    worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    assert re.fullmatch(r"controller|gw[0-9]+", worker)
    out = Path(os.environ["WMS652_SQLITE_EVIDENCE"])
    out.mkdir(parents=True, exist_ok=True)
    _stream = (out / f"transactions-{worker}.jsonl").open("w", buffering=1)
    from app.db.session import engine

    assert engine.dialect.name == "sqlite", "observe only isolated worker SQLite"
    assert Path(engine.url.database).name.startswith("wms_pytest_"), (
        "unchanged conftest isolated identity"
    )
    _record(
        "collector-start",
        worker=worker,
        database_basename=Path(engine.url.database).name,
        collected=[item.nodeid for item in session.items],
        byte_limit=_LIMIT,
        observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    for name, callback in [
        ("connect", _connect),
        ("begin", _begin),
        ("commit", _commit),
        ("rollback", _rollback),
        ("checkin", _checkin),
        ("before_cursor_execute", _before_cursor),
        ("after_cursor_execute", _after_cursor),
        ("handle_error", _error),
    ]:
        event.listen(engine.sync_engine, name, callback)
    for name, callback in [
        ("after_begin", _session_begin),
        ("after_transaction_end", _session_end),
        ("after_commit", _session_commit),
        ("after_rollback", _session_rollback),
        ("before_flush", _session_flush),
    ]:
        event.listen(Session, name, callback)
    _original_create_task = asyncio.BaseEventLoop.create_task
    asyncio.BaseEventLoop.create_task = _create_task


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    _record("test-protocol-start", nodeid=item.nodeid)
    yield
    _record("test-protocol-end", nodeid=item.nodeid)


def pytest_sessionfinish(session, exitstatus):
    global _stream
    if _stream is None:
        return
    _record(
        "collector-end",
        exitstatus=int(exitstatus),
        events=_events,
        bytes=_bytes,
        dropped=_dropped,
    )
    worker = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    Path(os.environ["WMS652_SQLITE_EVIDENCE"], f"completion-{worker}.json").write_text(
        json.dumps(
            {
                "exitstatus": int(exitstatus),
                "events": _events,
                "bytes": _bytes,
                "dropped": _dropped,
                "active_transactions": _transactions,
            },
            indent=2,
        )
    )
    _stream.close()
    _stream = None
    if _original_create_task:
        asyncio.BaseEventLoop.create_task = _original_create_task
