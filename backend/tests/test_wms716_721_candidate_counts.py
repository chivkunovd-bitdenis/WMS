"""WMS-716 x WMS-721 (stage candidate): tab counts follow the derived Ozon supply tab.

The Ozon supply tab follows its postings (WMS-721), not the stored status. The order
counts on the tabs (WMS-716) must be taken from the same selection as the list rows.
"""
from __future__ import annotations

import pytest
from sqlalchemy import event

from app.db.session import SessionLocal
from app.services import fbs_supply_service as supplies
from app.services.fbs_counts_service import fetch_fbs_counts
from tests.test_wms662_observed_handoff import seed
from tests.test_wms721_ozon_status_tabs import arrange_stage

pytestmark = pytest.mark.asyncio


async def test_ozon_tab_counts_match_derived_supply_rows(db_session):
    case = await seed(db_session, "ozon", quantities=(1, 1), count=1)
    # Stored status says "assembling"; the postings say "delivering".
    await arrange_stage(db_session, case, handed=True, status="in_delivery")
    case.supply.status = "assembling"
    await db_session.commit()
    async with SessionLocal() as reader:
        rows = {}
        for group in ("active", "delivery", "done"):
            page = await supplies.list_supply_worklist(
                reader, case.tenant.id, status_group=group, marketplace="ozon",
            )
            rows[group] = sum(item["orders_count"] for item in page["items"])
        counts = await fetch_fbs_counts(reader, case.tenant.id, marketplace="ozon")
        await reader.commit()
    assert rows["delivery"] == len(case.orders) and rows["active"] == 0
    assert counts["tabs"]["delivery"] == rows["delivery"]
    assert counts["tabs"]["active"] == rows["active"]


async def test_ozon_candidate_selects_are_bounded_for_all_derived_groups(db_session):
    case = await seed(db_session, "ozon", quantities=(1,), count=1)
    case.supply.status = "done"
    case.orders[0].status = "done"
    case.orders[0].wb_status = "done"
    await db_session.commit()
    # More than the worklist's 100-row page size makes repeated full-history
    # sweeps visible in the SELECT count. Most supplies intentionally have no
    # orders; a stored done status still keeps them in the Ozon candidate set.
    for _ in range(100):
        db_session.add(
            supplies.FbsSupply(
                tenant_id=case.tenant.id,
                seller_id=case.seller.id,
                warehouse_id=case.warehouse.id,
                marketplace="ozon",
                source="wms",
                name="Historical Ozon supply",
                status="done",
                delivery_type="warehouse_sc",
            )
        )
    await db_session.commit()

    statements: list[str] = []
    engine = db_session.bind
    assert engine is not None

    def capture_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture_selects)
    try:
        counts = await fetch_fbs_counts(
            db_session, case.tenant.id, marketplace="ozon", status_group="done",
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_selects)

    assert counts["tabs"] == {"new": 0, "active": 0, "delivery": 0}
    assert counts["sellers"][str(case.seller.id)] == 1
    # Includes seller lookup, order group counts, supply membership, linked
    # order aggregation, and eager loads. The bound leaves room for these fixed
    # queries while rejecting one full candidate sweep per derived tab.
    assert len(statements) <= 16, f"count request issued {len(statements)} SELECTs"
