#!/usr/bin/env python3
"""Minimal local controller for Pipeline v2 task state.

This is the first executable slice of the target wave-driver. It owns runtime
state under .pipeline-state/ and publishes read-only snapshots under tasks/.
It deliberately refuses to mark production DONE while the pipeline is not ACTIVE.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "pipeline" / "pipeline.yml"
STORE_ROOT = ROOT / ".pipeline-state" / "tasks"
SNAPSHOT_ROOT = ROOT / "tasks"

TOTAL_ORDER = [
    "S01",
    "S02",
    "B01",
    "B02",
    "B03",
    "B04",
    "S03",
    "S04",
    "S05",
    "S06",
    "S07",
    "S08",
    "S09",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
    "S16",
    "S17",
    "S18",
    "S19",
    "S20",
    "S21",
    "S22",
    "S23",
    "S24",
    "S25",
    "S26",
    "S27",
    "S28",
]

ROLE_BY_STAGE = {
    "S01": "pipeline-dispatcher",
    "S02": "pipeline-dispatcher",
    "B01": "pipeline-ba",
    "B02": "pipeline-ba",
    "B03": "pipeline-ba",
    "B04": "pipeline-reviewer",
    "S03": "pipeline-ba",
    "S04": "pipeline-reviewer",
    "S05": "pipeline-ba",
    "S06": "pipeline-ba",
    "S07": "pipeline-product",
    "S08": "pipeline-ba",
    "S09": "pipeline-ba",
    "S10": "pipeline-product",
    "S11": "pipeline-product",
    "S12": "pipeline-ba",
    "S13": "solution-architect",
    "S14": "pipeline-reviewer",
    "S15": "pipeline-ba",
    "S16": "pipeline-product",
    "S17": "pipeline-dispatcher",
    "S18": "pipeline-dev",
    "S19": "pipeline-dev",
    "S20": "pipeline-reviewer",
    "S21": "pipeline-dev",
    "S22": "pipeline-reviewer",
    "S23": "pipeline-reviewer",
    "S24": "pipeline-product",
    "S25": "pipeline-browser-product",
    "S26": "pipeline-dispatcher",
    "S27": "pipeline-dispatcher",
    "S28": "pipeline-reviewer",
}


class PipelineError(RuntimeError):
    """User-facing controller error."""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"missing {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON in {path.relative_to(ROOT)}: {exc}") from exc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"git {' '.join(args)} failed") from exc


def load_contract() -> dict[str, Any]:
    return load_json(CONTRACT_PATH)


def contract_hash() -> str:
    return "sha256:" + sha256_file(CONTRACT_PATH)


def task_paths(task_id: str) -> tuple[Path, Path, Path]:
    store_dir = STORE_ROOT / task_id
    return store_dir / "state.json", store_dir / "journal.jsonl", SNAPSHOT_ROOT / task_id / "state.json"


def append_journal(task_id: str, event: dict[str, Any]) -> None:
    _, journal_path, _ = task_paths(task_id)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    event = {"at": now_iso(), **event}
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def load_state(task_id: str) -> dict[str, Any]:
    state_path, _, _ = task_paths(task_id)
    return load_json(state_path)


def save_state(state: dict[str, Any], event: dict[str, Any]) -> None:
    task_id = state["task_id"]
    state_path, _, snapshot_path = task_paths(task_id)
    state["heartbeat_at"] = now_iso()
    state["pipeline_hash"] = contract_hash()
    write_json(state_path, state)
    snapshot = copy.deepcopy(state)
    snapshot["_snapshot_note"] = "Read-only Git snapshot; controller state lives in .pipeline-state/."
    write_json(snapshot_path, snapshot)
    append_journal(task_id, event)


def stage_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["id"]: stage for stage in contract["stages"]}


def order_stages(stage_ids: set[str]) -> list[str]:
    return [stage_id for stage_id in TOTAL_ORDER if stage_id in stage_ids]


def required_stages(contract: dict[str, Any], traits: list[str], risk_level: str) -> list[str]:
    stages = {
        stage["id"]
        for stage in contract["stages"]
        if stage.get("enabled_when") == "always"
    }
    for trait in traits:
        trait_contract = contract["traits"].get(trait)
        if trait_contract is None:
            raise PipelineError(f"unknown trait: {trait}")
        stages.update(trait_contract["required_stages"])
    if risk_level in {"high", "critical"}:
        stages.update({"S13", "S14"})
    return order_stages(stages)


def source_hash(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def current_branch() -> str:
    return git_output("branch", "--show-current") or "DETACHED"


def current_sha() -> str:
    return git_output("rev-parse", "HEAD")


def parse_traits(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def command_open(args: argparse.Namespace) -> int:
    contract = load_contract()
    traits = parse_traits(args.traits)
    required = required_stages(contract, traits, args.risk_level)
    task_id = args.task_id or "TASK-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    lease_until = datetime.now(UTC) + timedelta(minutes=args.lease_minutes)

    state = {
        "task_id": task_id,
        "source_hash": source_hash(args.source),
        "source_excerpt": args.source[:240],
        "pipeline_version": contract["pipeline_version"],
        "pipeline_hash": contract_hash(),
        "traits": traits,
        "risk_level": args.risk_level,
        "required_stages": required,
        "current_stage": "S01",
        "status": "QUEUED",
        "base_sha": args.base_sha or current_sha(),
        "branch": args.branch or current_branch(),
        "worktree": str(ROOT),
        "environment_id": args.environment_id,
        "database": args.database,
        "redis_namespace": args.redis_namespace,
        "celery_queue": args.celery_queue,
        "emulator_namespace": args.emulator_namespace,
        "owner_agent": args.owner_agent,
        "attempt": 1,
        "lease_until": lease_until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "heartbeat_at": now_iso(),
        "last_valid_receipt": None,
        "blocker": None,
        "resume_condition": None,
        "verdicts": {},
        "commits": [],
    }
    save_state(state, {"type": "TASK_OPENED", "task_id": task_id, "required_stages": required})
    print(json.dumps({"task_id": task_id, "status": state["status"], "required_stages": required}, ensure_ascii=False))
    return 0


def command_classify(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    traits = parse_traits(args.traits)
    risk_level = args.risk_level or state.get("risk_level", "low")
    old_required = state["required_stages"]
    new_required = required_stages(contract, traits, risk_level)
    state["traits"] = traits
    state["risk_level"] = risk_level
    state["required_stages"] = new_required
    if not state.get("verdicts"):
        state["current_stage"] = first_missing_stage(state)
        state["status"] = "QUEUED"
    elif old_required != new_required:
        state["current_stage"] = first_missing_stage(state)
        state["status"] = "REWORK"
    save_state(
        state,
        {
            "type": "TASK_CLASSIFIED",
            "task_id": args.task_id,
            "old_required_stages": old_required,
            "new_required_stages": new_required,
        },
    )
    print(json.dumps({"task_id": args.task_id, "required_stages": new_required}, ensure_ascii=False))
    return 0


def first_missing_stage(state: dict[str, Any]) -> str:
    verdicts = state.get("verdicts", {})
    for stage_id in state["required_stages"]:
        if stage_id not in verdicts:
            return stage_id
    return state["required_stages"][-1]


def receipt_for(state: dict[str, Any], stage_id: str, verdict: str, role: str, agent: str) -> dict[str, Any]:
    payload = {
        "task_id": state["task_id"],
        "run_id": f"{state['task_id']}:{stage_id}:{len(state.get('verdicts', {})) + 1}",
        "stage_id": stage_id,
        "pipeline_hash": contract_hash(),
        "role_binding_id": role,
        "agent_identity": agent,
        "input_hashes": {"state_before": stable_hash(state)},
        "output_hashes": {},
        "parent_receipt_hash": state.get("last_valid_receipt"),
        "baseline_sha": state["base_sha"],
        "started_at": now_iso(),
        "finished_at": now_iso(),
        "verdict": verdict,
        "blocker": None,
        "resume_stage": None,
    }
    payload["signature"] = stable_hash(payload)
    return payload


def command_advance(args: argparse.Namespace) -> int:
    contract = load_contract()
    stages = stage_map(contract)
    state = load_state(args.task_id)
    stage_id = args.stage
    if stage_id not in state["required_stages"]:
        raise PipelineError(f"{stage_id} is not required for task {args.task_id}")
    if stage_id != first_missing_stage(state):
        raise PipelineError(f"{stage_id} is not the next missing stage; expected {first_missing_stage(state)}")
    if args.verdict not in stages[stage_id]["pass_verdicts"]:
        raise PipelineError(f"{args.verdict} is not an allowed pass verdict for {stage_id}")

    receipt = receipt_for(state, stage_id, args.verdict, args.role, args.agent)
    evidence_dir = ROOT / "docs" / "evidence" / args.task_id
    receipt_path = evidence_dir / f"{stage_id}-{args.verdict}.receipt.json"
    write_json(receipt_path, receipt)

    state["verdicts"][stage_id] = {
        "verdict": args.verdict,
        "receipt_path": str(receipt_path.relative_to(ROOT)),
        "receipt_hash": stable_hash(receipt),
    }
    state["last_valid_receipt"] = stable_hash(receipt)
    if len(state["verdicts"]) == len(state["required_stages"]):
        state["status"] = "IMPLEMENTATION_DONE"
    else:
        state["status"] = "RUNNING"
        state["current_stage"] = first_missing_stage(state)
    save_state(state, {"type": "STAGE_ADVANCED", "stage_id": stage_id, "verdict": args.verdict})
    print(json.dumps({"task_id": args.task_id, "stage": stage_id, "status": state["status"]}, ensure_ascii=False))
    return 0


def validate_state(contract: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_required = required_stages(contract, state.get("traits", []), state.get("risk_level", "low"))
    if state.get("pipeline_version") != contract["pipeline_version"]:
        errors.append(f"{state['task_id']}: stale pipeline_version")
    if state.get("pipeline_hash") != contract_hash():
        errors.append(f"{state['task_id']}: stale pipeline_hash")
    if state.get("required_stages") != expected_required:
        errors.append(f"{state['task_id']}: required_stages do not match traits/risk")
    if state.get("current_stage") not in TOTAL_ORDER:
        errors.append(f"{state['task_id']}: invalid current_stage")
    if state.get("status") == "DONE" and contract.get("status") != "ACTIVE":
        errors.append(f"{state['task_id']}: DONE is forbidden while pipeline is not ACTIVE")
    if state.get("status") == "DONE" and "S28" not in state.get("verdicts", {}):
        errors.append(f"{state['task_id']}: DONE requires S28 production trace verdict")
    for stage_id in state.get("verdicts", {}):
        if stage_id not in state.get("required_stages", []):
            errors.append(f"{state['task_id']}: verdict for non-required stage {stage_id}")
    return errors


def iter_states() -> list[dict[str, Any]]:
    if not STORE_ROOT.exists():
        return []
    return [load_json(path) for path in sorted(STORE_ROOT.glob("*/state.json"))]


def command_validate(args: argparse.Namespace) -> int:
    contract = load_contract()
    states = [load_state(args.task_id)] if args.task_id else iter_states()
    errors: list[str] = []
    for state in states:
        errors.extend(validate_state(contract, state))
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"validated_tasks": [state["task_id"] for state in states]}, ensure_ascii=False))
    return 0


def command_status(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def next_stage_packet(state: dict[str, Any]) -> dict[str, Any]:
    stage_id = first_missing_stage(state)
    return {
        "task_id": state["task_id"],
        "stage": stage_id,
        "role": ROLE_BY_STAGE.get(stage_id, "pipeline-dispatcher"),
        "status": state["status"],
        "traits": state["traits"],
        "risk_level": state.get("risk_level", "low"),
        "required_stages": state["required_stages"],
        "done_stages": sorted(state.get("verdicts", {}).keys(), key=TOTAL_ORDER.index),
        "worktree": state["worktree"],
        "branch": state["branch"],
        "base_sha": state["base_sha"],
        "rules": [
            "Read AGENTS.md, docs/process/PIPELINE-RU.md and pipeline/pipeline.yml first.",
            "Do not accept your own work.",
            "Use python3 scripts/pipeline/run.py advance only for the stage you own.",
            "Do not set DONE while pipeline status is not ACTIVE.",
        ],
    }


def command_next(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    print(json.dumps(next_stage_packet(state), ensure_ascii=False, indent=2))
    return 0


def command_packet(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    packet = next_stage_packet(state)
    packet_path = ROOT / "tasks" / args.task_id / f"{packet['stage']}-{packet['role']}-packet.json"
    write_json(packet_path, packet)
    append_journal(args.task_id, {"type": "AGENT_PACKET_WRITTEN", "path": str(packet_path.relative_to(ROOT))})
    print(json.dumps({"packet_path": str(packet_path.relative_to(ROOT)), **packet}, ensure_ascii=False))
    return 0


def command_close(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    allowed = {"IMPLEMENTATION_DONE", "READY_FOR_RELEASE", "CANCELLED"}
    if contract.get("status") == "ACTIVE":
        allowed.add("DONE")
    if args.status not in allowed:
        raise PipelineError(f"{args.status} is not allowed while pipeline status is {contract.get('status')}")
    state["status"] = args.status
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "TASK_CLOSED", "status": args.status})
    print(json.dumps({"task_id": args.task_id, "status": args.status}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scripts/pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    open_p = sub.add_parser("open")
    open_p.add_argument("--task-id")
    open_p.add_argument("--source", required=True)
    open_p.add_argument("--traits", default="")
    open_p.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], default="low")
    open_p.add_argument("--base-sha")
    open_p.add_argument("--branch")
    open_p.add_argument("--environment-id", default="local")
    open_p.add_argument("--database", default="local")
    open_p.add_argument("--redis-namespace", default="local")
    open_p.add_argument("--celery-queue", default="local")
    open_p.add_argument("--emulator-namespace", default="local")
    open_p.add_argument("--owner-agent", default="manual")
    open_p.add_argument("--lease-minutes", type=int, default=60)
    open_p.set_defaults(func=command_open)

    classify_p = sub.add_parser("classify")
    classify_p.add_argument("--task-id", required=True)
    classify_p.add_argument("--traits", required=True)
    classify_p.add_argument("--risk-level", choices=["low", "medium", "high", "critical"])
    classify_p.set_defaults(func=command_classify)

    advance_p = sub.add_parser("advance")
    advance_p.add_argument("--task-id", required=True)
    advance_p.add_argument("--stage", required=True)
    advance_p.add_argument("--verdict", required=True)
    advance_p.add_argument("--role", required=True)
    advance_p.add_argument("--agent", required=True)
    advance_p.set_defaults(func=command_advance)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--task-id")
    validate_p.set_defaults(func=command_validate)

    status_p = sub.add_parser("status")
    status_p.add_argument("--task-id", required=True)
    status_p.set_defaults(func=command_status)

    next_p = sub.add_parser("next")
    next_p.add_argument("--task-id", required=True)
    next_p.set_defaults(func=command_next)

    packet_p = sub.add_parser("packet")
    packet_p.add_argument("--task-id", required=True)
    packet_p.set_defaults(func=command_packet)

    close_p = sub.add_parser("close")
    close_p.add_argument("--task-id", required=True)
    close_p.add_argument("--status", required=True)
    close_p.set_defaults(func=command_close)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
