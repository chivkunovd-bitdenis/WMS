#!/usr/bin/env python3
"""Validate the machine-readable blocker registry against the human registry."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BLOCKS_PATH = ROOT / "docs" / "product" / "blocks.json"
REGISTRY_PATH = ROOT / "docs" / "process" / "BLOCKERS-REGISTRY-RU.md"
HEADING_RE = re.compile(r"^### (BLK-[A-Z]+-\d{3}) — (.+)$", re.MULTILINE)
VALID_STATUSES = {"open", "narrowed", "closed"}
REQUIRED = {
    "id",
    "title",
    "status",
    "type",
    "owner_role",
    "affected_task_ids",
    "evidence",
    "last_verified_at",
    "resume_stage",
    "supersedes",
    "minimum_closure_artifact",
}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    blocks = json.loads(BLOCKS_PATH.read_text(encoding="utf-8"))
    entries = blocks.get("entries", [])
    markdown = REGISTRY_PATH.read_text(encoding="utf-8")
    markdown_ids = [match.group(1) for match in HEADING_RE.finditer(markdown)]

    require(blocks.get("status") in {"ACTIVE_DRAFT", "ACTIVE"}, "blocks registry status must be explicit", errors)
    require(isinstance(entries, list) and entries, "blocks registry must contain entries", errors)
    require(len(markdown_ids) >= 20, "human blockers registry must expose BLK headings", errors)

    ids: list[str] = []
    for index, entry in enumerate(entries):
        missing = REQUIRED - set(entry)
        require(not missing, f"entry {index} missing fields: {sorted(missing)}", errors)
        blocker_id = entry.get("id")
        require(isinstance(blocker_id, str) and blocker_id.startswith("BLK-"), f"entry {index} id must be BLK-*", errors)
        ids.append(str(blocker_id))
        require(entry.get("status") in VALID_STATUSES, f"{blocker_id}: invalid status", errors)
        require(isinstance(entry.get("title"), str) and len(entry["title"]) >= 8, f"{blocker_id}: title too short", errors)
        require(isinstance(entry.get("owner_role"), str) and entry["owner_role"], f"{blocker_id}: owner_role required", errors)
        require(isinstance(entry.get("affected_task_ids"), list), f"{blocker_id}: affected_task_ids must be an array", errors)
        require(isinstance(entry.get("evidence"), list) and entry["evidence"], f"{blocker_id}: evidence must be non-empty", errors)
        require(isinstance(entry.get("supersedes"), list), f"{blocker_id}: supersedes must be an array", errors)
        require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("last_verified_at"))), f"{blocker_id}: last_verified_at must be YYYY-MM-DD", errors)
        require(isinstance(entry.get("resume_stage"), str) and entry["resume_stage"], f"{blocker_id}: resume_stage required", errors)
        require(isinstance(entry.get("minimum_closure_artifact"), str) and len(entry["minimum_closure_artifact"]) >= 12, f"{blocker_id}: minimum closure artifact too short", errors)

    require(len(ids) == len(set(ids)), "duplicate blocker ids in blocks.json", errors)
    require(set(ids) == set(markdown_ids), "blocks.json ids must match BLOCKERS-REGISTRY-RU headings exactly", errors)

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    metatests = (ROOT / "scripts" / "ci" / "check_pipeline_metatests.py").read_text(encoding="utf-8")
    require("check_blockers_registry.py" in workflow, "CI must run blocker registry check", errors)
    require("check_blockers_registry.py" in metatests, "pipeline metatests must require blocker registry check", errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"blockers registry ok: {len(entries)} entries, status={blocks['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
