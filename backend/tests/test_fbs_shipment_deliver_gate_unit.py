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
from app.models.fbs_supply import (
    FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FBS_SUPPLY_STATUS_PACKED,
)
from app.services.fbs_shipment_service import (
    CHECK_BLOCKER,
    WB_ALLOWED_BLOCKER_CODES,
    FbsShipmentError,
    _build_delivery_checks,
    _checks_allow_delivery,
    _validate_checks_pass,
)
from app.services.fbs_supply_composition_service import SupplyCompositionDiscrepancy


def _mock_supply(
    *,
    marketplace: str = "wb",
    delivery_type: str = FBS_DELIVERY_TYPE_WAREHOUSE_SC,
    trbxes: list | None = None,
    honest_sign_skipped_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        marketplace=marketplace,
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
        sticker_status="ready",
        sticker_file="fbs/orders/sticker.png",
        product=None,
        markings=[],
    )


def test_deliver_allows_optional_pick_pack_for_in_supply() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_IN_SUPPLY)],
        cargo_qr_ready=True,
    )
    _validate_checks_pass(checks)
    assert all(check.code != "packaging_required" for check in checks)


def test_deliver_allows_optional_pick_pack_for_assembling() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_ASSEMBLING)],
        cargo_qr_ready=True,
    )
    _validate_checks_pass(checks)
    assert all(check.code != "packaging_required" for check in checks)


def test_deliver_ok_when_packed() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED)],
        cargo_qr_ready=True,
    )
    _validate_checks_pass(checks)
    assert all(check.ok for check in checks if check.code in {"supply_packed", "order_packed"})


def test_missing_order_sticker_warns_but_never_blocks() -> None:
    """Ненапечатанный стикер — предупреждение, а не запрет.

    Владелец 01.09.2026: «не захотели — не проклеили, идите в пизду». Стикер
    можно напечатать и после передачи, поэтому склад из-за него не стоит.
    """
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    order.sticker_status = "error"
    order.sticker_file = None
    checks = _build_delivery_checks(_mock_supply(), [order], cargo_qr_ready=True)

    warned = [check for check in checks if check.code == "order_sticker_not_ready"]
    assert len(warned) == 1
    assert warned[0].ok is False
    assert warned[0].severity == "warning"
    assert _checks_allow_delivery(checks) is True
    _validate_checks_pass(checks)


def test_non_wb_delivery_does_not_require_wb_order_sticker() -> None:
    order = _mock_order(FBS_ORDER_STATUS_PACKED)
    order.sticker_status = "not_requested"
    order.sticker_file = None
    checks = _build_delivery_checks(
        _mock_supply(marketplace="ozon"),
        [order],
        cargo_qr_ready=True,
        boxes_required=False,
    )

    assert all(check.code != "order_sticker_not_ready" for check in checks)
    _validate_checks_pass(checks)


def test_terminal_order_check_not_ok() -> None:
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_CANCELLED)],
        cargo_qr_ready=True,
    )
    terminal = [check for check in checks if check.code == "order_terminal"]
    assert len(terminal) == 1
    assert terminal[0].ok is False


def test_terminal_wb_composition_order_is_visible_but_does_not_block() -> None:
    order_id = uuid.uuid4()
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED)],
        cargo_qr_ready=True,
        discrepancies=(
            SupplyCompositionDiscrepancy(
                code="terminal_order",
                wb_order_id=5635876649,
                local_order_id=order_id,
                detail=FBS_ORDER_STATUS_CANCELLED,
            ),
        ),
    )

    advisory = [check for check in checks if check.code == "wb_terminal_order_ignored"]
    assert len(advisory) == 1
    assert advisory[0].ok is False
    assert advisory[0].order_id == order_id
    assert "исключён из списания" in advisory[0].message
    assert _checks_allow_delivery(checks) is True
    _validate_checks_pass(checks)


def test_warehouse_route_has_no_cargo_checks() -> None:
    checks = _build_delivery_checks(
        _mock_supply(delivery_type=FBS_DELIVERY_TYPE_WAREHOUSE_SC),
        [_mock_order(FBS_ORDER_STATUS_PACKED)],
        cargo_qr_ready=False,
    )
    codes = {check.code for check in checks}
    assert "cargo_places_required" not in codes
    assert "cargo_place_qr_not_ready" not in codes


def test_boxes_and_distribution_are_warnings_not_gates() -> None:
    """Ни отсутствие коробов, ни нераспределённый заказ не останавливают склад.

    Именно эта пара кодов гасила кнопку у оператора 01.09.2026, хотя короба
    физически стояли, а раскладывать по ним товар склад никогда и не начинал.
    """
    order_id = uuid.uuid4()
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order(FBS_ORDER_STATUS_PACKED, order_id=order_id)],
        cargo_qr_ready=True,
        has_physical_boxes=False,
        unassigned_packed_order_ids=frozenset({order_id}),
    )
    warned = {check.code: check for check in checks if not check.ok}
    assert warned["physical_boxes_required"].order_id is None
    assert warned["physical_boxes_required"].severity == "warning"
    assert warned["packed_order_unassigned"].order_id == order_id
    assert warned["packed_order_unassigned"].severity == "warning"
    assert _checks_allow_delivery(checks) is True
    _validate_checks_pass(checks)


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


def test_marking_required_is_a_warning_and_never_blocks() -> None:
    """Отсутствие Честного знака показывается, но передачу не запрещает."""
    checks = _build_delivery_checks(
        _mock_supply(),
        [_mock_order_needing_honest_sign()],
        cargo_qr_ready=True,
    )
    marking = next(check for check in checks if check.code == "marking_required")
    assert marking.ok is False
    assert marking.severity == "warning"
    assert _checks_allow_delivery(checks) is True
    _validate_checks_pass(checks)


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


# ---------------------------------------------------------------------------
# ⛔ Бетон. Эти два теста существуют, чтобы внутренние блокировки WB больше
# никогда не вернулись — ни правкой напрямую, ни новой проверкой под новым
# именем. Если тест упал, значит кто-то снова запирает оператора; правильный
# ответ — не чинить тест, а вернуть проверке уровень предупреждения.
# ---------------------------------------------------------------------------


def test_wb_delivery_blocker_codes_are_frozen() -> None:
    """У Wildberries останавливать передачу вправе ровно две проверки."""
    assert frozenset({"supply_bad_status", "supply_empty"}) == WB_ALLOWED_BLOCKER_CODES


def test_wb_supply_with_nothing_prepared_is_still_deliverable() -> None:
    """Сценарий владельца целиком: ни стикеров, ни ЧЗ, ни коробов, ни раскладки.

    Такая поставка обязана уехать. Оператор увидит список предупреждений и
    сможет допечатать всё после передачи.
    """
    order_id = uuid.uuid4()
    order = _mock_order(FBS_ORDER_STATUS_IN_SUPPLY, order_id=order_id)
    order.sticker_status = "error"
    order.sticker_file = None
    order.product = SimpleNamespace(requires_honest_sign=True)

    checks = _build_delivery_checks(
        _mock_supply(),
        [order],
        cargo_qr_ready=False,
        has_physical_boxes=False,
        unassigned_packed_order_ids=frozenset({order_id}),
    )

    blockers = [check.code for check in checks if check.severity == CHECK_BLOCKER]
    assert blockers == []
    assert _checks_allow_delivery(checks) is True
    _validate_checks_pass(checks)

    warned = {check.code for check in checks if check.severity == "warning"}
    assert {"order_sticker_not_ready", "marking_required", "physical_boxes_required"} <= warned


def test_already_delivered_supply_still_refuses_second_handoff() -> None:
    """Единственное, что владелец просил оставить запретом, — повторная передача."""
    supply = _mock_supply()
    supply.status = FBS_SUPPLY_STATUS_IN_DELIVERY
    checks = _build_delivery_checks(
        supply, [_mock_order(FBS_ORDER_STATUS_PACKED)], cargo_qr_ready=True
    )

    blocker = next(check for check in checks if check.severity == CHECK_BLOCKER)
    assert blocker.code == "supply_bad_status"
    assert _checks_allow_delivery(checks) is False
    with pytest.raises(FbsShipmentError, match="supply_bad_status"):
        _validate_checks_pass(checks)


def test_empty_supply_still_refuses_handoff() -> None:
    checks = _build_delivery_checks(_mock_supply(), [], cargo_qr_ready=True)
    blockers = [check.code for check in checks if check.severity == CHECK_BLOCKER]
    assert blockers == ["supply_empty"]
    assert _checks_allow_delivery(checks) is False
