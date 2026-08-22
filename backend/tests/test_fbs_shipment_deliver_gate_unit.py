"""Fast unit tests for FBS deliver gate — no DB/async fixtures."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.fbs_order import (
    FBS_ORDER_STATUS_ASSEMBLING,
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_SUPPLY,
    FBS_ORDER_STATUS_PACKED,
)
from app.models.fbs_supply import FBS_DELIVERY_TYPE_WAREHOUSE_SC, FBS_SUPPLY_STATUS_PACKED
from app.services import fbs_marking_service as marking_svc
from app.services.fbs_shipment_service import (
    FbsShipmentError,
    _build_delivery_checks,
    _sync_supply_orders_from_wb,
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
        optional_meta_json=[],
        product=None,
        markings=[],
    )


def _mock_order_with_verdict(
    decision: str, *, reason: str | None = None, order_id: uuid.UUID | None = None
) -> SimpleNamespace:
    order = _mock_order(FBS_ORDER_STATUS_PACKED, order_id=order_id)
    if decision in {"optional", "notRequired"}:
        order.optional_meta_json = ["sgtin"]
    else:
        order.required_meta_json = ["sgtin"]
    order.markings = [
        SimpleNamespace(
            kind="sgtin",
            meta_status="accepted" if decision == "filled" else "unknown",
            reason=reason,
            meta_details_json={"decision": decision},
            value="0104601234567890",
        )
    ]
    return order


@pytest.mark.parametrize("decision", ["filled", "optional", "notRequired"])
def test_delivery_uses_wb_verdict_for_allowed_decisions(decision: str) -> None:
    checks = _build_delivery_checks(
        _mock_supply(), [_mock_order_with_verdict(decision)], cargo_qr_ready=True
    )
    _validate_checks_pass(checks)


def test_delivery_allows_order_without_wb_metadata_requirements() -> None:
    checks = _build_delivery_checks(
        _mock_supply(), [_mock_order(FBS_ORDER_STATUS_PACKED)], cargo_qr_ready=True
    )
    allowed = next(check for check in checks if check.code == "marking_allowed")
    assert allowed.ok is True
    _validate_checks_pass(checks)


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        ("filled", "Код не прошёл проверку"),
        ("pending", None),
        ("required", None),
        ("unknown", None),
    ],
)
def test_delivery_blocks_wb_verdict_and_attaches_order(
    decision: str, reason: str | None
) -> None:
    order_id = uuid.uuid4()
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order_with_verdict(decision, reason=reason, order_id=order_id)],
        cargo_qr_ready=True,
    )
    failed = next(check for check in checks if check.code == "marking_not_allowed")
    assert failed.ok is False
    assert failed.order_id == order_id
    assert str(order_id) in failed.message
    if reason:
        assert reason in failed.message
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.code == "marking_not_allowed"
    assert exc.value.message == failed.message
    assert exc.value.context == {
        "delivery_check": {
            "code": "marking_not_allowed",
            "message": failed.message,
            "order_id": str(order_id),
        }
    }
    assert exc.value.http_status == 400


@pytest.mark.asyncio
async def test_delivery_sync_error_invalidates_stale_filled_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-03-TC-006/012: a direct deliver fails closed after a fresh WB error."""
    tenant_id = uuid.uuid4()
    order = _mock_order_with_verdict("filled")
    order.tenant_id = tenant_id
    order.wb_order_id = 912345
    supply = _mock_supply()
    supply.seller_id = uuid.uuid4()
    supply.wb_supply_id = "WB-SUPPLY-1"
    session = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())

    async def load_orders(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        del args, kwargs
        return [order]

    async def fetch_statuses(*args: object, **kwargs: object) -> list[dict[str, object]]:
        del args, kwargs
        return []

    async def fail_marking_sync(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise marking_svc.FbsMarkingError("wb_transport_error")

    from app.services import fbs_shipment_service as shipment_svc

    monkeypatch.setattr(shipment_svc, "_load_supply_orders_read", load_orders)
    monkeypatch.setattr(shipment_svc, "fetch_marketplace_orders_status", fetch_statuses)
    monkeypatch.setattr(marking_svc, "sync_order_marking_statuses", fail_marking_sync)

    refreshed = await _sync_supply_orders_from_wb(
        session, tenant_id, supply, AsyncMock(), "marketplace-token"
    )

    assert refreshed == [order]
    assert order.metadata_delivery_allowed is False
    assert order.markings[0].meta_details_json["decision"] is None
    checks = _build_delivery_checks(supply, refreshed, cargo_qr_ready=True)
    failed = next(check for check in checks if check.code == "marking_not_allowed")
    assert failed.order_id == order.id
    assert failed.message == f"Нет ответа WB по заказу {order.id}."
    with pytest.raises(FbsShipmentError) as exc:
        _validate_checks_pass(checks)
    assert exc.value.context["delivery_check"]["order_id"] == str(order.id)


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
