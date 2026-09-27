"""One server-only rollout policy for API, capability and background processing."""

from __future__ import annotations

import uuid

from app.core.settings import settings


def allowed_withdrawal_sellers() -> frozenset[uuid.UUID]:
    """Reject the entire list on any malformed entry, never partially enable it."""
    value = settings.withdrawal_seller_allowlist.strip()
    if not value:
        return frozenset()
    try:
        values = value.split(",")
        identifiers = [uuid.UUID(part.strip()) for part in values]
        # A UUID is a configuration identity, not a substring, label, or wildcard.
        if any(
            str(identifier) != part.strip().lower()
            for part, identifier in zip(values, identifiers, strict=True)
        ):
            return frozenset()
        return frozenset(identifiers)
    except ValueError:
        return frozenset()


def withdrawal_allowed(seller_id: uuid.UUID | None) -> bool:
    return seller_id is not None and seller_id in allowed_withdrawal_sellers()
