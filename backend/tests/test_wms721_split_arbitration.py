"""WMS-721: the first split observation must survive a subsequent dispute."""
import pytest

from tests.test_wms662_observed_handoff import saved, seed, split_cards, sync
from tests.test_wms721_ozon_status_tabs import accounting, assert_group
from tests.test_wms721_ozon_status_tabs import client_boundary as client_boundary


@pytest.mark.asyncio
async def test_split_first_delivery_then_arbitration_retains_delivery(db_session):
    case = await seed(db_session, "ozon", quantities=(3, 2))
    api, a, b = await split_cards(db_session, case)
    api.set(case, case.orders[0], "delivering", number=b, quantities=(1, 2))
    await sync(case, api)
    await assert_group(case, "delivery")
    before = accounting(await saved(case))
    for number, quantities in ((a, (2, 0)), (b, (1, 2))):
        api.set(case, case.orders[0], "arbitration", number=number, quantities=quantities)
    for _ in range(2):
        await sync(case, api)
        await assert_group(case, "delivery")
        assert accounting(await saved(case)) == before
