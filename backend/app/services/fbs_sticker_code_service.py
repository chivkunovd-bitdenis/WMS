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


def sticker_barcode_from_wb_row(row: dict[str, Any]) -> str | None:
    """Технический код стикера — тот, что закодирован в QR и читается сканером.

    В ответе WB это поле ``barcode`` (например ``*DUIkWJJF``). Оператор его нигде
    не видит глазами, но на печатной этикетке им заполнены все семь кодов — и QR,
    и линейные штрихкоды. Без него скан стикера не сопоставить с заказом.
    """
    raw = row.get("barcode") or row.get("sticker_barcode")
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    return cleaned or None
