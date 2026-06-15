"""Parse Wildberries ``content/v2/get/cards/list`` card JSON for UI (photos, SKUs, subject)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_WB_COLOR_CHAR_ID = 14177449
_COMPOSITION_CHAR_NAMES = frozenset(
    {
        "состав",
        "состав ткани",
        "состав материала",
        "материал",
    }
)


def brand_from_card(card: dict[str, Any]) -> str | None:
    raw = card.get("brand")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def subject_name_from_card(card: dict[str, Any]) -> str | None:
    for key in ("subjectName", "subject_name"):
        raw = card.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


@dataclass(frozen=True)
class WbSizeVariant:
    chrt_id: int | None
    size_label: str | None
    barcode: str


def _parse_chrt_id(entry: dict[str, Any]) -> int | None:
    raw = entry.get("chrtID") if "chrtID" in entry else entry.get("chrtId")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def iter_size_variants_from_card(card: dict[str, Any]) -> list[WbSizeVariant]:
    """One WMS product row per barcode in ``sizes[].skus``."""
    out: list[WbSizeVariant] = []
    sizes = card.get("sizes")
    if isinstance(sizes, list) and sizes:
        for sz in sizes:
            if not isinstance(sz, dict):
                continue
            label = _size_label_from_entry(sz)
            chrt = _parse_chrt_id(sz)
            skus = sz.get("skus")
            if not isinstance(skus, list):
                continue
            for s in skus:
                if isinstance(s, str) and (t := s.strip()):
                    out.append(WbSizeVariant(chrt_id=chrt, size_label=label, barcode=t))
    if out:
        return out
    for barcode in collect_skus_from_card(card):
        out.append(WbSizeVariant(chrt_id=None, size_label=None, barcode=barcode))
    return out


def sku_code_for_wb_variant(
    vendor: str | None,
    nm: int | None,
    variant: WbSizeVariant,
    *,
    multi_variant: bool,
) -> str:
    base = (vendor or (str(nm) if nm is not None else "") or variant.barcode).strip()
    if not multi_variant:
        return base[:128]
    if variant.size_label:
        suffix = variant.size_label.replace("/", "-").strip()
        if suffix:
            return f"{base}/{suffix}"[:128]
    if variant.chrt_id is not None:
        return f"{base}/chrt{variant.chrt_id}"[:128]
    return f"{base}/{variant.barcode[-8:]}"[:128]


def product_display_name(base_title: str, variant: WbSizeVariant, *, multi_variant: bool) -> str:
    title = base_title.strip() or "WB товар"
    if not multi_variant or not variant.size_label:
        return title[:255]
    return f"{title} {variant.size_label}"[:255]


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
    return _characteristic_from_card(
        card,
        names=frozenset({"цвет"}),
        char_id=_WB_COLOR_CHAR_ID,
    )


def composition_from_card(card: dict[str, Any]) -> str | None:
    """Material composition from card ``characteristics`` (name «Состав» etc.)."""
    return _characteristic_from_card(card, names=_COMPOSITION_CHAR_NAMES)


def _characteristic_from_card(
    card: dict[str, Any],
    *,
    names: frozenset[str],
    char_id: int | None = None,
) -> str | None:
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
        if isinstance(name, str) and name.strip().casefold() in names:
            return raw_val
        if char_id is not None and ch.get("id") == char_id:
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
