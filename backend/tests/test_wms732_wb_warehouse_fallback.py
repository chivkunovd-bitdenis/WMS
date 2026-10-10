"""WMS-732 C12-C14: known FBW cache fallback and explicit WB disablement.

Baseline 0da9f6dd9. HTTP fixtures represent disabled/recovered WB, not live proof.
Positive confirmed-source cases require the source-selection criterion from A6;
existing customer data and credentials must never be copied as a catalogue.
Baseline: 14 cases, 9 expected product failures and 5 preserved-behaviour passes.
Green negative-source cases reject fabricated rows under an empty/unavailable WB
reply; the unconfigured-recipient case rejects population without WB setup.
Mutations touch only wb_mp_warehouse_service.py and are restored byte-for-byte.
"""
from __future__ import annotations

import pytest

from app.services import wb_mp_warehouse_service as wh
from tests.test_wms732_wb_warehouses import (
    api,
    by_number,
    cache,
    daily,
    draft,
    initial,
    saved,
    seed,
    unload_snapshot,
    wire_row,
)
from tests.test_wms732_wb_warehouses import (
    wb as wb,
)

pytestmark = pytest.mark.asyncio
DISABLED = "This method is temporarily disabled. Link: https://dev.wildberries.ru/release-notes?id=570"


@pytest.mark.parametrize("path", ["daily", "lazy", "background"])
async def test_c13_no_confirmed_source_creates_no_warehouses_or_automatic_selection(
    db_session, wb, path,
):
    case = await seed(db_session)
    await draft(db_session, case, selected=None)
    before = await unload_snapshot(case)
    wb.set("content-732", DISABLED, 404)
    wb.set("supplies-732", DISABLED, 404)
    if path == "daily":
        await daily(case)
    else:
        await initial(case, path)
    assert await saved(case) == {}
    assert await unload_snapshot(case) == before
    assert await api(case) == []


@pytest.mark.parametrize("body", [DISABLED, {"title": "Not Found", "detail": DISABLED}])
async def test_c14_explicit_disabled_method_stops_entire_daily_key_search(db_session, wb, body):
    first = await seed(db_session, 1, (("first-732", "first-spare-732"),))
    second = await seed(db_session, 2, (("second-732", "second-spare-732"),))
    for token in ("first-732", "first-spare-732", "second-732", "second-spare-732"):
        wb.set(token, body, 404)
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert len(wb.calls) == 1, "explicit global method disablement must stop redundant key attempts"
    assert await saved(first) == {} and await saved(second) == {}
    # The unavailable-method result is scoped to one daily sweep, not forever.
    wb.calls.clear()
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert len(wb.calls) == 1, "the next day must make one fresh availability attempt"


async def test_c14_recovery_adds_new_wb_numbers_without_refreshing_historical_rows(db_session, wb):
    case = await seed(db_session)
    await cache(db_session, case)
    before = await saved(case)
    wb.set("content-732", DISABLED, 404)
    wb.set("supplies-732", DISABLED, 404)
    await daily(case)
    assert await saved(case) == before
    wb.calls.clear()
    wb.set("content-732", [wire_row(507, "Новое имя WB"), wire_row(512, "Новый после WB")])
    await daily(case)
    after = await saved(case)
    assert 512 in by_number(after)
    assert all(after.get(key) == row for key, row in before.items())
    assert wb.tokens == ["content-732"]


async def confirmed_source(session, monkeypatch, wb, number, rows, date):
    """Make provenance a scenario precondition via real successful FBW ingestion.

    The existing canonical table has only one product writer: the FBW loader.
    This fixture does not invent a source flag, source whitelist or new catalogue.
    Other-purpose warehouses are kept in their actual FBS/Ozon/WMS tables.
    """
    from datetime import datetime
    case = await seed(session, number, ((f"source-{number}-732", None),))
    wb.set(f"source-{number}-732", rows)
    class HistoricalClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return date.astimezone(tz) if tz else date.replace(tzinfo=None)
    with monkeypatch.context() as clock:
        clock.setattr(wh, "datetime", HistoricalClock)
        await daily(case)
    loaded = by_number(await saved(case))
    assert set(loaded) == {row["ID"] for row in rows}
    return case


def disable(wb, *cases):
    for case in cases:
        for pair in case.pairs:
            for token in pair or ():
                if token:
                    wb.set(token, DISABLED, 404)


async def source_and_receivers(session, monkeypatch, wb):
    from datetime import timedelta

    from tests.test_wms732_wb_warehouses import OLD_DATE
    source = await confirmed_source(session, monkeypatch, wb, 10,
                                    [wire_row(507), wire_row(509, "Новый известный FBW")],
                                    OLD_DATE)
    receivers = [await seed(session, number, ((f"receiver-{number}-732", None),))
                 for number in range(1, 5)]
    await cache(session, receivers[3], date=OLD_DATE - timedelta(days=2))
    for case in receivers:
        await draft(session, case, selected=None)
    disable(wb, source, *receivers)
    return source, receivers


async def assert_copy(source_rows, case, *, before=None):
    current = await saved(case)
    numbers = by_number(current)
    expected = by_number(source_rows)
    assert set(numbers) == set(expected), "missing FBW numbers must be filled from the known list"
    fields = ("name", "address", "work_time", "is_active", "is_transit_active", "fetched_at")
    for wid, original in expected.items():
        row = numbers[wid]
        if before and wid in by_number(before):
            assert row == by_number(before)[wid]
        else:
            assert {key: row[key] for key in fields} == {key: original[key] for key in fields}
        assert row["tenant_id"] == case.tenant.id
        assert row["id"] not in source_rows
    response = await api(case)
    assert {row["id"] for row in response} == {str(key) for key in current}
    allowed = {"id", "wb_warehouse_id", "name", "address", "work_time",
               "is_active", "is_transit_active"}
    assert all(set(row) == allowed for row in response), (
        "no donor tenant, seller or credentials in API"
    )


async def test_c12_daily_populates_three_empty_and_one_partial_cache_preserving_source(
    db_session, monkeypatch, wb,
):
    source, receivers = await source_and_receivers(db_session, monkeypatch, wb)
    source_before = await saved(source)
    receiver_before = [await saved(case) for case in receivers]
    drafts_before = [await unload_snapshot(case) for case in receivers]
    noncatalog_before = await noncatalog_snapshot()
    wb.calls.clear()
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    for case, old in zip(receivers, receiver_before, strict=True):
        await assert_copy(source_before, case, before=old)
    assert await saved(source) == source_before
    assert [await unload_snapshot(case) for case in receivers] == drafts_before
    assert await noncatalog_snapshot() == noncatalog_before
    first_result = [await saved(case) for case in receivers]
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert [await saved(case) for case in receivers] == first_result
    assert await saved(source) == source_before
    assert len(wb.calls) == 2, "each daily sweep must make one disabled-method attempt"


@pytest.mark.parametrize("path", ["lazy", "background"])
async def test_c12_initial_empty_caches_copy_fbw_dates_and_preserve_existing_caches(
    db_session, monkeypatch, wb, path,
):
    source, receivers = await source_and_receivers(db_session, monkeypatch, wb)
    source_before = await saved(source)
    old = await saved(receivers[3])
    drafts_before = [await unload_snapshot(case) for case in receivers]
    noncatalog_before = await noncatalog_snapshot()
    for case in receivers[:3]:
        await initial(case, path)
        await assert_copy(source_before, case)
        previous = await saved(case)
        await initial(case, path)
        assert await saved(case) == previous
    # Nonempty-cache reads/background initial-fill remain non-destructive.
    await initial(receivers[3], path)
    assert await saved(receivers[3]) == old
    assert await saved(source) == source_before
    assert [await unload_snapshot(case) for case in receivers] == drafts_before
    assert await noncatalog_snapshot() == noncatalog_before


async def test_c12_concurrent_daily_and_initial_fallback_copy_each_number_once(
    db_session, monkeypatch, wb,
):
    import asyncio

    from tests.test_wms732_wb_warehouses import OLD_DATE
    source = await confirmed_source(db_session, monkeypatch, wb, 10,
                                    [wire_row(507), wire_row(509)], OLD_DATE)
    receiver = await seed(db_session)
    disable(wb, source, receiver)
    before = await saved(source)
    arrivals = []
    entered, release = asyncio.Event(), asyncio.Event()
    async def barrier(request):
        arrivals.append(True)
        if len(arrivals) == 2:
            entered.set()
        await release.wait()
    wb.before_reply = barrier
    tasks = [asyncio.create_task(daily(receiver)),
             asyncio.create_task(initial(receiver, "lazy"))]
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        release.set()
        await asyncio.gather(*tasks)
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    wb.before_reply = None
    await assert_copy(before, receiver)
    assert await saved(source) == before


async def other_purpose_warehouses(session, case):
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    session.add_all([
        FbsWarehouseBinding(tenant_id=case.tenant.id, seller_id=case.sellers[0].id,
                            marketplace=marketplace, external_warehouse_id=str(number),
                            wb_warehouse_id=number, wms_warehouse_id=case.warehouse.id)
        for marketplace, number in (("wb", 9901), ("ozon", 1020005029603630))
    ])
    await session.commit()


async def test_c13_latest_fbw_source_wins_and_other_purpose_data_is_not_copied(
    db_session, monkeypatch, wb,
):
    from datetime import timedelta

    from tests.test_wms732_wb_warehouses import OLD_DATE
    older = await confirmed_source(db_session, monkeypatch, wb, 10,
                                   [wire_row(507, "Старый FBW", address="Старый адрес")],
                                   OLD_DATE - timedelta(days=2))
    latest = await confirmed_source(db_session, monkeypatch, wb, 11,
                                    [wire_row(507, "Последний FBW", address="Последний адрес")],
                                    OLD_DATE)
    await other_purpose_warehouses(db_session, latest)
    receiver = await seed(db_session)
    disable(wb, older, latest, receiver)
    before = {case.tenant.id: await saved(case) for case in (older, latest)}
    await daily(receiver)
    await assert_copy(before[latest.tenant.id], receiver)
    assert set(by_number(await saved(receiver))) == {507}
    assert {case.tenant.id: await saved(case) for case in (older, latest)} == before


async def test_c13_equal_source_dates_have_stable_results_for_distinct_receivers(
    db_session, monkeypatch, wb,
):
    from tests.test_wms732_wb_warehouses import OLD_DATE
    a = await confirmed_source(db_session, monkeypatch, wb, 10,
                              [wire_row(507, "Равная дата A")], OLD_DATE)
    b = await confirmed_source(db_session, monkeypatch, wb, 11,
                              [wire_row(507, "Равная дата B")], OLD_DATE)
    receivers = [await seed(db_session, i, ((f"tie-{i}-732", None),)) for i in (1, 2, 3)]
    disable(wb, a, b, *receivers)
    results = []
    for case in receivers:
        await daily(case)
        rows = by_number(await saved(case))
        assert set(rows) == {507}
        results.append(rows[507]["name"])
    assert len(set(results)) == 1 and results[0] in {"Равная дата A", "Равная дата B"}


async def test_c13_fbs_and_ozon_only_are_not_a_confirmed_fbw_source(db_session, wb):
    donor = await seed(db_session, 10, (("donor-732", None),))
    await other_purpose_warehouses(db_session, donor)
    receiver = await seed(db_session)
    disable(wb, donor, receiver)
    await daily(receiver)
    assert await api(receiver) == []
    assert await saved(receiver) == {}


async def noncatalog_snapshot():
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.billing import BillingLedgerEntry
    from app.models.fbs_order import FbsOrder, FbsOrderReservation
    from app.models.fbs_warehouse_binding import FbsWarehouseBinding
    from app.models.inventory_balance import InventoryBalance
    from app.models.inventory_movement import InventoryMovement
    from app.models.marketplace_unload import MarketplaceUnloadRequest
    from app.models.product import Product
    from app.models.seller import Seller
    from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.warehouse import Warehouse

    async with SessionLocal() as reader:
        result = {}
        for model in (Tenant, Seller, SellerWildberriesCredentials, User, Warehouse,
                      MarketplaceUnloadRequest, FbsWarehouseBinding, Product, FbsOrder,
                      FbsOrderReservation, InventoryBalance, InventoryMovement, BillingLedgerEntry):
            table = model.__table__
            rows = await reader.execute(select(table).order_by(*table.primary_key.columns))
            result[table.name] = [dict(row) for row in rows.mappings()]
        return result


async def test_c12_unconfigured_tenant_is_not_populated_or_given_donor_settings(
    db_session, monkeypatch, wb,
):
    from tests.test_wms732_wb_warehouses import OLD_DATE
    source = await confirmed_source(db_session, monkeypatch, wb, 10,
                                    [wire_row(507)], OLD_DATE)
    receiver = await seed(db_session, pairs=(None,))
    disable(wb, source)
    before = await noncatalog_snapshot()
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert await saved(receiver) == {}
    assert await api(receiver) == []
    assert await noncatalog_snapshot() == before
