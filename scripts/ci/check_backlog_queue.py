#!/usr/bin/env python3
"""Validate the machine-readable backlog queue without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / "docs" / "product" / "backlog-queue.json"
BUSINESS_DOC = ROOT / "tasks" / "20260820-night-bug-queue" / "BACKLOG-BUSINESS-MEANING-RU.md"
REQUIRED_ITEM_FIELDS = {
    "id",
    "title",
    "source_section",
    "business_meaning",
    "type",
    "readiness",
    "dependencies",
    "suggested_roles",
    "suggested_stages",
}


def has_narrative_description(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", value.strip()) if part]
    return len(sentences) >= 3


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
        if not has_narrative_description(item["business_meaning"]):
            return fail(f"{item_id}.business_meaning must contain at least three sentences")
        ids.append(item_id)
        for field in ("dependencies", "suggested_roles", "suggested_stages"):
            if not isinstance(item[field], list):
                return fail(f"{item_id}.{field} must be an array")
        client_items = item.get("client_items")
        if client_items is not None:
            if not isinstance(client_items, list) or not client_items:
                return fail(f"{item_id}.client_items must be a non-empty array")
            for client_index, client_item in enumerate(client_items):
                if not isinstance(client_item, dict):
                    return fail(f"{item_id}.client_items[{client_index}] must be an object")
                client_id = client_item.get("id")
                if not isinstance(client_id, str) or not client_id.strip():
                    return fail(f"{item_id}.client_items[{client_index}].id must be a non-empty string")
                if not isinstance(client_item.get("title"), str) or not client_item["title"].strip():
                    return fail(f"{client_id}.title must be a non-empty string")
                if not has_narrative_description(client_item.get("business_meaning")):
                    return fail(f"{client_id}.business_meaning must contain at least three sentences")
    duplicates = sorted({item_id for item in ids if ids.count(item_id) > 1})
    if duplicates:
        return fail("duplicate IDs: %s" % ", ".join(duplicates))
    known_ids = set(ids)
    unknown = sorted({dep for item in items for dep in item["dependencies"] if dep not in known_ids})
    if unknown:
        return fail("unknown dependency IDs: %s" % ", ".join(unknown))
    try:
        business_doc = BUSINESS_DOC.read_text(encoding="utf-8")
    except FileNotFoundError:
        return fail(f"missing {BUSINESS_DOC.relative_to(ROOT)}")
    for item in items:
        heading = f"## {item['id']} — {item['title']}"
        if heading not in business_doc or item["business_meaning"] not in business_doc:
            return fail(f"business document is out of sync for {item['id']}")
        for client_item in item.get("client_items", []):
            client_heading = f"### {client_item['id']} — {client_item['title']}"
            if client_heading not in business_doc or client_item["business_meaning"] not in business_doc:
                return fail(f"business document is out of sync for {client_item['id']}")
    print(f"backlog queue: OK ({len(items)} items, {len(ids)} unique IDs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
