from datetime import date

from app.services.storage_measurement_service import month_bounds, previous_month


def test_previous_month_defaults_to_completed_calendar_month() -> None:
    assert previous_month(date(2026, 8, 22)) == (date(2026, 7, 1), date(2026, 7, 31))


def test_month_bounds_rejects_invalid_month() -> None:
    try:
        month_bounds(2026, 13)
    except ValueError as exc:
        assert str(exc) == "invalid_month"
    else:
        raise AssertionError("invalid month must fail")
