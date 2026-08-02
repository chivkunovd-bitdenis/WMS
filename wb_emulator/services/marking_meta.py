"""In-memory order marking meta (KIZ/sgtin and related kinds) for emulator."""

from __future__ import annotations

from typing import Any

META_KINDS: frozenset[str] = frozenset({"sgtin", "uin", "imei", "gtin"})

_META_PLURAL_KEYS: dict[str, str] = {
    "sgtin": "sgtins",
    "uin": "uins",
    "imei": "imeis",
    "gtin": "gtins",
}

# (seller_key, order_id) -> {plural_key: [{value, checkStatus}, ...]}
_meta_store: dict[tuple[str, int], dict[str, list[dict[str, str]]]] = {}


def reset_marking_meta_store() -> None:
    """Clear all stored meta (tests only)."""
    _meta_store.clear()


def plural_key_for_kind(kind: str) -> str:
    key = _META_PLURAL_KEYS.get(kind)
    if key is None:
        raise ValueError(f"invalid_meta_kind:{kind}")
    return key


def check_status_for_value(value: str) -> str:
    """KIZ containing ERR → error; otherwise ok."""
    if "ERR" in value.upper():
        return "error"
    return "ok"


def upsert_meta(seller_key: str, order_id: int, kind: str, value: str) -> None:
    """Store marking identifier; derive checkStatus from value."""
    if kind not in META_KINDS:
        raise ValueError(f"invalid_meta_kind:{kind}")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError("empty_meta_value")

    plural = plural_key_for_kind(kind)
    bucket = _meta_store.setdefault((seller_key, order_id), {})
    entries = bucket.setdefault(plural, [])
    status = check_status_for_value(trimmed)
    for entry in entries:
        if entry.get("value") == trimmed:
            entry["checkStatus"] = status
            return
    entries.append({"value": trimmed, "checkStatus": status})


def get_meta(seller_key: str, order_id: int) -> dict[str, Any]:
    """Return WB-shaped GET /orders/{id}/meta payload."""
    stored = _meta_store.get((seller_key, order_id), {})
    return dict(stored)


def parse_put_values(kind: str, body: dict[str, Any]) -> list[str]:
    """Extract values from PUT body (plural array key per WB contract)."""
    plural = plural_key_for_kind(kind)
    raw = body.get(plural)
    if raw is None:
        raise ValueError(f"missing_key:{plural}")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                values.append(item.strip())
        return values
    raise ValueError(f"invalid_payload:{plural}")
