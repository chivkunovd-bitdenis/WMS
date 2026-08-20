#!/usr/bin/env python3
"""Validate the machine-readable backlog queue without third-party dependencies."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "docs" / "product" / "backlog-queue.json"
REQUIRED_ITEM_FIELDS = {"id", "title", "source_section", "type", "readiness", "dependencies", "suggested_roles", "suggested_stages"}


def fail(message: str) -> int:
    print(f"backlog queue: {message}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fail(f"missing {QUEUE.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        return fail(f"invalid JSON: {exc}")
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        return fail("items must be a non-empty array")
    ids = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return fail(f"item {index} must be an object")
        missing = sorted(REQUIRED_ITEM_FIELDS - item.keys())
        if missing:
            return fail("item %s missing fields: %s" % (index, ", ".join(missing)))
        item_id = item["id"]
        if not isinstance(item_id, str) or not item_id.strip():
            return fail(f"item {index} id must be a non-empty string")
        ids.append(item_id)
        for field in ("dependencies", "suggested_roles", "suggested_stages"):
            if not isinstance(item[field], list):
                return fail(f"{item_id}.{field} must be an array")
    duplicates = sorted({item_id for item in ids if ids.count(item_id) > 1})
    if duplicates:
        return fail("duplicate IDs: %s" % ", ".join(duplicates))
    known_ids = set(ids)
    unknown = sorted({dep for item in items for dep in item["dependencies"] if dep not in known_ids})
    if unknown:
        return fail("unknown dependency IDs: %s" % ", ".join(unknown))
    print(f"backlog queue: OK ({len(items)} items, {len(ids)} unique IDs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
