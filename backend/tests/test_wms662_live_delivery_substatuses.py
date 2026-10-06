"""WMS-662 classifier regression from saved real Ozon reads, no DB or network.

Source: WMS-675 live-proof commit 5b5da992a6cd766eb250ab83f4575fc8b11cdf22.
These two delivering substatuses mean the posting is already in delivery.
The original WMS-662 negative matrix remains unchanged in its contract file.
"""

import json
from pathlib import Path

import pytest

from app.services.fbs_observed_handoff_service import ozon_proves_handoff


LIVE_PROOF = (
    Path(__file__).parents[2]
    / "docs/reviews/wms675-evidence-20261006/live-ozon-run-20261006-attempt1"
)


@pytest.mark.parametrize(
    ("filename", "substatus"),
    [
        ("posting-0113371235-0054-3.json", "posting_in_pickup_point"),
        ("posting-83893932-0680-2.json", "posting_on_way_to_city"),
    ],
)
def test_live_delivering_substatus_proves_handoff(filename: str, substatus: str) -> None:
    saved = json.loads((LIVE_PROOF / filename).read_text())
    assert saved["http_status"] == 200
    assert saved["endpoint"] == "/v3/posting/fbs/get"
    card = saved["card"]
    assert card["status"] == "delivering"
    assert card["substatus"] == substatus
    assert ozon_proves_handoff(card) is True


@pytest.mark.parametrize(
    ("status", "substatus"),
    [
        ("cancelled", None),
        ("cancel", "posting_in_pickup_point"),
        ("delivering", "cancelled"),
        ("awaiting_packaging", None),
        ("awaiting_packaging", "posting_in_pickup_point"),
        ("awaiting_deliver", "posting_transferring_to_delivery"),
        ("unknown", "posting_on_way_to_city"),
        ("delivering", "unrecognized_substatus"),
        (None, None),
    ],
)
def test_delivery_substatuses_do_not_accept_cancelled_pending_or_unknown(
    status: str | None, substatus: str | None
) -> None:
    assert ozon_proves_handoff({"status": status, "substatus": substatus}) is False


def test_existing_received_delivery_stays_positive() -> None:
    assert ozon_proves_handoff({"status": "delivered", "substatus": "posting_received"}) is True
