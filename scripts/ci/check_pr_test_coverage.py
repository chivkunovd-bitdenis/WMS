#!/usr/bin/env python3
"""Fail if PR body does not include a substantive Test coverage block (AGENTS.md)."""

from __future__ import annotations

import os
import re
import sys


def _extract_section(body: str) -> str:
    marker = "### Test coverage"
    i = body.find(marker)
    if i < 0:
        return ""
    rest = body[i + len(marker) :]
    m = re.search(r"^\s*###\s+\S", rest, flags=re.MULTILINE)
    if m:
        return rest[: m.start()].strip()
    return rest.strip()


def _keyword_depth(section: str) -> int:
    """Count distinct semantic markers (anti rubber-stamp: not only TC- ids)."""
    s = section.lower()
    keys = (
        "given",
        "when",
        "then",
        "negative",
        "restriction",
        "негатив",
        "огранич",
        "дано",
        "когда",
        "тогда",
        "ожидаемо",
        "expected",
    )
    return sum(1 for k in keys if k in s)


def _table_rows_with_tc(section: str) -> int:
    return sum(1 for line in section.splitlines() if "TC-" in line and "|" in line)


def main() -> int:
    labels_raw = os.environ.get("PR_LABELS", "")
    labels = {x.strip().lower() for x in labels_raw.split(",") if x.strip()}
    if "skip-test-coverage-check" in labels:
        print("skip: label skip-test-coverage-check")
        return 0

    body = os.environ.get("PR_BODY") or ""
    if "### Test coverage" not in body:
        print(
            "error: PR description must include a '### Test coverage' section "
            "(table with TC-ID / Applies). See AGENTS.md — Test coverage traceability.",
            file=sys.stderr,
        )
        return 1
    if "TC-" not in body:
        print(
            "error: PR '### Test coverage' section must list at least one TC-ID "
            "(e.g. TC-S06-001 or TC-NEW-001).",
            file=sys.stderr,
        )
        return 1

    section = _extract_section(body)
    if len(section) < 400:
        print(
            "error: '### Test coverage' block is too short (min ~400 chars of real "
            "Notes: Given/When/Then, negatives, restrictions). See AGENTS.md — "
            "Quality bar.",
            file=sys.stderr,
        )
        return 1
    if _table_rows_with_tc(section) < 2:
        print(
            "error: '### Test coverage' must include at least two table rows that "
            "mention TC-... (not a one-line stub).",
            file=sys.stderr,
        )
        return 1
    if not re.search(r"\|\s*Y\s*\|", section, flags=re.IGNORECASE):
        print(
            "error: mark at least one applicable row with Applies = Y in the "
            "Test coverage table.",
            file=sys.stderr,
        )
        return 1
    if _keyword_depth(section) < 3:
        print(
            "error: Test coverage Notes must show real behaviour, not IDs only: "
            "include at least three distinct hints among Given/When/Then (or "
            "дано/когда/тогда), negative/негатив, restriction/огранич..., expected. "
            "See AGENTS.md — Quality bar.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
