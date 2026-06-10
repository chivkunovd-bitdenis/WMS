"""Parse Wildberries ``content/v2/get/cards/list`` card JSON for UI (photos, SKUs, subject)."""

from __future__ import annotations

from typing import Any

_WB_COLOR_CHAR_ID = 14177449


def subject_name_from_card(card: dict[str, Any]) -> str | None:
    for key in ("subjectName", "subject_name"):
        raw = card.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def collect_skus_from_card(card: dict[str, Any]) -> list[str]:
    """WB puts barcodes (ШК) under ``sizes[].skus`` (list of strings)."""
    out: list[str] = []
    sizes = card.get("sizes")
    if not isinstance(sizes, list):
        return out
    for sz in sizes:
        if not isinstance(sz, dict):
            continue
        skus = sz.get("skus")
        if not isinstance(skus, list):
            continue
        for s in skus:
            if isinstance(s, str) and (t := s.strip()):
                out.append(t)
    return out


def primary_sku_display(skus: list[str]) -> str | None:
    return skus[0] if skus else None


def _characteristic_value_to_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            part = _characteristic_value_to_str(item)
            if part:
                parts.append(part)
        return ", ".join(parts) if parts else None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def color_from_card(card: dict[str, Any]) -> str | None:
    """Color from card ``characteristics`` (name «Цвет» or known WB id)."""
    chars = card.get("characteristics")
    if not isinstance(chars, list):
        return None
    fallback: str | None = None
    for ch in chars:
        if not isinstance(ch, dict):
            continue
        raw_val = _characteristic_value_to_str(ch.get("value"))
        if not raw_val:
            continue
        name = ch.get("name")
        if isinstance(name, str) and name.strip().casefold() == "цвет":
            return raw_val
        if ch.get("id") == _WB_COLOR_CHAR_ID:
            fallback = raw_val
    return fallback


def _size_label_from_entry(entry: dict[str, Any]) -> str | None:
    tech = entry.get("techSize")
    if isinstance(tech, str) and tech.strip():
        return tech.strip()
    wb_size = entry.get("wbSize")
    if isinstance(wb_size, str) and wb_size.strip():
        return wb_size.strip()
    return None


def size_from_card_for_barcode(card: dict[str, Any], barcode: str | None) -> str | None:
    """Size for the SKU row matching ``barcode`` (``techSize`` / ``wbSize``)."""
    sizes = card.get("sizes")
    if not isinstance(sizes, list) or not sizes:
        return None
    target = barcode.strip() if isinstance(barcode, str) and barcode.strip() else None
    if target:
        for sz in sizes:
            if not isinstance(sz, dict):
                continue
            skus = sz.get("skus")
            if not isinstance(skus, list):
                continue
            if any(isinstance(s, str) and s.strip() == target for s in skus):
                label = _size_label_from_entry(sz)
                if label:
                    return label
    if len(sizes) == 1 and isinstance(sizes[0], dict):
        return _size_label_from_entry(sizes[0])
    return None


def first_photo_url_from_card(card: dict[str, Any]) -> str | None:
    """First image URL from ``photos[0]`` (WB returns several size keys)."""
    photos = card.get("photos")
    if not isinstance(photos, list) or not photos:
        return None
    ph0 = photos[0]
    if not isinstance(ph0, dict):
        return None
    for key in ("big", "square", "c516x688", "hq", "tm"):
        u = ph0.get(key)
        if isinstance(u, str) and u.strip():
            return u.strip()
    return None
