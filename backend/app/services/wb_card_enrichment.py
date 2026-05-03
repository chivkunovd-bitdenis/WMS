"""Parse Wildberries ``content/v2/get/cards/list`` card JSON for UI (photos, SKUs, subject)."""

from __future__ import annotations

from typing import Any


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
