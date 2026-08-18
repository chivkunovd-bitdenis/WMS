#!/usr/bin/env python3
"""Fail if PR body omits the mandatory WMS Product gate evidence."""

from __future__ import annotations

import os
import re
import sys


def _extract_section(body: str) -> str:
    match = re.search(r"^##+\s+Product gate\s*$", body, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return ""
    rest = body[match.end() :]
    next_header = re.search(r"^##+\s+\S", rest, flags=re.MULTILINE)
    if next_header:
        return rest[: next_header.start()].strip()
    return rest.strip()


def _has_any(section: str, *needles: str) -> bool:
    lowered = section.lower()
    return any(needle.lower() in lowered for needle in needles)


def main() -> int:
    body = os.environ.get("PR_BODY") or ""
    labels_raw = os.environ.get("PR_LABELS", "")
    labels = {x.strip().lower() for x in labels_raw.split(",") if x.strip()}

    section = _extract_section(body)
    if not section:
        print(
            "error: PR description must include '## Product gate'. "
            "Every WMS task needs BA feature cards, Product before dev, "
            "Code Review, and Product Browser Review after dev. See AGENTS.md.",
            file=sys.stderr,
        )
        return 1

    if "emergency-product-gate-bypass" in labels:
        if not re.search(r"EMERGENCY_BYPASS_USER_APPROVED\s*:\s*yes", section, flags=re.IGNORECASE):
            print(
                "error: emergency-product-gate-bypass label requires "
                "EMERGENCY_BYPASS_USER_APPROVED: yes in the Product gate section.",
                file=sys.stderr,
            )
            return 1
        return 0

    checked_boxes = len(re.findall(r"^\s*-\s*\[[xX]\]", section, flags=re.MULTILINE))
    if checked_boxes < 6:
        print(
            "error: Product gate checklist must be completed, not left as a "
            "blank PR template. Mark the completed BA/Product/Dev/Review/browser "
            "items with [x].",
            file=sys.stderr,
        )
        return 1

    required_literals = (
        "BA_READY",
        "PRODUCT_APPROVED_FOR_DEV",
        "CODE_REVIEW_PASSED",
        "PRODUCT_BROWSER_APPROVED",
    )
    missing = [literal for literal in required_literals if literal not in section]
    if missing:
        print(
            "error: Product gate section is missing required final verdict marker(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    checks = (
        ("feature cards", "feature_cards", "feature card", "карточ"),
        ("isolated", "изолирован"),
        ("real browser", "реальн", "visible tab", "видим"),
        ("evidence", "evidence_paths", "доказ"),
    )
    for group in checks:
        if not _has_any(section, *group):
            print(
                "error: Product gate section must mention "
                + " / ".join(group)
                + ".",
                file=sys.stderr,
            )
            return 1

    if len(section) < 500:
        print(
            "error: Product gate section is too short to be useful. "
            "Include feature cards path, isolated agents, real-browser evidence, "
            "visible states, and verdicts.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
