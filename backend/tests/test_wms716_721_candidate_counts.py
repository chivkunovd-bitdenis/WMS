"""WMS-716 x WMS-721 (stage candidate): tab counts follow the derived Ozon supply tab.

The Ozon supply tab follows its postings (WMS-721), not the stored status. The order
counts on the tabs (WMS-716) must be taken from the same selection as the list rows.
"""
from __future__ import annotations

import pytest

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
