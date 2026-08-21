#!/usr/bin/env python3
"""Smoke-test the executable Pipeline v2 night runner host loop."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "scripts" / "pipeline" / "run.py"
NIGHT_RUNNER = ROOT / "scripts" / "pipeline" / "night_runner.py"
TASK_ID = "TASK-NIGHT-RUNNER-SMOKE"
DIRTY_TASK_ID = "BLG-D06"


def command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def cleanup(task_id: str) -> None:
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / task_id, ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / task_id, ignore_errors=True)
    shutil.rmtree(ROOT / "docs" / "evidence" / task_id, ignore_errors=True)


def open_task(task_id: str) -> subprocess.CompletedProcess[str]:
    return command(
        str(RUN),
        "open",
        "--task-id",
        task_id,
        "--source",
        f"night runner smoke {task_id}",
        "--traits",
        "process_change",
        "--risk-level",
        "low",
        "--owner-agent",
        "night-runner-smoke",
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


def load_state(task_id: str) -> dict:
    result = command(str(RUN), "status", "--task-id", task_id)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def main() -> int:
    failures: list[str] = []
    product_before = product_git_state()
    cleanup(TASK_ID)
    dirty_marker = ROOT / "tasks" / DIRTY_TASK_ID / ".night-runner-dirty-smoke"
    try:
        opened = open_task(TASK_ID)
        if opened.returncode != 0:
            failures.append(f"open task failed: {opened.stderr.strip()}")
        else:
            runner = command(
                str(NIGHT_RUNNER),
                "--task-id",
                TASK_ID,
                "--execute",
                "--max-cycles",
                "3",
                "--max-workers",
                "2",
                "--no-git-dirty-guard",
                "--json-lines",
            )
            if runner.returncode != 0:
                failures.append(f"night runner failed: {runner.stderr.strip()}")
            else:
                lines = [json.loads(line) for line in runner.stdout.splitlines() if line.strip()]
                actions = [line.get("action") for line in lines]
                if actions[:2] != ["advanced", "advanced"]:
                    failures.append(f"runner must auto-advance S01/S02, got actions={actions!r}")
                if not any(line.get("action") == "handoff_ready" for line in lines):
                    failures.append(f"runner must stop content stage as handoff_ready, got actions={actions!r}")
                state = load_state(TASK_ID)
                if sorted(state.get("verdicts", {}).keys()) != ["S01", "S02"]:
                    failures.append(f"runner must write only S01/S02 receipts, got {state.get('verdicts')!r}")
                if state.get("current_stage") != "S05":
                    failures.append(f"process_change task should stop at S05, got {state.get('current_stage')}")

        dirty_marker.write_text("temporary smoke marker\n", encoding="utf-8")
        guarded = command(
            str(NIGHT_RUNNER),
            "--task-id",
            DIRTY_TASK_ID,
            "--execute",
            "--max-cycles",
            "1",
            "--json-lines",
        )
        if guarded.returncode != 0:
            failures.append(f"night runner dirty guard failed: {guarded.stderr.strip()}")
        else:
            rows = [json.loads(line) for line in guarded.stdout.splitlines() if line.strip()]
            if not rows or rows[0].get("action") != "skipped_dirty_task":
                failures.append(f"dirty guard must skip uncommitted task paths, got {rows!r}")
    finally:
        cleanup(TASK_ID)
        dirty_marker.unlink(missing_ok=True)

    product_after = product_git_state()
    if product_after != product_before:
        failures.append("night runner smoke changed product code")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("PASS: night runner advances mechanical stages, writes dispatch, and protects dirty task work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
