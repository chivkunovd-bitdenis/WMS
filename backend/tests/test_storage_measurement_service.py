from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

from app.models.inventory_movement import InventoryMovement
from app.models.product_dimension_event import ProductDimensionEvent
from app.services.storage_measurement_service import (
    MOSCOW,
    _stock_segments,
    _volume_segments,
    month_bounds,
    previous_month,
)


def _movement(**values: object) -> InventoryMovement:
    return cast(InventoryMovement, SimpleNamespace(**values))


def _dimension_event(**values: object) -> ProductDimensionEvent:
    return cast(ProductDimensionEvent, SimpleNamespace(**values))


def test_previous_month_defaults_to_completed_calendar_month() -> None:
    assert previous_month(date(2026, 8, 22)) == (date(2026, 7, 1), date(2026, 7, 31))


def test_month_bounds_rejects_invalid_month() -> None:
    try:
        month_bounds(2026, 13)
    except ValueError as exc:
        assert str(exc) == "invalid_month"
    else:
        raise AssertionError("invalid month must fail")


def test_stock_segments_keep_fractional_day_boundaries() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    end = datetime(2026, 7, 3, tzinfo=MOSCOW)
    movements = [
        _movement(created_at=datetime(2026, 7, 1, 12, tzinfo=MOSCOW), quantity_delta=2),
        _movement(created_at=datetime(2026, 7, 2, 12, tzinfo=MOSCOW), quantity_delta=-1),
    ]
    segments = _stock_segments(movements, start, end)
    assert segments == [
        (start, datetime(2026, 7, 1, 12, tzinfo=MOSCOW), 0),
        (datetime(2026, 7, 1, 12, tzinfo=MOSCOW), datetime(2026, 7, 2, 12, tzinfo=MOSCOW), 2),
        (datetime(2026, 7, 2, 12, tzinfo=MOSCOW), end, 1),
    ]


def test_volume_segments_split_continuous_stock_at_dimension_change() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    change_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=2)]
    old = _dimension_event(
        observed_at=start,
        volume_liters=Decimal("1"),
        source="wb",
        applied=False,
        fingerprint="old-wb",
    )
    new = _dimension_event(
        observed_at=change_at,
        volume_liters=Decimal("3"),
        source="wb",
        applied=True,
        fingerprint="new-wb",
    )

    segments = _volume_segments(
        movements, [old, new], start, end, legacy_volume_liters=None
    )

    assert [(left, right, held, volume) for left, right, held, volume, _ in segments] == [
        (start, change_at, 2, Decimal("1")),
        (change_at, end, 2, Decimal("3")),
    ]


def test_volume_segments_do_not_apply_later_measurement_to_earlier_stock() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    measured_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=1)]
    event = _dimension_event(
        observed_at=measured_at,
        volume_liters=Decimal("2"),
        source="manual",
        applied=True,
        fingerprint="manual-measurement",
    )

    segments = _volume_segments(
        movements, [event], start, end, legacy_volume_liters=Decimal("9")
    )

    assert [(held, volume) for _, _, held, volume, _ in segments] == [
        (1, None),
        (1, Decimal("2")),
    ]


def test_wb_observation_after_manual_measurement_does_not_change_storage_volume() -> None:
    start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    wb_observed_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=start, quantity_delta=1)]
    manual = _dimension_event(
        observed_at=start,
        volume_liters=Decimal("1"),
        source="manual",
        applied=True,
        fingerprint="manual-measurement",
    )
    wb_observation = _dimension_event(
        observed_at=wb_observed_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=False,
        fingerprint="wb-observation",
    )

    segments = _volume_segments(
        movements,
        [manual, wb_observation],
        start,
        end,
        legacy_volume_liters=None,
    )

    assert [(left, right, volume) for left, right, _, volume, _ in segments] == [
        (start, end, Decimal("1")),
    ]


def test_wb_restore_changes_open_timeline_without_recalculating_closed_period() -> None:
    closed_start = datetime(2026, 7, 1, tzinfo=MOSCOW)
    closed_end = datetime(2026, 8, 1, tzinfo=MOSCOW)
    wb_observed_at = datetime(2026, 7, 20, tzinfo=MOSCOW)
    restored_at = datetime(2026, 8, 5, tzinfo=MOSCOW)
    open_end = datetime(2026, 9, 1, tzinfo=MOSCOW)
    movements = [_movement(created_at=closed_start, quantity_delta=1)]
    manual = _dimension_event(
        observed_at=closed_start,
        volume_liters=Decimal("1"),
        source="manual",
        applied=False,
        fingerprint="manual-measurement",
    )
    wb_observation = _dimension_event(
        observed_at=wb_observed_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=False,
        fingerprint="wb-observation",
    )
    wb_restore = _dimension_event(
        observed_at=restored_at,
        volume_liters=Decimal("6"),
        source="wb",
        applied=True,
        fingerprint="wb-observation:restore-event",
    )

    closed_segments = _volume_segments(
        movements,
        [manual, wb_observation, wb_restore],
        closed_start,
        closed_end,
        legacy_volume_liters=None,
    )
    open_segments = _volume_segments(
        movements,
        [manual, wb_observation, wb_restore],
        closed_start,
        open_end,
        legacy_volume_liters=None,
    )

    assert [(left, right, volume) for left, right, _, volume, _ in closed_segments] == [
        (closed_start, closed_end, Decimal("1")),
    ]
    assert [(left, right, volume) for left, right, _, volume, _ in open_segments] == [
        (closed_start, restored_at, Decimal("1")),
        (restored_at, open_end, Decimal("6")),
    ]
