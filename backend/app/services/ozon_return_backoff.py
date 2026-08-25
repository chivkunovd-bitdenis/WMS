"""Process-local rate-limit guard dedicated to interactive Ozon returns."""

from app.services.marketplace_provider import MarketplaceBackoff, MarketplaceProviderError

_BACKOFF = MarketplaceBackoff()


def raise_if_blocked() -> None:
    remaining = _BACKOFF.remaining_seconds("ozon")
    if remaining <= 0:
        return
    raise MarketplaceProviderError(
        "ozon",
        429,
        {"retry_after_seconds": remaining},
        code="ozon_rate_limited",
    )


def record_rate_limit(error: MarketplaceProviderError) -> None:
    if error.status_code != 429:
        return
    retry_after = error.payload.get("retry_after_seconds", 60)
    delay = float(retry_after) if isinstance(retry_after, (int, float)) else 60.0
    _BACKOFF.record_rate_limit("ozon", retry_after_seconds=delay)
