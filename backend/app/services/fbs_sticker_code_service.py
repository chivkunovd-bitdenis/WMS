"""Human-readable WB FBS sticker code extraction."""

from __future__ import annotations

from typing import Any


def _clean_part(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def sticker_code_from_wb_row(row: dict[str, Any]) -> str | None:
    """Return the cabinet-visible sticker number, not the scanner barcode.

    WB sticker responses carry a technical ``barcode`` and the operator-facing
    sticker number split into ``partA``/``partB``. Pick lists need the latter:
    e.g. ``5667260 6304``.
    """
    part_a = _clean_part(row.get("partA") or row.get("part_a"))
    part_b = _clean_part(row.get("partB") or row.get("part_b"))
    if part_a and part_b:
        return f"{part_a} {part_b}"
    return None
