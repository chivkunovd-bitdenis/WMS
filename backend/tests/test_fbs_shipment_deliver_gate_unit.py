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
    PackingDistribution,
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


def _ready_distribution(*orders: SimpleNamespace) -> PackingDistribution:
    box_id = uuid.uuid4()
    return PackingDistribution(
        box_ids=(box_id,),
        assignments=tuple((order.id, box_id) for order in orders),
    )


def _missing_distribution() -> PackingDistribution:
    return PackingDistribution(box_ids=(), assignments=())


def test_deliver_blocked_for_in_supply() -> None:
    order = _mock_order(FBS_ORDER_STATUS_IN_SUPPLY)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=_ready_distribution(order),
    )
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.code == "packaging_required"


def test_deliver_blocked_for_assembling() -> None:
    order = _mock_order(FBS_ORDER_STATUS_ASSEMBLING)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=_ready_distribution(order),
    )
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.code == "packaging_required"


def test_deliver_ok_when_packed() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=_ready_distribution(order),
    )
    _validate_checks_pass(checks)
    assert all(check.ok for check in checks if check.code in {"supply_packed", "order_packed"})


def test_cancelled_order_check_not_ok() -> None:
    order = _mock_order(FBS_ORDER_STATUS_CANCELLED)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=_ready_distribution(order),
    )
    cancelled = [check for check in checks if check.code == "order_cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].ok is False


def test_warehouse_route_has_no_cargo_checks() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    checks = _build_delivery_checks(
        _mock_supply(delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC),
        [order],
        cargo_qr_ready=False,
        distribution=_ready_distribution(order),
    )
    codes = {check.code for check in checks}
    assert "cargo_places_required" not in codes
    assert "cargo_place_qr_not_ready" not in codes


def test_deliver_blocked_without_local_packing_boxes() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=_missing_distribution(),
    )
    failed_codes = {check.code for check in checks if not check.ok}
    assert failed_codes == {"packing_boxes_required", "orders_not_distributed"}


def test_deliver_blocked_when_packed_order_is_not_distributed() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=True,
        distribution=PackingDistribution(box_ids=(uuid.uuid4(),), assignments=()),
    )
    failed = [check for check in checks if not check.ok]
    assert [(check.code, check.order_id) for check in failed] == [
        ("orders_not_distributed", order.id)
    ]
