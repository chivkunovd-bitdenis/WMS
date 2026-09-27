"""Reviewed code snapshot, not a runtime scraper or owner configuration.

Source: https://docs.crpt.ru/gismt/Прослеживаемость_товаров/
Snapshot 2026-09-24. The source publishes current full vs partial/absent modes,
NOT commencement dates. snapshot_date must never become a legal start date.
Full maps to the LK_RECEIPT 'traceability started' statusEx branch.
"""

from datetime import date
from typing import Literal

SOURCE_URL = "https://docs.crpt.ru/gismt/Прослеживаемость_товаров/"
SNAPSHOT_VERSION = "crpt-traceability-2026-09-24"
SNAPSHOT_DATE = date(2026, 9, 24)
# No start dates are published in this table. Unknown pg stays unknown.
PUBLISHED_START_DATES: dict[str, date] = {}
FULL = frozenset(
    {"otp", "perfumery", "lp", "milk", "furslp", "ncp", "shoes", "electronics", "tires"}
)
PARTIAL_OR_ABSENT = frozenset(
    {
        "carparts",
        "alcohol",
        "antiseptic",
        "bio",
        "grocery",
        "nabeer",
        "bicycle",
        "vetpharma",
        "water",
        "toys",
        "cableraw",
        "conserve",
        "petfood",
        "chemistry",
        "wheelchairs",
        "furs",
        "seafood",
        "autofluids",
        "meat",
        "gadgets",
        "opticfiber",
        "heater",
        "books",
        "beer",
        "pyrotechnics",
        "fire",
        "polymer",
        "frozen",
        "nicotindev",
        "radio",
        "vegetableoil",
        "sweets",
        "softdrinks",
        "construction",
        "tobacco",
        "titan",
        "homeware",
        "fertilizers",
    }
)


def traceability_mode(pg: str | None) -> Literal["started", "not_started"] | None:
    if pg in FULL:
        return "started"
    if pg in PARTIAL_OR_ABSENT:
        return "not_started"
    return None
