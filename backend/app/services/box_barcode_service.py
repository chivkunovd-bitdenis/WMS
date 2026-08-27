"""Generate physical-box barcodes accepted by Wildberries packaging uploads."""

from __future__ import annotations

import re
import secrets

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_WB_BOX_BARCODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,30}$")
_ALLOWED_PREFIXES = frozenset({"WHB", "INB"})
_SUFFIX_LENGTH = 14
_SUFFIX_BITS = _SUFFIX_LENGTH * 5


def is_wb_compatible_box_barcode(value: str) -> bool:
    """Return whether *value* satisfies WB's self-generated box-code rules."""
    return bool(
        _WB_BOX_BARCODE_PATTERN.fullmatch(value)
        and not value.upper().startswith("WB_")
    )


def generate_box_barcode(prefix: str) -> str:
    """Return a WB-compatible Code 128 value with 70 random bits.

    Fourteen Base32 symbols keep the complete value at 18 characters.  That
    length remains readable on the default 58x40 mm label at 203 dpi, unlike a
    maximum-length 30-character value, while retaining a negligible collision
    probability at WMS scale.
    """
    normalized_prefix = prefix.upper()
    if normalized_prefix not in _ALLOWED_PREFIXES:
        raise ValueError("WB-compatible generation is limited to WHB and INB boxes")

    suffix = _encode_number(secrets.randbits(_SUFFIX_BITS), _SUFFIX_LENGTH)
    barcode = f"{normalized_prefix}-{suffix}"
    if not is_wb_compatible_box_barcode(barcode):
        raise ValueError("generated box barcode is not WB-compatible")
    return barcode


def _encode_number(number: int, length: int) -> str:
    encoded = ["0"] * length
    for index in range(length - 1, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[number & 31]
        number >>= 5
    return "".join(encoded)
