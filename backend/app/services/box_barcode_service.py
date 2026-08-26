"""Generate physical-box barcodes accepted by Wildberries packaging uploads."""

from __future__ import annotations

import re
import uuid

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_WB_BOX_BARCODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,30}$")
_ALLOWED_PREFIXES = frozenset({"WHB", "INB"})


def is_wb_compatible_box_barcode(value: str) -> bool:
    """Return whether *value* satisfies WB's self-generated box-code rules."""
    return bool(
        _WB_BOX_BARCODE_PATTERN.fullmatch(value)
        and not value.upper().startswith("WB_")
    )


def generate_box_barcode(prefix: str) -> str:
    """Return ``PREFIX-`` plus the complete 128-bit UUIDv4 in Base32."""
    normalized_prefix = prefix.upper()
    if normalized_prefix not in _ALLOWED_PREFIXES:
        raise ValueError("WB-compatible generation is limited to WHB and INB boxes")

    suffix = _encode_uuid(uuid.uuid4())
    barcode = f"{normalized_prefix}-{suffix}"
    if not is_wb_compatible_box_barcode(barcode):
        raise ValueError("generated box barcode is not WB-compatible")
    return barcode


def _encode_uuid(value: uuid.UUID) -> str:
    encoded = ["0"] * 26
    number = value.int
    for index in range(25, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[number & 31]
        number >>= 5
    return "".join(encoded)
