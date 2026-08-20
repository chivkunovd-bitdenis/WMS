#!/usr/bin/env python3
"""Dependency-free recovery probes for Pipeline v2 durable JSON state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


class ReplayError(RuntimeError):
    """Durable recovery input is unusable."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"cannot read JSON state {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReplayError(f"JSON state {path} must contain an object")
    return value


def load_journal(path: Path) -> list[dict[str, Any]]:
    """Read complete records and ignore a torn final JSONL record."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1:
                break
            raise ReplayError(f"invalid non-final journal record {path}:{index + 1}: {exc}") from exc
        if not isinstance(value, dict):
            raise ReplayError(f"journal record {path}:{index + 1} must be an object")
        records.append(value)
    return records


def next_stage(state: dict[str, Any]) -> str | None:
    verdicts = state.get("verdicts", {})
    if not isinstance(verdicts, dict):
        raise ReplayError("state.verdicts must be an object")
    for stage_id in state.get("required_stages", []):
        if stage_id not in verdicts:
            return stage_id
    return None


def recover_task(state_path: Path, journal_path: Path) -> dict[str, Any]:
    """Rebuild the resumable cursor from durable state and journal facts."""
    state = load_json(state_path)
    journal = load_journal(journal_path)
    advanced = [
        event["stage_id"]
        for event in journal
        if event.get("type") == "STAGE_ADVANCED" and isinstance(event.get("stage_id"), str)
    ]
    return {
        "task_id": state.get("task_id"),
        "status": state.get("status"),
        "next_stage": next_stage(state),
        "last_valid_receipt": state.get("last_valid_receipt"),
        "completed_stages": list(state.get("verdicts", {}).keys()),
        "journal_advanced_stages": advanced,
        "journal_records": len(journal),
    }


def recover_wave(state_root: Path) -> list[dict[str, Any]]:
    return [
        recover_task(path, path.with_name("journal.jsonl"))
        for path in sorted(state_root.glob("*/state.json"))
    ]


class EffectReplayGuard:
    """Fence a committed external effect by its stable idempotency key."""

    def __init__(self, journal_path: Path) -> None:
        self.journal_path = journal_path
        self.committed = {
            event["effect_key"]
            for event in load_journal(journal_path)
            if event.get("type") == "EXTERNAL_EFFECT_COMMITTED"
            and isinstance(event.get("effect_key"), str)
        }

    def apply_once(self, effect_key: str, effect: Callable[[], None]) -> bool:
        if effect_key in self.committed:
            return False
        effect()
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "EXTERNAL_EFFECT_COMMITTED", "effect_key": effect_key}) + "\n")
        self.committed.add(effect_key)
        return True
