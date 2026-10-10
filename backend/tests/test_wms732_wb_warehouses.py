"""WMS-732 C1-C9a: daily FBW loading and append-only cache contract.

Baseline: 0da9f6dd9; initially clean worktree; SQLite pytest environment.
No pre-existing red checks were run. Expected new-behaviour failures: destructive
replacement, first-seller-only lookup, invalid-list acceptance and batch isolation.
Only HTTP I/O is faked. The client parser, credentials, jobs, DB and API are real.
Baseline: 32 cases, 13 expected product failures, 19 preserved-behaviour passes.
Mutation proof: all preserved cases fail for duplicate insertion, loss of cached
API rows, broken key fallback or fabricated empty-response rows. Targeted mutants
also catch skipping nonempty daily caches, corrupting mapped wire fields, logging
a fixture secret and leaking another tenant's catalogue. Only the warehouse
service is mutated, and every mutation is restored byte-for-byte.
C9a fixture schema: https://dev.wildberries.ru/openapi/orders-fbw
GET /api/v1/warehouses, response sample 200 (accessed via indexed official page
2026-10-09; direct open returned 498). This is format proof, not live availability.
"""
from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import event, select

from app.api.wb_mp_warehouses import list_wb_mp_warehouses
from app.celery_app import celery_app
from app.core.settings import settings
from app.db.session import SessionLocal, engine
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.seller import Seller
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.tenant import Tenant
from app.models.tenant_wb_mp_warehouse import TenantWbMpWarehouse
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import wb_mp_warehouse_service as wh
from app.services.integration_fernet import encrypt_secret
from app.tasks.background_jobs import run_wb_mp_warehouses_daily_sync_task

pytestmark = pytest.mark.asyncio
OLD_DATE = datetime(2026, 8, 14, 10, tzinfo=UTC)


def wire_row(wid=507, name="Коледино", **fields):
    return {"ID": wid, "name": name, "address": "Адрес FBW", "workTime": "24/7",
            "isActive": True, "isTransitActive": False, **fields}


class WbReplies:
    """Controlled HTTP boundary; never replaces the operation being tested."""
    def __init__(self):
        self.responses = {}
        self.calls = []
        self.before_reply = None

    def set(self, token, value, status=200):
        self.responses[token] = (status, value)

    async def handle(self, _transport, request):
        token = request.headers.get("Authorization", "")
        self.calls.append((token, request.method, request.url.host, request.url.path))
        assert request.method == "GET"
        assert request.url.path == "/api/v1/warehouses", "FBS/ping must not replace FBW"
        assert request.url.host == "supplies-api.wildberries.ru"
        assert token in self.responses, "unexpected credential / cross-tenant access"
        if self.before_reply:
            await self.before_reply(request)
        status, value = self.responses[token]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, str):
            return httpx.Response(status, text=value, request=request)
        return httpx.Response(status, json=copy.deepcopy(value), request=request)

    @property
    def tokens(self):
        return [token for token, _, _, _ in self.calls]


@pytest.fixture
def wb(monkeypatch):
    fixture = WbReplies()
    async def handle(transport, request):
        return await fixture.handle(transport, request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle)
    monkeypatch.setattr(settings, "e2e_mock_wb_warehouses", False)
    monkeypatch.setattr(settings, "wildberries_supplies_api_base",
                        "https://supplies-api.wildberries.ru")
    return fixture


async def seed(session, number=1, pairs=(("content-732", "supplies-732"),)):
    tenant = Tenant(id=uuid.UUID(int=number), name=f"WMS732 {number}",
                    slug=f"wms732-{uuid.uuid4().hex}")
    warehouse = Warehouse(tenant=tenant, name="Основной склад", code=f"W732-{number}")
    session.add_all([tenant, warehouse])
    await session.flush()
    sellers = []
    for i, pair in enumerate(pairs):
        seller = Seller(tenant_id=tenant.id, name=f"Селлер {number}/{i}",
                        created_at=OLD_DATE + timedelta(seconds=i))
        session.add(seller)
        await session.flush()
        if pair is not None:
            session.add(SellerWildberriesCredentials(
                seller_id=seller.id,
                content_token_encrypted=encrypt_secret(pair[0]) if pair[0] else None,
                supplies_token_encrypted=encrypt_secret(pair[1]) if pair[1] else None,
            ))
        sellers.append(seller)
    await session.commit()
    return SimpleNamespace(tenant=tenant, sellers=sellers, warehouse=warehouse,
                           pairs=pairs)


async def cache(session, case, wid=507, name="Прежний склад", date=OLD_DATE, **fields):
    row = TenantWbMpWarehouse(
        tenant_id=case.tenant.id, wb_warehouse_id=wid, name=name,
        address="Прежний адрес", work_time="09-18", is_active=False,
        is_transit_active=True, fetched_at=date,
    )
    for key, value in fields.items():
        setattr(row, key, value)
    session.add(row)
    await session.commit()
    return row


async def saved(case):
    async with SessionLocal() as reader:
        rows = list(await reader.scalars(select(TenantWbMpWarehouse).where(
            TenantWbMpWarehouse.tenant_id == case.tenant.id,
        ).order_by(TenantWbMpWarehouse.wb_warehouse_id, TenantWbMpWarehouse.id)))
        return {row.id: {column.key: getattr(row, column.key)
                         for column in row.__table__.columns} for row in rows}


def by_number(rows):
    out = {}
    for row in rows.values():
        wid = row["wb_warehouse_id"]
        assert wid not in out, f"duplicate warehouse number {wid} in one tenant"
        out[wid] = row
    return out


async def api(case):
    readings = []
    for _ in range(2):
        async with SessionLocal() as reader:
            # Real API handler, including its actual loading path and serialization.
            user = User(tenant_id=case.tenant.id, role="fulfillment_admin", password_hash="test")
            result = await list_wb_mp_warehouses(user, reader)
            readings.append([row.model_dump() for row in result])
    assert readings[0] == readings[1]
    return readings[1]


async def daily(case):
    await wh.run_daily_wb_mp_warehouses_sync_for_tenant(case.tenant.id)


async def initial(case, path):
    if path == "lazy":
        await api(case)
    else:
        await wh.run_wb_mp_warehouses_sync_task(case.tenant.id, case.sellers[0].id)


async def test_c1_daily_schedule_executes_handler_for_empty_and_nonempty_cache(db_session, wb):
    empty = await seed(db_session, 1, (("empty-732", None),))
    existing = await seed(db_session, 2, (("existing-732", None),))
    await cache(db_session, existing)
    wb.set("empty-732", [wire_row(508, "Новый пустому")])
    wb.set("existing-732", [wire_row(509, "Новый непустому")])
    task = celery_app.conf.beat_schedule["wb-mp-warehouses-daily"]
    assert task["task"] == run_wb_mp_warehouses_daily_sync_task.name
    schedule = copy.copy(task["schedule"])
    schedule.nowfun = lambda: datetime(2026, 10, 9, 3, tzinfo=schedule.tz)
    assert schedule.is_due(datetime(2026, 10, 8, 3, tzinfo=schedule.tz)).is_due
    assert not schedule.is_due(datetime(2026, 10, 9, 3, tzinfo=schedule.tz)).is_due
    assert schedule.hour == {3} and schedule.minute == {0}
    def shape(entry):
        value = entry["schedule"]
        if hasattr(value, "hour"):
            value = (tuple(sorted(value.hour)), tuple(sorted(value.minute)),
                     getattr(value.nowfun, "__name__", None))
        return entry["task"], value
    # Pin unrelated observable schedules to the baseline, not merely to a
    # before/after snapshot that would miss a static configuration regression.
    expected = {
        "developer-requests-sync": (
            "wms.developer_requests_sync", float(settings.trello_sync_interval_sec)),
        "withdrawal-poll": ("wms.withdrawal_poll", 2.0),
        "wb-catalog-hourly": ("wms.wb_catalog_hourly_sync", (tuple(range(24)), (17,), None)),
        "marking-low-stock": ("wms.marking_low_stock", ((0, 6, 12, 18), (15,), None)),
        "fbs-orders-autopoll": ("wms.fbs_orders_autopoll", float(settings.fbs_poll_interval_sec)),
        "fbs-orders-full-reconcile": (
            "wms.fbs_orders_full_reconcile", ((0, 6, 12, 18), (30,), None)),
        "fbs-order-statuses-autopoll": (
            "wms.fbs_order_statuses_autopoll", float(settings.fbs_statuses_sync_interval_sec)),
        "fbs-marking-verdicts-autopoll": ("wms.fbs_marking_verdicts_autopoll", 60.0),
        "fbs-stock-reconcile": (
            "wms.fbs_stock_reconcile", float(settings.fbs_stock_reconcile_interval_sec)),
        "billing-storage-daily": ("wms.billing_storage_daily", ((0,), (0,), "moscow_now")),
    }
    assert {key: shape(value) for key, value in celery_app.conf.beat_schedule.items()
            if key != "wb-mp-warehouses-daily"} == expected
    neighbours = {key: repr(value) for key, value in celery_app.conf.beat_schedule.items()
                  if key != "wb-mp-warehouses-daily"}
    # Run the actual synchronous Celery handler without substituting asyncio.run.
    await asyncio.to_thread(run_wb_mp_warehouses_daily_sync_task.run)
    assert 508 in by_number(await saved(empty))
    assert 509 in by_number(await saved(existing))
    assert set(wb.tokens) == {"empty-732", "existing-732"}
    assert neighbours == {key: repr(value) for key, value in celery_app.conf.beat_schedule.items()
                          if key != "wb-mp-warehouses-daily"}


async def test_c2_adds_new_numbers_without_changing_known_or_absent_rows(db_session, wb):
    case = await seed(db_session)
    a = await cache(db_session, case)
    await cache(db_session, case, 508, "Отсутствует в ответе")
    before = await saved(case)
    wb.set("content-732", [wire_row(507, "Переименован", address="Другой адрес"),
                           wire_row(509, "Новый")])
    await daily(case)
    after = await saved(case)
    assert all(after.get(key) == row for key, row in before.items())
    new = by_number(after)[509]
    assert new["name"] == "Новый" and new["address"] == "Адрес FBW"
    assert new["work_time"] == "24/7" and new["is_active"] is True
    assert new["is_transit_active"] is False
    assert new["fetched_at"] > before[a.id]["fetched_at"]
    assert {row["wb_warehouse_id"] for row in await api(case)} == {507, 508, 509}


async def test_c3_retries_and_duplicate_rows_add_each_number_once(db_session, wb):
    case = await seed(db_session)
    await cache(db_session, case)
    before = await saved(case)
    for payload in ([wire_row(507), wire_row(509)],
                    [wire_row(507), wire_row(509)],
                    [wire_row(507), wire_row(509), wire_row(509)]):
        wb.set("content-732", payload)
        await daily(case)
    after = await saved(case)
    assert len(by_number(after)) == 2
    assert all(after.get(key) == row for key, row in before.items())


@pytest.mark.parametrize("first", ["absent", "401", "403", "empty", "invalid"])
async def test_c4_next_seller_is_tried_after_unusable_first_seller(db_session, wb, first):
    case = await seed(db_session, pairs=(None if first == "absent" else ("bad-732", "bad-732"),
                                         ("good-732", "unused-732")))
    if first != "absent":
        wb.set("bad-732", [{}] if first == "invalid" else [],
               int(first) if first in {"401", "403"} else 200)
    wb.set("good-732", [wire_row(509, "С другого селлера")])
    wb.set("unused-732", [wire_row(510, "Не должен загружаться")])
    await daily(case)
    assert set(by_number(await saved(case))) == {509}
    assert wb.tokens == (["bad-732"] if first != "absent" else []) + ["good-732"]


@pytest.mark.parametrize("failure", [401, 403, 404, "empty"])
async def test_c4_second_key_is_tried_and_search_stops_after_success(db_session, wb, failure):
    case = await seed(db_session, pairs=(("bad-732", "good-732"), ("unused-732", None)))
    wb.set("bad-732", [], failure if isinstance(failure, int) else 200)
    wb.set("good-732", [wire_row(509)])
    wb.set("unused-732", [wire_row(510)])
    await daily(case)
    assert set(by_number(await saved(case))) == {509}
    assert wb.tokens == ["bad-732", "good-732"]


async def test_c4_duplicate_keys_are_not_repeated_across_sellers(db_session, wb):
    case = await seed(db_session, pairs=(("same-732", "same-732"),
                                         ("same-732", "good-732")))
    wb.set("same-732", [], 401)
    wb.set("good-732", [wire_row(509)])
    await daily(case)
    assert wb.tokens == ["same-732", "good-732"]
    assert set(by_number(await saved(case))) == {509}


async def test_c4_all_keys_fail_preserves_cache_and_retries_next_day(db_session, wb):
    case = await seed(db_session)
    await cache(db_session, case)
    before = await saved(case)
    wb.set("content-732", [], 401)
    wb.set("supplies-732", [], 403)
    for _ in range(2):
        await daily(case)
        assert await saved(case) == before
    assert wb.tokens == ["content-732", "supplies-732"] * 2


@pytest.mark.parametrize("failure", [404, 429, 500, "timeout", "invalid", "empty", "malformed"])
async def test_c5_one_tenant_failure_does_not_stop_neighbour_and_recovers(
    db_session, wb, caplog, failure,
):
    first = await seed(db_session, 1, (("failed-secret-732", None),))
    second = await seed(db_session, 2, (("working-secret-732", None),))
    await cache(db_session, first)
    before = await saved(first)
    if failure == "timeout":
        wb.set("failed-secret-732", httpx.ReadTimeout("fixture timeout"))
    elif failure == "invalid":
        wb.set("failed-secret-732", [{"name": "Номер отсутствует"}])
    elif failure == "malformed":
        wb.set("failed-secret-732", "{not JSON")
    else:
        wb.set("failed-secret-732", [], failure if isinstance(failure, int) else 200)
    wb.set("working-secret-732", [wire_row(509)])
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert await saved(first) == before
    assert set(by_number(await saved(second))) == {509}
    assert "failed-secret-732" not in caplog.text and "working-secret-732" not in caplog.text
    wb.set("failed-secret-732", [wire_row(507), wire_row(510)])
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert 510 in by_number(await saved(first))
    assert "failed-secret-732" not in caplog.text and "working-secret-732" not in caplog.text


async def test_c6_database_fault_is_atomic_isolated_and_retry_is_idempotent(db_session, wb):
    first = await seed(db_session, 1, (("first-732", None),))
    second = await seed(db_session, 2, (("second-732", None),))
    await cache(db_session, first)
    before = await saved(first)
    wb.set("first-732", [wire_row(509), wire_row(510)])
    wb.set("second-732", [wire_row(511)])
    triggered = []
    def fail_after_insert(conn, cursor, statement, parameters, context, executemany):
        if not triggered and statement.lstrip().lower().startswith("insert") and (
            "tenant_wb_mp_warehouses" in statement.lower()
        ):
            triggered.append(True)
            raise RuntimeError("wms732-database-fault-after-first-insert")
    event.listen(engine.sync_engine, "after_cursor_execute", fail_after_insert)
    error = None
    try:
        await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    except RuntimeError as exc:
        error = exc
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", fail_after_insert)
    assert triggered, "database fault must actually execute"
    assert await saved(first) == before, "no partial batch or deletion may survive rollback"
    assert 511 in by_number(await saved(second)), (
        "another tenant must finish after local DB failure"
    )
    assert error is None, "per-tenant DB failure must not escape the daily sweep"
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    committed = await saved(first)
    # Replay after a saved result whose reply was lost; this must not rewrite it.
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert await saved(first) == committed
    assert set(by_number(committed)) == {507, 509, 510}


@pytest.mark.parametrize("old_row_arrives_during_fetch", [False, True])
async def test_c7_daily_and_initial_overlap_are_unique_and_preserve_rows(
    db_session, wb, old_row_arrives_during_fetch,
):
    case = await seed(db_session)
    entered = asyncio.Event()
    release = asyncio.Event()
    arrivals = []
    async def barrier(request):
        arrivals.append(True)
        if len(arrivals) == 2:
            entered.set()
        await release.wait()
    wb.before_reply = barrier
    wb.set("content-732", [wire_row(509)])
    tasks = [asyncio.create_task(daily(case)), asyncio.create_task(initial(case, "lazy"))]
    before = {}
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        # The initial read started on an empty cache. A previously saved row can
        # arrive while both WB replies are pending; neither writer may remove it.
        if old_row_arrives_during_fetch:
            await cache(db_session, case)
            before = await saved(case)
        release.set()
        await asyncio.gather(*tasks)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    after = await saved(case)
    assert 509 in by_number(after)
    assert all(after.get(key) == row for key, row in before.items())
    assert len([row for row in after.values() if row["wb_warehouse_id"] == 509]) == 1
    wb.before_reply = None
    other = await seed(db_session, 2, (("other-732", None),))
    wb.set("other-732", [wire_row(509, "Другой фулфилмент")])
    await daily(other)
    own, neighbour = await api(case), await api(other)
    own_by_number = {row["wb_warehouse_id"]: row for row in own}
    assert 509 in own_by_number and len(neighbour) == 1
    assert own_by_number[509]["name"] == "Коледино"
    assert neighbour[0]["name"] == "Другой фулфилмент"
    assert {row["id"] for row in own}.isdisjoint(row["id"] for row in neighbour)


async def unload_snapshot(case):
    async with SessionLocal() as reader:
        rows = list(await reader.scalars(select(MarketplaceUnloadRequest).where(
            MarketplaceUnloadRequest.tenant_id == case.tenant.id,
        )))
        return {row.id: {column.key: getattr(row, column.key)
                         for column in row.__table__.columns} for row in rows}


async def draft(session, case, selected=507):
    row = MarketplaceUnloadRequest(tenant_id=case.tenant.id,
                                  warehouse_id=case.warehouse.id,
                                  seller_id=case.sellers[0].id, marketplace="wb",
                                  wb_mp_warehouse_id=selected, status="draft")
    session.add(row)
    await session.commit()
    return row


async def test_c8_daily_retains_existing_unload_and_selected_warehouse(db_session, wb):
    case = await seed(db_session)
    await cache(db_session, case)
    await draft(db_session, case)
    before = await unload_snapshot(case)
    wb.set("content-732", [wire_row(509)])
    await daily(case)
    assert await unload_snapshot(case) == before
    rows = {row["wb_warehouse_id"]: row for row in await api(case)}
    assert 507 in rows, "cache refresh removed the warehouse selected in an existing FBO draft"
    assert rows[507]["name"] == "Прежний склад"
    assert 509 in rows


@pytest.mark.parametrize("path", ["daily", "lazy", "background"])
async def test_c8_loading_paths_handle_large_optional_and_invalid_rows(db_session, wb, path):
    case = await seed(db_session)
    await draft(db_session, case)
    before = await unload_snapshot(case)
    big = 1020005029603630
    wb.set("content-732", [wire_row(507, "Прежний склад"),
        wire_row(big, "Большой номер", address=None, workTime=None),
        {"ID": 509, "name": "Без необязательных полей"},
        {"ID": 510, "name": ""}, {"name": "Без номера"}, {"ID": 511},
    ])
    if path == "daily":
        await daily(case)
    else:
        await initial(case, path)
    assert set(by_number(await saved(case))) == {507, 509, big}
    rows = {row["wb_warehouse_id"]: row for row in await api(case)}
    assert set(rows) == {507, 509, big}
    assert rows[big]["address"] is None and rows[big]["work_time"] is None
    assert rows[509]["address"] is None and rows[509]["work_time"] is None
    assert await unload_snapshot(case) == before


@pytest.mark.parametrize("path", ["daily", "lazy", "background"])
async def test_c8_empty_reply_preserves_known_cache_and_documents(db_session, wb, path):
    case = await seed(db_session)
    await cache(db_session, case)
    await draft(db_session, case)
    before, documents = await saved(case), await unload_snapshot(case)
    wb.set("content-732", [])
    wb.set("supplies-732", [])
    if path == "daily":
        await daily(case)
    else:
        await initial(case, path)
    assert await saved(case) == before
    assert await unload_snapshot(case) == documents
    rows = await api(case)
    assert len(rows) == 1 and rows[0]["name"] == "Прежний склад"


async def test_c9a_official_fbw_http_format_round_trips_through_client_service_and_api(
    db_session, wb,
):
    case = await seed(db_session)
    # Official FBW 200 response sample, not /api/v3/offices (FBS).
    wb.set("content-732", [{"ID": 300461, "name": "Гомель 2",
        "address": "Гомель, Могилёвская улица 1/А", "workTime": "24/7",
        "isActive": False, "isTransitActive": True,
    }])
    assert settings.e2e_mock_wb_warehouses is False
    await daily(case)
    result = await api(case)
    assert len(result) == 1
    assert {key: value for key, value in result[0].items() if key != "id"} == {
        "wb_warehouse_id": 300461, "name": "Гомель 2",
        "address": "Гомель, Могилёвская улица 1/А", "work_time": "24/7",
        "is_active": False, "is_transit_active": True,
    }
    assert len(wb.calls) == 1
