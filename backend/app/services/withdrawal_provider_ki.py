"""Provider identity projection, preserving the stored scanner value verbatim."""

from app.services.true_api_marking_check import short_ki


def provider_ki(original: str) -> str:
    # Reuse the strict existing AI01+AI21 parser, not scanner repair heuristics.
    # A naked KI has the same terminal boundary as a GS-terminated first field.
    value = short_ki(original if "\x1d" in original else original + "\x1d")
    if value is None or not 18 <= len(value) <= 74:
        raise ValueError("invalid_provider_ki")
    serial = value[18:]
    if not serial or any(ord(char) < 33 or ord(char) > 126 for char in serial):
        raise ValueError("invalid_provider_ki")
    # Cryptographic fields are recognized only at explicit GS boundaries.
    if "\x1d" in original:
        tail = original.split("\x1d")[1:]
        if any(
            not part or not part.startswith(("91", "92", "93")) or len(part) <= 2 for part in tail
        ):
            raise ValueError("ambiguous_provider_ki")
    return value
