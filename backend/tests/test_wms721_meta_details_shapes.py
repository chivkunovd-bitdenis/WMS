"""WMS-721: the worklist reads meta_details_json whatever shape is stored.

The Ozon stage snapshot lives in a dict. A list of key/decision entries, the shape
WMS-477 seeds for WB verdicts, carries no stage snapshot, so the worklist must
report the stage as absent instead of failing on `.get`.
"""

import pytest

from app.services import fbs_worklist_service as worklist
from tests.test_wms662_observed_handoff import seed


# An Ozon order holding a list also reaches _delivery_route, which reads the same
# field without a type check (etalon code, not changed by WMS-721). That case is
# deliberately not part of this test; it is reported separately.
@pytest.mark.parametrize(
    "marketplace,stored,expected",
    [
        ("wb", [{"key": "sgtin", "decision": "pending"}], None),
        ("wb", {"ozon_confirmed_stage": "delivery"}, "delivery"),
        ("ozon", {"ozon_confirmed_stage": "delivery"}, "delivery"),
    ],
    ids=["wb-list-entries", "wb-dict-stage", "ozon-dict-stage"],
)
async def test_worklist_stage_reads_any_meta_details_shape(
    db_session, marketplace, stored, expected,
):
    case = await seed(db_session, marketplace)
    order = case.orders[0]
    order.meta_details_json = stored
    await db_session.flush()

    [item] = await worklist.build_worklist_items(db_session, case.tenant.id, [order])

    assert item["ozon_confirmed_stage"] == expected
