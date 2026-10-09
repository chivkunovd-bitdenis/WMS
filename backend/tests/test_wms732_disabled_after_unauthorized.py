"""WMS-732: a later global WB outage must also fill earlier eligible tenants."""
from datetime import timedelta

import pytest

from app.services import wb_mp_warehouse_service as wh
from tests.test_wms732_wb_warehouse_fallback import (
    assert_copy,
    noncatalog_snapshot,
    source_and_receivers,
)
from tests.test_wms732_wb_warehouses import OLD_DATE, cache, saved, seed
from tests.test_wms732_wb_warehouses import wb as wb


@pytest.mark.asyncio
@pytest.mark.parametrize("first_has_old_cache", [False, True])
async def test_late_disabled_method_fills_earlier_unauthorized_tenant(
    db_session, monkeypatch, wb, first_has_old_cache,
):
    source, receivers = await source_and_receivers(db_session, monkeypatch, wb)
    unconfigured = await seed(db_session, 0, pairs=(None,))
    first = receivers[0]
    if first_has_old_cache:
        await cache(db_session, first, date=OLD_DATE - timedelta(days=2))
    source_before = await saved(source)
    receivers_before = [await saved(case) for case in receivers]
    unrelated_before = await noncatalog_snapshot()
    first_token = first.pairs[0][0]
    disabled_token = receivers[1].pairs[0][0]
    wb.set(first_token, [], 401)
    wb.calls.clear()

    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()

    assert wb.tokens == [first_token, disabled_token], "no WB calls after explicit disablement"
    for case, before in zip(receivers, receivers_before, strict=True):
        await assert_copy(source_before, case, before=before)
    assert await saved(unconfigured) == {}
    assert await saved(source) == source_before
    assert await noncatalog_snapshot() == unrelated_before

    first_result = [await saved(case) for case in receivers]
    wb.calls.clear()
    await wh.run_daily_wb_mp_warehouses_sync_all_tenants()
    assert wb.tokens == [first_token, disabled_token], "a new sweep retries availability once"
    assert [await saved(case) for case in receivers] == first_result
    assert await saved(source) == source_before
