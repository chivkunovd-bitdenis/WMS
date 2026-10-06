"""Additional public-entrypoint sales/recovery contract; fake only HTTP/Redis I/O."""

# ruff: noqa: F811 -- pytest injects the imported sales_http fixture by name.

import json
import uuid
from itertools import pairwise
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from test_withdrawal_orchestration import MOD, Emulator
from test_wms517_sales_contract import (
    build,
    fixture_order,
    prepare,
    sale,
    sales_http,  # noqa: F401 -- public HTTP boundary fixture
)

from app.api.marking_withdrawals import withdrawal_products
from app.core.settings import settings
from app.db.session import SessionLocal
from app.db.withdrawal_repository import WithdrawalError, current_items, get_operation, registry
from app.models.marking_withdrawal import WithdrawalDocument, WithdrawalOperation
from app.services import wb_sales_report
from app.services.withdrawal_orchestration import scoped_documents
from app.services.withdrawal_service import create_operation, retry_operation


@pytest.fixture
def redis_boundary(monkeypatch, sales_http):
    """Two Redis clients share a deterministic server clock/store at the I/O edge."""
    server = SimpleNamespace(now=0, slots={}, cache={}, writes=[], clients=[], http_times=[])

    class Client:
        def __init__(self):
            self.closed = False
            server.clients.append(self)

        async def eval(self, script, numkeys, key, *args):
            assert numkeys == 1 and "TIME" in script
            if args:
                server.slots[key] = max(server.slots.get(key, 0), server.now + int(args[0]))
                return 1
            slot = max(server.now, server.slots.get(key, 0))
            server.slots[key] = slot + 61000
            return slot - server.now

        async def get(self, key):
            value, until = server.cache.get(key, (None, 0))
            return value if until > server.now else None

        async def set(self, key, value, *, ex):
            server.writes.append((key, value, ex))
            server.cache[key] = (value, server.now + ex * 1000)

        async def aclose(self):
            self.closed = True

    def from_url(url, **kwargs):
        assert url == "redis://fixture.invalid/0"
        return Client()

    async def pause(seconds):
        sales_http.waits.append(seconds)
        server.now += round(seconds * 1000)

    original = sales_http.handle

    async def handle(request):
        server.http_times.append(server.now)
        response = await original(request)
        if response.status_code == 429:
            response.headers["Retry-After"] = "120"
        return response

    monkeypatch.setattr(settings, "celery_broker_url", "redis://fixture.invalid/0")
    monkeypatch.setattr(wb_sales_report, "Redis", SimpleNamespace(from_url=from_url))
    monkeypatch.setattr(wb_sales_report.asyncio, "sleep", pause)
    monkeypatch.setattr(sales_http, "handle", handle)
    return server


async def test_shared_redis_limits_two_public_callers_and_retry_after(
    db_session, sales_http, redis_boundary
):
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    assert (await registry(db_session, scope))[1] == 1
    async with SessionLocal() as other:
        op = await create_operation(
            other, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
        await other.commit()
        assert op.id
    times = redis_boundary.http_times
    assert len(times) == 4
    assert all(right - left >= 61000 for left, right in pairwise(times))
    assert len(redis_boundary.slots) == 1, "separate clients must share the seller's limiter"
    sales_http.status = 429
    # A new independent seller must not inherit the first seller's slot/cache.
    other_scope, other_marking, _, _ = await fixture_order(db_session, sales_http)
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, other_scope, row_ids=[other_marking.id], client_request_id=uuid.uuid4()
        )
    last = redis_boundary.http_times[-1]
    sales_http.status = None
    await create_operation(
        db_session, other_scope, row_ids=[other_marking.id], client_request_id=uuid.uuid4()
    )
    assert redis_boundary.http_times[-2] - last >= 120000
    assert len(redis_boundary.slots) == 2
    assert len(redis_boundary.clients) >= 4
    assert all(client.closed for client in redis_boundary.clients)


async def test_complete_cache_serves_products_but_failed_fresh_create_preserves_cache(
    db_session, sales_http, redis_boundary
):
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    assert (await registry(db_session, scope))[1] == 1
    cached = dict(redis_boundary.cache)
    calls = len(sales_http.requests)
    sales_http.status = 403
    assert await withdrawal_products(db_session, scope, search=None, limit=100)
    assert len(sales_http.requests) == calls
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
    assert len(sales_http.requests) == calls + 1
    assert redis_boundary.cache == cached
    assert all(ttl == 300 for _, _, ttl in redis_boundary.writes)
    assert await db_session.scalar(select(func.count(WithdrawalOperation.id))) == 0
    sales_http.status = None
    sales_http.rows = [sale(order.wb_rid, identifier="R1", price="-123.45")]
    with pytest.raises(WithdrawalError):
        await create_operation(
            db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
        )
    assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 0
    # Expiration must cause a fresh registry read, which observes the return.
    redis_boundary.now += 300001
    assert (await registry(db_session, scope))[1] == 0


async def test_cursor_seventh_fraction_digit_and_latest_saved_source(db_session, sales_http):
    scope, marking, order, _ = await fixture_order(db_session, sales_http)
    first = sale(order.wb_rid, changed="2026-10-05T12:00:00.1234567")
    latest = sale(order.wb_rid, changed="2026-10-05T12:00:00.1234568")
    sales_http.pages = [[first], [first, latest], []]
    op = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=uuid.uuid4()
    )
    assert len(sales_http.requests) == 3
    assert sales_http.requests[1].url.params["dateFrom"] == first["lastChangeDate"]
    assert sales_http.requests[2].url.params["dateFrom"] == latest["lastChangeDate"]
    evidence = (await current_items(db_session, scope, op.id))[0].preflight_evidence["wb_sale"]
    assert evidence["lastChangeDate"] == latest["lastChangeDate"]
    assert evidence["raw_sale"]["lastChangeDate"] == latest["lastChangeDate"]
    assert evidence["complete"] and evidence["pages"] == 3


async def test_failed_fresh_build_keeps_prior_attempt_exact_document(db_session, sales_http):
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    emulator = Emulator([MOD])
    async with httpx.AsyncClient(transport=httpx.MockTransport(emulator.handle)) as http:
        runtime = emulator.runtime(http)
        op = await prepare(db_session, scope, marking, runtime, emulator)
        op = await build(db_session, scope, op, runtime, emulator)
        doc = (await scoped_documents(db_session, scope, op))[0]
        item = (await current_items(db_session, scope, op.id))[0]
        op_id, doc_id = op.id, doc.id
        before = (
            doc.exact_payload,
            doc.payload_sha256,
            json.dumps(item.preflight_evidence, sort_keys=True),
        )
        item.state = "failed"
        item.error = {"source": "crpt", "code": "definite-terminal-reject"}
        doc.state = "failed"
        op.state = "failed"
        await db_session.commit()
        op = await retry_operation(db_session, scope, op_id, expected_attempt=1)
        await db_session.commit()
        assert op.attempt == 2
        # Prepare the new attempt's certificate without creating another operation.
        from datetime import UTC, datetime, timedelta

        from app.services.withdrawal_orchestration import CertificateSelection, prepare_challenge

        op = await prepare_challenge(
            db_session,
            scope,
            op_id,
            CertificateSelection("fixture-thumb", datetime.now(UTC) + timedelta(hours=1)),
            runtime,
        )
        sales_http.status = 403
        op = await build(db_session, scope, op, runtime, emulator)
        await db_session.rollback()
        op = await get_operation(db_session, scope, op_id)
        old_doc = await db_session.get(WithdrawalDocument, doc_id)
        from app.models.marking_withdrawal import WithdrawalItem

        old_item = await db_session.scalar(
            select(WithdrawalItem).where(
                WithdrawalItem.operation_id == op_id, WithdrawalItem.attempt == 1
            )
        )
        assert before == (
            old_doc.exact_payload,
            old_doc.payload_sha256,
            json.dumps(old_item.preflight_evidence, sort_keys=True),
        )
        assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 1
        assert op.attempt == 2 and op.workflow_error
        assert op.workflow_lease_id is None
        assert not any(path.endswith("/lk/documents/create") for path in emulator.calls)


@pytest.mark.parametrize("state", ["created", "reconciling"])
async def test_new_request_resumes_saved_claim_without_fresh_sales(db_session, sales_http, state):
    scope, marking, _, _ = await fixture_order(db_session, sales_http)
    request_id = uuid.uuid4()
    op = await create_operation(
        db_session, scope, row_ids=[marking.id], client_request_id=request_id
    )
    op.state = state
    await db_session.commit()
    op_id, calls = op.id, len(sales_http.requests)
    sales_http.status = 403
    for request in (request_id, uuid.uuid4()):
        async with SessionLocal() as other:
            resumed = await create_operation(
                other, scope, row_ids=[marking.id], client_request_id=request
            )
            assert resumed.id == op_id and resumed.state == state and resumed.attempt == 1
    assert len(sales_http.requests) == calls
    assert await db_session.scalar(select(func.count(WithdrawalOperation.id))) == 1
    assert await db_session.scalar(select(func.count(WithdrawalDocument.id))) == 0
