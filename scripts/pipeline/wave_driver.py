#!/usr/bin/env python3
"""Build a read-only resource plan for Pipeline v2 waiting tasks.

This driver deliberately has no execution path.  It reads Git task snapshots and
prints deterministic isolated allocations, but never creates worktrees, starts
agents, acquires controller locks, or writes controller/product state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_ROOT = ROOT / "tasks"
WORKTREE_ROOT = ROOT / ".worktrees" / "waves"
EVIDENCE_ROOT = ROOT / "docs" / "evidence"
SLUG_RE = re.compile(r"[^a-z0-9]+")


class WavePlanError(RuntimeError):
    """A task snapshot cannot safely receive a dry-run allocation."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WavePlanError(f"invalid JSON in {path}") from exc
    if not isinstance(value, dict):
        raise WavePlanError(f"task snapshot must be an object: {path}")
    return value


def task_slug(task_id: str) -> str:
    slug = SLUG_RE.sub("-", task_id.lower()).strip("-")
    if not slug:
        raise WavePlanError("task_id cannot be converted into an allocation name")
    return slug


def stable_wave_id(states: list[dict[str, Any]]) -> str:
    identity = [
        {"task_id": state["task_id"], "base_sha": state["base_sha"]}
        for state in states
    ]
    raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "wave-" + hashlib.sha256(raw).hexdigest()[:12]


def waiting_states(tasks_root: Path) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for path in sorted(tasks_root.glob("*/state.json")):
        state = load_json(path)
        if state.get("status") != "WAITING":
            continue
        task_id = state.get("task_id")
        base_sha = state.get("base_sha")
        if not isinstance(task_id, str) or not task_id:
            raise WavePlanError(f"WAITING snapshot has no task_id: {path}")
        if not isinstance(base_sha, str) or not base_sha:
            raise WavePlanError(f"{task_id} has no base_sha")
        states.append(state)
    return sorted(states, key=lambda state: state["task_id"])


def allocation_for(state: dict[str, Any], wave_id: str, index: int, port_base: int) -> dict[str, Any]:
    slug = task_slug(state["task_id"])
    api_port = port_base + index * 10
    frontend_port = api_port + 1
    namespace = f"wms-pipeline-{wave_id}-{slug}"
    worktree = WORKTREE_ROOT / wave_id / slug
    resources = [
        f"worktree:{worktree.relative_to(ROOT)}",
        f"port:{api_port}",
        f"port:{frontend_port}",
        f"database:{namespace}",
        f"redis:{namespace}",
        f"queue:{namespace}",
        f"emulator:{namespace}",
    ]
    declared_resources = state.get("resources")
    if isinstance(declared_resources, list):
        resources.extend(resource for resource in declared_resources if isinstance(resource, str) and resource)
    return {
        "task_id": state["task_id"],
        "status": state["status"],
        "current_stage": state.get("current_stage"),
        "base_sha": state["base_sha"],
        "branch": state.get("branch"),
        "allocation": {
            "worktree": str(worktree.relative_to(ROOT)),
            "ports": {"api": api_port, "frontend": frontend_port},
            "database": namespace,
            "redis_namespace": namespace,
            "celery_queue": namespace,
            "emulator_namespace": namespace,
            "evidence_dir": str((EVIDENCE_ROOT / state["task_id"]).relative_to(ROOT)),
            "resources": sorted(set(resources)),
        },
    }


def build_plan(tasks_root: Path, wave_id: str | None, port_base: int) -> dict[str, Any]:
    if not 1024 <= port_base <= 65515:
        raise WavePlanError("port-base must leave room for two ports per task")
    states = waiting_states(tasks_root)
    actual_wave_id = wave_id or stable_wave_id(states)
    if not re.fullmatch(r"[a-z0-9-]+", actual_wave_id):
        raise WavePlanError("wave-id may contain only lowercase letters, digits and hyphens")
    tasks = [allocation_for(state, actual_wave_id, index, port_base) for index, state in enumerate(states)]
    all_resources = [resource for task in tasks for resource in task["allocation"]["resources"]]
    if len(all_resources) != len(set(all_resources)):
        raise WavePlanError("resource collision in dry-run plan")
    return {
        "schema_version": "1.0",
        "driver_mode": "dry_run",
        "writes_state": False,
        "starts_agents": False,
        "creates_worktrees": False,
        "source": "read-only tasks/*/state.json snapshots with status WAITING",
        "wave_id": actual_wave_id,
        "tasks": tasks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scripts/pipeline/wave_driver.py")
    parser.add_argument("--tasks-root", type=Path, default=DEFAULT_TASKS_ROOT)
    parser.add_argument("--wave-id")
    parser.add_argument("--port-base", type=int, default=31000)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = build_plan(args.tasks_root, args.wave_id, args.port_base)
    except WavePlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    print(f"{plan['wave_id']}: dry-run; agents/worktrees/state writes disabled")
    for task in plan["tasks"]:
        allocation = task["allocation"]
        print(
            f"{task['task_id']}: {allocation['worktree']} | api={allocation['ports']['api']} "
            f"web={allocation['ports']['frontend']} | db={allocation['database']} "
            f"queue={allocation['celery_queue']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
