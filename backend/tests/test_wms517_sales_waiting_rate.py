"""R19: a seller's new 429 cooldown also applies to an already sleeping reader."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.settings import settings
from app.services import wb_sales_report


async def test_waiting_reader_rechecks_shared_retry_after_before_http(monkeypatch):
    real_sleep = asyncio.sleep
    now = 0.0
    sleepers = []
    slots = {}
    requests = []
    first_in_http = asyncio.Event()
    release_429 = asyncio.Event()

    async def sleep(seconds):
        future = asyncio.get_running_loop().create_future()
        sleepers.append((now + seconds, future))
        await future

    async def settle():
        for _ in range(20):
            await real_sleep(0)

    async def advance(target):
        nonlocal now
        now = target
        for deadline, future in sleepers:
            if deadline <= now and not future.done():
                future.set_result(None)
        await settle()

    class FakeRedis:
        async def eval(self, script, numkeys, key, *args):
            assert numkeys == 1
            milliseconds = round(now * 1000)
            if script == wb_sales_report._DEFER:
                slots[key] = max(slots.get(key, 0), milliseconds + int(args[0]))
                return 1
            if script == wb_sales_report._RESERVE:
                slot = max(milliseconds, slots.get(key, 0))
                slots[key] = slot + 61000
                return slot - milliseconds
            raise AssertionError("Unexpected Redis script; model its server-side semantics")

        async def get(self, key):
            return slots.get(key)

        async def set(self, key, value, **kwargs):
            slots[key] = value

        async def aclose(self):
            pass

    async def handle(request):
        requests.append((request.headers["Authorization"], now))
        if request.headers["Authorization"] == "fixture-caller-a":
            first_in_http.set()
            await release_429.wait()
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json=[])

    client_factory = httpx.AsyncClient
    monkeypatch.setattr(
        wb_sales_report.httpx,
        "AsyncClient",
        lambda **kwargs: client_factory(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(wb_sales_report.asyncio, "sleep", sleep)
    monkeypatch.setattr(settings, "celery_broker_url", "redis://fixture.invalid/0")
    monkeypatch.setattr(
        wb_sales_report, "Redis", SimpleNamespace(from_url=lambda *a, **kw: FakeRedis())
    )
    monkeypatch.setattr(
        wb_sales_report,
        "get_decrypted_marketplace_token",
        AsyncMock(side_effect=["fixture-caller-a", "fixture-caller-b"]),
    )
    tenant_id, seller_id = uuid.uuid4(), uuid.uuid4()

    async def read():
        return await wb_sales_report.read_sales_report(
            SimpleNamespace(commit=AsyncMock()),
            tenant_id=tenant_id,
            seller_id=seller_id,
            orders=[],
        )

    caller_a = asyncio.create_task(read())
    caller_b = None
    try:
        await first_in_http.wait()
        caller_b = asyncio.create_task(read())
        await settle()
        assert requests == [("fixture-caller-a", 0)]
        assert any(deadline == 61 and not future.done() for deadline, future in sleepers)

        # B already holds the 61-second slot when A's delayed HTTP response arrives.
        release_429.set()
        with pytest.raises(wb_sales_report.WbSalesError, match="wb_sales_incomplete_http_429"):
            await caller_a
        await advance(61)
        assert requests == [("fixture-caller-a", 0)], (
            "B sent HTTP at its old 61-second reservation despite A's Retry-After: 120"
        )
        assert not caller_b.done(), "B must remain waiting during the shared cooldown"

        # Also prove eventual progress, without real-time sleeps or a database.
        for _ in range(10):
            pending = [deadline for deadline, future in sleepers if not future.done()]
            if caller_b.done():
                break
            assert pending, "B stalled without a scheduled wakeup"
            await advance(min(pending))
        assert caller_b.done(), "B never resumed after the cooldown"
        report = await caller_b
        assert report.pages == 1 and report.row_count == 0
        assert len(requests) == 2 and requests[1][1] >= 120
    finally:
        for task in (caller_a, caller_b):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (caller_a, caller_b) if task), return_exceptions=True
        )
