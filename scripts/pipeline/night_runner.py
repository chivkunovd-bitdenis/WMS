#!/usr/bin/env python3
"""Executable host loop for WMS Pipeline v2 waves.

The controller owns task state and receipts. This runner only coordinates the
loop around it: read next packet, advance mechanical dispatcher stages, create
handoff prompts, optionally call an external executor command, validate, repeat.
It deliberately does not invent BA/Product/Research/Architecture artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "scripts" / "pipeline" / "run.py"
DISPATCH = ROOT / "scripts" / "pipeline" / "dispatch.py"
AUTO_PASS = {
    "S01": ("pipeline-dispatcher", "TASK_INTAKE_READY"),
    "S02": ("pipeline-dispatcher", "IMPACT_CLASSIFIED"),
}
TERMINAL_STATUSES = {
    "WAITING",
    "PARKED",
    "IMPLEMENTATION_DONE",
    "READY_FOR_RELEASE",
    "DEPLOYING",
    "MONITORING",
    "STABILIZED_WITH_DEBT",
    "INVESTIGATION_DONE",
    "CANCELLED",
    "DONE",
}


class RunnerError(RuntimeError):
    """Night runner user-facing error."""


@dataclass(frozen=True)
class CmdResult:
    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class TaskDecision:
    task_id: str
    status: str
    stage: str
    role: str
    action: str
    detail: str


def run_cmd(args: list[str], *, check: bool = False, env: dict[str, str] | None = None) -> CmdResult:
    result = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    cmd = " ".join(shlex.quote(part) for part in args)
    if check and result.returncode != 0:
        raise RunnerError(f"{cmd} failed: {result.stderr.strip() or result.stdout.strip()}")
    return CmdResult(result.returncode, result.stdout, result.stderr)


def json_cmd(args: list[str]) -> dict[str, Any]:
    result = run_cmd(args, check=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"invalid JSON from {' '.join(args)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RunnerError(f"expected JSON object from {' '.join(args)}")
    return payload


def load_state(task_id: str) -> dict[str, Any]:
    return json_cmd([sys.executable, str(RUN), "status", "--task-id", task_id])


def next_packet(task_id: str) -> dict[str, Any]:
    return json_cmd([sys.executable, str(RUN), "next", "--task-id", task_id])


def validate(task_id: str) -> None:
    run_cmd([sys.executable, str(RUN), "validate", "--task-id", task_id], check=True)


def dispatch(task_id: str, executor: str) -> str:
    result = run_cmd([sys.executable, str(DISPATCH), "--task-id", task_id, "--executor", executor], check=True)
    return result.stdout.strip()


def all_task_ids() -> list[str]:
    ids = []
    for path in sorted((ROOT / "tasks").glob("*/state.json")):
        task_id = path.parent.name
        if not task_id.startswith("_"):
            ids.append(task_id)
    return ids


def wave_task_ids(wave_id: str) -> list[str]:
    wave_path = ROOT / "tasks" / "_waves" / f"{wave_id}.json"
    if not wave_path.exists():
        raise RunnerError(f"missing wave snapshot: {wave_path.relative_to(ROOT)}")
    payload = json.loads(wave_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise RunnerError(f"wave snapshot has no task list: {wave_path.relative_to(ROOT)}")
    ids = [task.get("task_id") for task in tasks if isinstance(task, dict)]
    return [task_id for task_id in ids if isinstance(task_id, str) and task_id]


def selected_task_ids(args: argparse.Namespace) -> list[str]:
    if args.task_id:
        return sorted(set(args.task_id))
    if args.wave_id:
        return wave_task_ids(args.wave_id)
    if args.all:
        return all_task_ids()
    raise RunnerError("choose --wave-id, --task-id, or --all")


def git_porcelain_paths() -> set[str]:
    result = run_cmd(["git", "status", "--porcelain=v1", "-z"], check=True)
    paths: set[str] = set()
    chunks = [chunk for chunk in result.stdout.split("\0") if chunk]
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        status = chunk[:2]
        path = chunk[3:]
        if status.startswith("R") or status.startswith("C"):
            index += 1
            if index < len(chunks):
                paths.add(chunks[index])
        paths.add(path)
        index += 1
    return paths


def dirty_task_ids() -> set[str]:
    dirty: set[str] = set()
    for path in git_porcelain_paths():
        parts = Path(path).parts
        if len(parts) >= 3 and parts[0] == "tasks" and parts[1] != "_waves":
            dirty.add(parts[1])
        if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "evidence":
            dirty.add(parts[2])
    return dirty


def advance_auto_stage(task_id: str, stage: str, role: str, verdict: str, args: argparse.Namespace) -> str:
    result = run_cmd(
        [
            sys.executable,
            str(RUN),
            "advance",
            "--task-id",
            task_id,
            "--stage",
            stage,
            "--verdict",
            verdict,
            "--role",
            role,
            "--agent",
            args.agent_id,
            "--executor",
            args.executor,
            "--input-tokens",
            "0",
            "--output-tokens",
            "0",
            "--estimated-usd",
            "0",
        ],
        check=False,
    )
    if result.code != 0:
        return f"advance_failed: {result.stderr.strip() or result.stdout.strip()}"
    return "advanced"


def executor_env(packet: dict[str, Any], dispatch_path: str, args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "WMS_PIPELINE_TASK_ID": str(packet["task_id"]),
            "WMS_PIPELINE_STAGE": str(packet["stage"]),
            "WMS_PIPELINE_ROLE": str(packet["role"]),
            "WMS_PIPELINE_STATUS": str(packet["status"]),
            "WMS_PIPELINE_DISPATCH": dispatch_path,
            "WMS_PIPELINE_EXECUTOR": args.executor,
            "WMS_PIPELINE_AGENT_ID": args.agent_id,
        }
    )
    return env


def run_external_executor(packet: dict[str, Any], dispatch_path: str, args: argparse.Namespace) -> str:
    if not args.executor_command:
        return "handoff_ready"
    command = args.executor_command.format(
        task_id=packet["task_id"],
        stage=packet["stage"],
        role=packet["role"],
        dispatch_path=dispatch_path,
        executor=args.executor,
    )
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=executor_env(packet, dispatch_path, args),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.executor_timeout_seconds,
    )
    if result.returncode != 0:
        return f"executor_failed: {result.stderr.strip() or result.stdout.strip()}"
    return "executor_completed"


def process_task(task_id: str, dirty: set[str], args: argparse.Namespace) -> TaskDecision:
    if args.git_dirty_guard and task_id in dirty and not args.allow_dirty_task:
        state = load_state(task_id)
        return TaskDecision(
            task_id,
            state.get("status", "UNKNOWN"),
            state.get("current_stage", "UNKNOWN"),
            "unknown",
            "skipped_dirty_task",
            "task/evidence paths have uncommitted changes; pass --allow-dirty-task to adopt them",
        )

    packet = next_packet(task_id)
    status = str(packet["status"])
    stage = str(packet["stage"])
    role = str(packet["role"])
    if status in TERMINAL_STATUSES:
        return TaskDecision(task_id, status, stage, role, "terminal", "no action")

    if stage in AUTO_PASS:
        expected_role, verdict = AUTO_PASS[stage]
        if role != expected_role:
            return TaskDecision(task_id, status, stage, role, "blocked", f"role mismatch: expected {expected_role}")
        if args.execute:
            detail = advance_auto_stage(task_id, stage, role, verdict, args)
            if detail == "advanced":
                validate(task_id)
                dispatch_path = dispatch(task_id, args.executor)
                return TaskDecision(task_id, "RUNNING", stage, role, "advanced", dispatch_path)
            return TaskDecision(task_id, status, stage, role, "advance_failed", detail)
        dispatch_path = dispatch(task_id, args.executor)
        return TaskDecision(task_id, status, stage, role, "planned_auto_advance", dispatch_path)

    dispatch_path = dispatch(task_id, args.executor)
    if args.execute:
        before = load_state(task_id)
        detail = run_external_executor(packet, dispatch_path, args)
        after = load_state(task_id)
        validate(task_id)
        if after.get("current_stage") != before.get("current_stage") or after.get("status") != before.get("status"):
            try:
                next_dispatch = dispatch(task_id, args.executor)
                detail = f"{detail}; next_dispatch={next_dispatch}"
            except RunnerError as exc:
                detail = f"{detail}; next_dispatch_failed={exc}"
        return TaskDecision(task_id, str(after.get("status")), str(after.get("current_stage")), role, detail.split(":", 1)[0], detail)
    return TaskDecision(task_id, status, stage, role, "handoff_ready", dispatch_path)


def run_cycle(task_ids: list[str], args: argparse.Namespace) -> list[TaskDecision]:
    dirty = dirty_task_ids() if args.git_dirty_guard else set()
    decisions: list[TaskDecision] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(process_task, task_id, dirty, args): task_id for task_id in task_ids}
        for future in as_completed(futures):
            task_id = futures[future]
            try:
                decisions.append(future.result())
            except Exception as exc:  # noqa: BLE001 - surface per-task failure, keep the wave alive.
                decisions.append(TaskDecision(task_id, "UNKNOWN", "UNKNOWN", "unknown", "error", str(exc)))
    return sorted(decisions, key=lambda item: item.task_id)


def print_decisions(cycle: int, decisions: list[TaskDecision], *, json_lines: bool) -> None:
    if json_lines:
        for decision in decisions:
            print(json.dumps({"cycle": cycle, **decision.__dict__}, ensure_ascii=False))
        return
    print(f"cycle {cycle}: {len(decisions)} task decisions")
    for decision in decisions:
        print(
            f"{decision.task_id}: {decision.status} stage={decision.stage} role={decision.role} "
            f"action={decision.action} detail={decision.detail}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scripts/pipeline/night_runner.py")
    parser.add_argument("--wave-id")
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true", help="perform controller-safe actions; default only plans/dispatches")
    parser.add_argument("--executor", choices=["codex", "claude", "cursor"], default="codex")
    parser.add_argument("--executor-command", help="shell command for non-mechanical stages; receives WMS_PIPELINE_* env")
    parser.add_argument("--executor-timeout-seconds", type=int, default=3600)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-cycles", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--agent-id", default="night-runner")
    parser.add_argument("--git-dirty-guard", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-dirty-task", action="store_true")
    parser.add_argument("--json-lines", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_workers < 1:
        raise RunnerError("--max-workers must be >= 1")
    if args.max_cycles < 1:
        raise RunnerError("--max-cycles must be >= 1")
    task_ids = selected_task_ids(args)
    if not task_ids:
        raise RunnerError("no tasks selected")

    for cycle in range(1, args.max_cycles + 1):
        decisions = run_cycle(task_ids, args)
        print_decisions(cycle, decisions, json_lines=args.json_lines)
        if all(decision.action in {"terminal", "skipped_dirty_task"} for decision in decisions):
            break
        if cycle < args.max_cycles and args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
