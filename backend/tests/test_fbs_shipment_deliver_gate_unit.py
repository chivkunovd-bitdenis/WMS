"""Fast unit tests for FBS deliver gate — no DB/async fixtures."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
    FbsOrder,
)
from app.services.fbs_shipment_service import FbsShipmentError, _validate_orders_deliverable


def _mock_order(status: str) -> SimpleNamespace:
    return SimpleNamespace(status=status, product=None, markings=[])


def test_deliver_blocked_for_in_supply() -> None:
    with pytest.raises(FbsShipmentError) as exc:
        _validate_orders_deliverable([cast("FbsOrder", _mock_order(FBS_ORDER_STATUS_IN_SUPPLY))])
    assert exc.value.code == "packaging_required"


def test_deliver_blocked_for_assembling() -> None:
    with pytest.raises(FbsShipmentError) as exc:
        _validate_orders_deliverable([cast("FbsOrder", _mock_order(FBS_ORDER_STATUS_ASSEMBLING))])
    assert exc.value.code == "packaging_required"


def test_deliver_ok_when_packed() -> None:
    _validate_orders_deliverable([cast("FbsOrder", _mock_order(FBS_ORDER_STATUS_PACKED))])
