"""Official MOD evidence only; no warehouse mapping or operator selection."""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.db.withdrawal_repository import WithdrawalError

DISTANCE_MOD_GROUPS = frozenset(
    {
        "antiseptic",
        "bicycle",
        "perfumery",
        "toys",
        "conserve",
        "petfood",
        "lp",
        "milk",
        "seafood",
        "shoes",
        "radio",
        "gadgets",
        "vegetableoil",
        "softdrinks",
        "construction",
        "water",
        "electronics",
        "tires",
    }
)


def external_mod_fields(row: dict[str, Any], *, inn: str, pg: str) -> tuple[str, str | None] | None:
    """A candidate must contain every officially required field for this seller."""
    groups = row.get("productGroups")
    if row.get("inn") != inn or not isinstance(groups, list) or pg not in groups:
        return None
    fias = row.get("fiasId")
    if not isinstance(fias, str):
        return None
    try:
        uuid.UUID(fias)
    except ValueError:
        return None
    kpp = row.get("kpp") if len(inn) == 10 else None
    if len(inn) == 10 and (not isinstance(kpp, str) or re.fullmatch(r"[0-9]{9}", kpp) is None):
        return None
    return fias, kpp


def required_external_mod(
    *, inn: str, pg: str, rows: list[dict[str, Any]]
) -> tuple[str | None, str | None]:
    if pg not in DISTANCE_MOD_GROUPS:
        return None, None
    candidates = [
        fields for row in rows if (fields := external_mod_fields(row, inn=inn, pg=pg)) is not None
    ]
    if not candidates:
        raise WithdrawalError("external_mod_missing")
    if len(candidates) != 1:
        raise WithdrawalError("external_mod_ambiguous")
    # Cardinality has been proven, never choose the first of multiple candidates.
    (fields,) = candidates
    return fields
