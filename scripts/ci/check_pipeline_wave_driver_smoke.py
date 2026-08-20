#!/usr/bin/env python3
"""Smoke-test the read-only Pipeline v2 wave-driver allocation plan."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "scripts" / "pipeline" / "wave_driver.py"


def write_snapshot(root: Path, task_id: str, status: str, base_sha: str) -> None:
    path = root / task_id / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"task_id": task_id, "status": status, "current_stage": "S01", "base_sha": base_sha, "branch": "test"}) + "\n",
        encoding="utf-8",
    )


def product_git_state() -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "frontend", "backend"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def main() -> int:
    failures: list[str] = []
    product_before = product_git_state()
    with tempfile.TemporaryDirectory(prefix="pipeline-wave-driver-") as raw_root:
        tasks_root = Path(raw_root) / "tasks"
        write_snapshot(tasks_root, "TASK-WAVE-A", "WAITING", "a" * 40)
        write_snapshot(tasks_root, "TASK-WAVE-B", "WAITING", "b" * 40)
        write_snapshot(tasks_root, "TASK-WAVE-IGNORED", "QUEUED", "c" * 40)
        result = subprocess.run(
            [sys.executable, str(DRIVER), "--tasks-root", str(tasks_root), "--wave-id", "smoke-wave"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        failures.append(f"wave driver failed: {result.stderr.strip()}")
        plan: dict = {}
    else:
        plan = json.loads(result.stdout)
    if plan:
        if plan.get("driver_mode") != "dry_run":
            failures.append("driver must identify output as dry_run")
        for flag in ("writes_state", "starts_agents", "creates_worktrees"):
            if plan.get(flag) is not False:
                failures.append(f"dry-run must keep {flag}=false")
        tasks = plan.get("tasks", [])
        if [task.get("task_id") for task in tasks] != ["TASK-WAVE-A", "TASK-WAVE-B"]:
            failures.append(f"driver must plan only sorted WAITING tasks: {tasks!r}")
        resources = [resource for task in tasks for resource in task["allocation"]["resources"]]
        if len(resources) != len(set(resources)):
            failures.append("dry-run allocations must be resource-isolated")
        for task in tasks:
            worktree = ROOT / task["allocation"]["worktree"]
            if worktree.exists():
                failures.append(f"dry-run must not create planned worktree: {worktree}")
    product_after = product_git_state()
    if product_after != product_before:
        failures.append("wave driver smoke changed product code")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: wave driver dry-run plans isolated resources without agents, worktrees, state, or product writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
