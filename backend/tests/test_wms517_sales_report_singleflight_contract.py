"""IC11-IC14: real readers/Redis Lua, two module replicas, controlled HTTP/clock.

Redis is a dedicated subprocess on a private Unix socket; no application broker,
credentials, real WB requests or real 61-second waits are accessed.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.settings import settings
from app.services import wb_sales_report

_REAL_SLEEP = asyncio.sleep


@pytest_asyncio.fixture
async def redis_ownership_io():
    binary = shutil.which("redis-server")
    assert binary, "WMS-517 Redis contract needs redis-server; install redis-server before pytest"
    socket_directory = tempfile.TemporaryDirectory(prefix="w517-redis-", dir="/tmp")
    socket = Path(socket_directory.name) / "redis.sock"
    process = subprocess.Popen(
        [binary, "--port", "0", "--unixsocket", str(socket), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    real_sleep = _REAL_SLEEP
    redis = Redis(unix_socket_path=str(socket), decode_responses=True)
    try:
        for _ in range(100):
            if socket.exists():
                break
            await real_sleep(0.01)
        await redis.ping()
        yield SimpleNamespace(client=redis, socket=str(socket))
    finally:
        await redis.aclose()
        process.terminate()
        process.wait(timeout=3)
        socket_directory.cleanup()


@pytest_asyncio.fixture
async def readers(redis_ownership_io, monkeypatch):
    redis = redis_ownership_io.client
    socket = redis_ownership_io.socket
    real_sleep = _REAL_SLEEP
    now = 0.0
    reservations = []
    requests = []
    entered = asyncio.Event()
    release = asyncio.Event()
    status = 200
    held_tokens = {"owner"}
    changed = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    sale = {
        "srid": "rid-1",
        "saleID": "S1",
        "finishedPrice": "123.45",
        "date": changed,
        "lastChangeDate": changed,
    }
    pages_by_token = {}
    replicas = []

    class Client(Redis):
        async def eval(self, script, numkeys, *keys_and_args):
            nonlocal now
            if script == wb_sales_report._RESERVE:
                key = keys_and_args[0]
                slot = max(now, float(await redis.get(key) or now))
                await redis.set(key, slot + 61)
                reservations.append(key)
                return round((slot - now) * 1000)
            if script == wb_sales_report._DEFER:
                key, milliseconds, generation = keys_and_args
                await redis.set(
                    key, max(now + int(milliseconds) / 1000, float(await redis.get(key) or 0))
                )
                await redis.set(key + ":defer", generation)
                return 1
            # Execute the implementation's actual atomic owner/lease Lua in Redis.
            return await super().eval(script, numkeys, *keys_and_args)

    async def sleep(seconds):
        nonlocal now
        now += seconds
        await real_sleep(0.001)

    async def handle(request):
        assert request.method == "GET" and request.url.path == wb_sales_report.SALES_SOURCE
        token = request.headers["Authorization"]
        requests.append((token, str(request.url.params["dateFrom"])))
        index = pages_by_token.get(token, 0)
        pages_by_token[token] = index + 1
        if token in held_tokens and index == 0:
            entered.set()
            await release.wait()
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "120"}, json={"error": "fixture"})
        return httpx.Response(200, json=[sale] if index == 0 else [])

    factory = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: factory(transport=httpx.MockTransport(handle), **kw)
    )
    monkeypatch.setattr(settings, "celery_broker_url", "redis://fixture.invalid/0")
    monkeypatch.setattr(asyncio, "sleep", sleep)
    for index in range(2):
        name = f"wms517_fixture_replica_{index}_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, wb_sales_report.__file__)
        assert spec and spec.loader
        replica = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, replica)
        spec.loader.exec_module(replica)
        monkeypatch.setattr(
            replica,
            "Redis",
            SimpleNamespace(
                from_url=lambda *a, **kw: Client(
                    unix_socket_path=str(socket), decode_responses=True
                )
            ),
        )

        async def token(session, *_args):
            return session.fixture_token

        monkeypatch.setattr(replica, "get_decrypted_marketplace_token", token)
        replicas.append(replica)
    tenant, seller = uuid.uuid4(), uuid.uuid4()
    orders = [
        wb_sales_report.SalesOrder(uuid.uuid4(), "rid-1", datetime.now(UTC) - timedelta(days=7))
    ]
    tasks = []

    async def read(index=0, *, token="owner", fresh=False, scope=None, order_list=None):
        session = SimpleNamespace(commit=AsyncMock(), fixture_token=token)
        result = await replicas[index].read_sales_report(
            session,
            tenant_id=(scope or (tenant, seller))[0],
            seller_id=(scope or (tenant, seller))[1],
            orders=orders if order_list is None else order_list,
            fresh=fresh,
        )
        session.commit.assert_awaited()
        return result

    def start(*args, **kwargs):
        task = asyncio.create_task(read(*args, **kwargs))
        tasks.append(task)
        return task

    async def settle():
        for _ in range(20):
            await real_sleep(0.001)

    async def finish(task):
        return await asyncio.wait_for(task, 2)

    async def ownership_keys():
        return [
            key
            for key in await redis.keys("wb:sales:*")
            if ":complete:" not in key and ":rate:" not in key
        ]

    state = SimpleNamespace(
        redis=redis,
        read=read,
        start=start,
        settle=settle,
        finish=finish,
        requests=requests,
        reservations=reservations,
        entered=entered,
        release=release,
        held_tokens=held_tokens,
        orders=orders,
        tenant=tenant,
        seller=seller,
        ownership_keys=ownership_keys,
        replicas=replicas,
    )

    def configure_status(value):
        nonlocal status
        status = value
        pages_by_token.clear()

    state.set_status = configure_status
    try:
        yield state
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_ic11_two_replica_clients_share_one_complete_vendor_loop(readers):
    owner = readers.start(0)
    await asyncio.wait_for(readers.entered.wait(), 2)
    waiter = readers.start(1, token="waiter")
    await readers.settle()
    readers.release.set()
    first, second = await asyncio.gather(readers.finish(owner), readers.finish(waiter))
    assert len(readers.requests) == 2, (
        "Registry and product reads duplicated a complete WB page loop"
    )
    assert len(readers.reservations) == 2, "A waiting reader consumed extra seller rate slots"
    assert first.by_rid == second.by_rid and first.received_at == second.received_at
    assert first.pages == second.pages == 2 and first.row_count == second.row_count == 1
    assert first.date_from == second.date_from
    assert "rid-1" in first.by_rid


async def test_ic12_cancelled_waiter_does_not_duplicate_or_cancel_owner(readers):
    owner = readers.start(0)
    await asyncio.wait_for(readers.entered.wait(), 2)
    cancelled = readers.start(1, token="cancelled")
    latest = readers.start(1, token="latest")
    await readers.settle()
    cancelled.cancel()
    await asyncio.gather(cancelled, return_exceptions=True)
    readers.release.set()
    reports = await asyncio.gather(readers.finish(owner), readers.finish(latest))
    assert len(readers.requests) == 2, "Filter callers launched their own WB reads"
    assert len(readers.reservations) == 2
    assert reports[0].received_at == reports[1].received_at and reports[1].row_count == 1


@pytest.mark.parametrize("status", [429, 503])
async def test_ic13_owner_failure_is_finite_and_explicit_retry_recovers(readers, status):
    readers.set_status(status)
    owner = readers.start(0)
    await asyncio.wait_for(readers.entered.wait(), 2)
    waiter = readers.start(1, token="waiter")
    await readers.settle()
    readers.release.set()
    errors = await asyncio.gather(
        readers.finish(owner), readers.finish(waiter), return_exceptions=True
    )
    assert all(isinstance(error, ValueError) for error in errors), (
        "Failed owner left an infinite waiter"
    )
    assert not await readers.redis.keys("wb:sales:complete:*"), (
        "Partial failure was cached as complete"
    )
    readers.set_status(200)
    report = await readers.finish(readers.start(1, token="retry"))
    assert report.pages == 2 and report.row_count == 1


async def test_ic13_expired_owner_cannot_release_replacement_lease(readers):
    owner = readers.start(0)
    await asyncio.wait_for(readers.entered.wait(), 2)
    keys = await readers.ownership_keys()
    assert len(keys) == 1, "Cold report must have a shared finite owner lease"
    old_value = await readers.redis.get(keys[0])
    assert await readers.redis.pttl(keys[0]) > 0, "Ownership must expire after process loss"
    # Force expiry at the Redis I/O boundary, without waiting real minutes.
    await readers.redis.pexpire(keys[0], 1)
    await readers.settle()
    readers.held_tokens.add("replacement")
    replacement = readers.start(1, token="replacement")
    for _ in range(50):
        await readers.settle()
        if any(token == "replacement" for token, _ in readers.requests):
            break
    new_value = await readers.redis.get(keys[0])
    assert new_value and new_value != old_value, "A new caller could not recover an expired lease"
    # Cancelling the former owner must compare its lease token before deleting.
    owner.cancel()
    await asyncio.gather(owner, return_exceptions=True)
    assert await readers.redis.get(keys[0]) == new_value, "Old owner deleted a newer reader's lease"
    readers.release.set()
    report = await readers.finish(replacement)
    assert report.row_count == 1


async def test_ic14_scope_order_digest_ttl_and_fresh_read_are_preserved(readers):
    readers.release.set()
    cached = await readers.read(0)
    calls = len(readers.requests)
    same = await readers.read(1, token="cached")
    assert len(readers.requests) == calls and same.received_at == cached.received_at
    for scope, order_list in [
        ((uuid.uuid4(), readers.seller), readers.orders),
        ((readers.tenant, uuid.uuid4()), readers.orders),
        (
            (readers.tenant, readers.seller),
            [wb_sales_report.SalesOrder(uuid.uuid4(), "rid-1", readers.orders[0].created_at_wb)],
        ),
    ]:
        await readers.read(1, token=f"scope-{uuid.uuid4()}", scope=scope, order_list=order_list)
        assert len(readers.requests) == calls + 2, (
            "Different tenant/seller/order identity reused foreign evidence"
        )
        calls += 2
    complete = await readers.redis.keys("wb:sales:complete:*")
    for key in complete:
        assert 295 <= await readers.redis.ttl(key) <= 300, "Existing complete-cache TTL300 changed"
    await readers.read(1, token="fresh", fresh=True)
    assert len(readers.requests) == calls + 2, "Fresh signature preparation reused a view report"
    before = {
        key: await readers.redis.get(key) for key in await readers.redis.keys("wb:sales:complete:*")
    }
    readers.set_status(503)
    with pytest.raises(ValueError, match="wb_sales_incomplete"):
        await readers.read(1, token="fresh-failed", fresh=True)
    after = {
        key: await readers.redis.get(key) for key in await readers.redis.keys("wb:sales:complete:*")
    }
    assert before == after, "Failed fresh validation erased prior complete evidence"
    readers.set_status(200)
    for key in await readers.redis.keys("wb:sales:complete:*"):
        await readers.redis.pexpire(key, 1)
    await readers.settle()
    calls = len(readers.requests)
    await readers.read(1, token="after-expiry")
    assert len(readers.requests) == calls + 2, "Expired cache suppressed a fresh WB return check"


async def test_ic14_fresh_validation_does_not_join_an_inflight_view(readers):
    owner = readers.start(0)
    await asyncio.wait_for(readers.entered.wait(), 2)
    fresh = readers.start(1, token="fresh-concurrent", fresh=True)
    fresh_report = await readers.finish(fresh)
    assert fresh_report.pages == 2 and fresh_report.row_count == 1
    assert not owner.done(), "Fresh validation unexpectedly settled the blocked view reader"
    assert len(readers.requests) == 3, (
        "Fresh validation joined the pending view instead of reading WB"
    )
    readers.release.set()
    await readers.finish(owner)
    assert len(readers.requests) == 4
