from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.services.storage_measurement_service import (
    MOSCOW,
    _stock_segments,
    _volume_segments,
    month_bounds,
    previous_month,
)


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
        SimpleNamespace(created_at=datetime(2026, 7, 1, 12, tzinfo=MOSCOW), quantity_delta=2),
        SimpleNamespace(created_at=datetime(2026, 7, 2, 12, tzinfo=MOSCOW), quantity_delta=-1),
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
    movements = [SimpleNamespace(created_at=start, quantity_delta=2)]
    old = SimpleNamespace(observed_at=start, volume_liters=Decimal("1"))
    new = SimpleNamespace(observed_at=change_at, volume_liters=Decimal("3"))

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
    movements = [SimpleNamespace(created_at=start, quantity_delta=1)]
    event = SimpleNamespace(observed_at=measured_at, volume_liters=Decimal("2"))

    segments = _volume_segments(
        movements, [event], start, end, legacy_volume_liters=Decimal("9")
    )

    assert [(held, volume) for _, _, held, volume, _ in segments] == [
        (1, None),
        (1, Decimal("2")),
    ]
