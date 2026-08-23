"""Fast unit tests for FBS deliver gate — no DB/async fixtures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
    honest_sign_skipped_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=FBS_SUPPLY_STATUS_PACKED,
        delivery_type=delivery_type,
        trbxes=trbxes or [],
        # Поставка, по которой оператор нажал «Сдать без Честного знака», хранит здесь
        # время снятия требования; у обычной поставки поле пустое.
        honest_sign_skipped_at=honest_sign_skipped_at,
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


def test_deliver_requires_physical_boxes_and_packed_order_assignments() -> None:
    order_id = uuid.uuid4()
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED, order_id=order_id)],
        cargo_qr_ready=True,
        has_physical_boxes=False,
        unassigned_packed_order_ids=frozenset({order_id}),
    )
    failed = {check.code: check for check in checks if not check.ok}
    assert failed["physical_boxes_required"].order_id is None
    assert failed["packed_order_unassigned"].order_id == order_id


def test_deliver_allows_boxes_without_distribution() -> None:
    order_id = uuid.uuid4()
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED, order_id=order_id)],
        cargo_qr_ready=True,
        has_physical_boxes=True,
        without_distribution=True,
        unassigned_packed_order_ids=frozenset({order_id}),
    )
    _validate_checks_pass(checks)
    codes = {check.code for check in checks}
    assert "boxes_without_distribution" in codes
    assert "packed_order_unassigned" not in codes


def _mock_order_needing_honest_sign() -> SimpleNamespace:
    """Заказ на маркированный товар, по которому код так и не отсканировали."""
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    order.product = SimpleNamespace(requires_honest_sign=True)
    return order


def test_marking_required_blocks_delivery_by_default() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order_needing_honest_sign()],
        cargo_qr_ready=True,
    )
    assert any(check.code == "marking_required" and not check.ok for check in checks)


def test_skip_honest_sign_removes_our_marking_gate() -> None:
    """«Сдать без Честного знака» снимает требование, выставленное нами."""
    checks = _build_delivery_checks(
        _mock_supply(honest_sign_skipped_at=datetime.now(UTC)),
        [_mock_order_needing_honest_sign()],
        cargo_qr_ready=True,
    )
    assert not any(check.code == "marking_required" for check in checks)
    _validate_checks_pass(checks)


def test_preflight_exposes_real_wb_marking_status() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    order.required_meta_json = ["sgtin"]
    order.markings = [
        SimpleNamespace(
            kind="sgtin",
            value="0104601234567890",
            meta_status="accepted",
            meta_details_json={"decision": "filled", "reason": None},
            reason=None,
        )
    ]
    checks = _build_delivery_checks(_mock_supply(), [order], cargo_qr_ready=True)
    marking = next(check for check in checks if check.code == "marking_allowed")
    assert marking.ok is True
    assert marking.message == "WB: маркировка подтверждена."

    order.markings[0].meta_details_json = {
        "decision": "filled",
        "reason": "uinBadStatus",
    }
    checks = _build_delivery_checks(_mock_supply(), [order], cargo_qr_ready=True)
    marking = next(check for check in checks if check.code == "marking_not_allowed")
    assert marking.ok is False
    assert marking.message == "WB не принял маркировку: uinBadStatus"
