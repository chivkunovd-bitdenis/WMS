"""Fast unit tests for FBS deliver gate — no DB/async fixtures."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_SUPPLY_STATUS_PACKED
from app.services.fbs_shipment_service import (
    FbsShipmentError,
    _build_delivery_checks,
    _validate_checks_pass,
)


def _mock_supply(
    *,
    delivery_type: str = FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    trbxes: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=delivery_type,
        trbxes=trbxes or [],
    )


def _mock_order(status: str, *, order_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id or uuid.uuid4(),
        status=status,
        wb_status="new",
        metadata_delivery_allowed=True,
        required_meta_json=[],
        product=None,
        markings=[],
    )


def test_deliver_blocked_for_in_supply() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_IN_SUPPLY)],
        cargo_qr_ready=True,
    )
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.code == "packaging_required"


def test_deliver_blocked_for_assembling() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_ASSEMBLING)],
        cargo_qr_ready=True,
    )
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.code == "packaging_required"


def test_deliver_ok_when_packed() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED)],
        cargo_qr_ready=True,
    )
    _validate_checks_pass(checks)
    assert all(check.ok for check in checks if check.code in {"supply_packed", "order_packed"})


def test_cancelled_order_check_not_ok() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_CANCELLED)],
        cargo_qr_ready=True,
    )
    cancelled = [check for check in checks if check.code == "order_cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].ok is False


def test_warehouse_route_has_no_cargo_checks() -> None:
    checks = _build_delivery_checks(
        _mock_supply(delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC),
        [_mock_order(FBS_ORDER_STATUS_PACKED)],
        cargo_qr_ready=False,
    )
    codes = {check.code for check in checks}
    assert "cargo_places_required" not in codes
    assert "cargo_place_qr_not_ready" not in codes
