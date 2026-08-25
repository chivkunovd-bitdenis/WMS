"""Small value conversions shared by the Ozon return workflow."""

from datetime import UTC, date, datetime


def status_text(value: object) -> str:
    root = getattr(value, "root", value)
    return str(root or "GIVEOUT_STATUS_UNSPECIFIED")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None
