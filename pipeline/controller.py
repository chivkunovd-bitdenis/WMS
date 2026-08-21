#!/usr/bin/env python3
"""Minimal local controller for Pipeline v2 task state.

This is the first executable slice of the target wave-driver. It owns runtime
state under .pipeline-state/ and publishes read-only snapshots under tasks/.
It deliberately refuses to mark production DONE while the pipeline is not ACTIVE.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pipeline.budget_policy import load_budget_policy
from pipeline.model_policy import recommendation_for_packet


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "pipeline" / "pipeline.yml"
SCHEMA_PATHS = {
    "task_state": ROOT / "pipeline" / "task-state.schema.json",
    "receipt": ROOT / "pipeline" / "receipt.schema.json",
}
STORE_ROOT = ROOT / ".pipeline-state" / "tasks"
SNAPSHOT_ROOT = ROOT / "tasks"
LOCK_STORE_PATH = ROOT / ".pipeline-state" / "locks.json"
LOCK_AUDIT_PATH = ROOT / ".pipeline-state" / "locks.journal.jsonl"
CONTROLLER_LOCK_PATH = ROOT / ".pipeline-state" / "controller.lock"
EXTERNAL_EFFECT_STORE_PATH = ROOT / ".pipeline-state" / "external-effects.json"
BACKLOG_QUEUE_PATH = ROOT / "docs" / "product" / "backlog-queue.json"
BLOCKS_REGISTRY_PATH = ROOT / "docs" / "product" / "blocks.json"
WAVE_STORE_ROOT = ROOT / ".pipeline-state" / "waves"
WAVE_SNAPSHOT_ROOT = ROOT / "tasks" / "_waves"

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

BLOCKER_TYPES = [
    "OWNER_INPUT",
    "ENV",
    "FIXTURE",
    "EXTERNAL",
    "ORACLE_CONFLICT",
    "BASELINE",
    "ACCESS",
    "SECURITY",
    "RELEASE",
]

INCOMPATIBLE_STAGE_PAIRS = {
    ("S18", "S20"),
    ("S18", "S24"),
    ("S18", "S25"),
    ("S15", "S19"),
    ("S15", "S22"),
    ("S26", "S27"),
}

FAILURE_ROUTES = {
    "PRODUCT_REJECTED": {"status": "REWORK", "resume_stage": "S09", "blocker_type": "OWNER_INPUT"},
    "PRODUCT_CONTRACT_REJECTED": {"status": "REWORK", "resume_stage": "S08", "blocker_type": "OWNER_INPUT"},
    "ARCH_REVIEW_REWORK": {"status": "REWORK", "resume_stage": "S13", "blocker_type": "BASELINE"},
    "SNAPSHOT_CHANGED": {"status": "WAITING", "resume_stage": "S24", "blocker_type": "BASELINE"},
    "GOLD_CASE_RED": {"status": "REWORK", "resume_stage": "S18", "blocker_type": "FIXTURE"},
    "REGRESSION_DETECTED": {"status": "REWORK", "resume_stage": "B03", "blocker_type": "FIXTURE"},
    "REQUIRED_CASE_WITHOUT_BINDING": {"status": "WAITING", "resume_stage": "S19", "blocker_type": "FIXTURE"},
    "ORACLE_REWRITE_WITHOUT_SOURCE": {"status": "WAITING", "resume_stage": "S15", "blocker_type": "ORACLE_CONFLICT"},
    "MUTATING_CASE_UNSAFE": {"status": "WAITING", "resume_stage": "S15", "blocker_type": "FIXTURE"},
    "EMERGENCY_SCOPE_MISSING": {"status": "WAITING", "resume_stage": "S01", "blocker_type": "OWNER_INPUT"},
    "PRODUCTION_TRACE_FAILED": {"status": "REWORK", "resume_stage": "S27", "blocker_type": "RELEASE"},
}

TYPE_TRAITS = {
    "background_worker": ["background_worker"],
    "bug": ["bug"],
    "concurrency": ["database_change", "background_worker"],
    "data": ["database_change", "tenant_sensitive"],
    "data_integrity": ["database_change", "tenant_sensitive"],
    "external_contract": ["external_contract"],
    "mobile_contract": ["mobile_contract"],
    "new_domain": ["new_domain", "external_contract"],
    "new_module": ["new_module"],
    "performance": ["database_change", "background_worker"],
    "pipeline_change": ["pipeline_change"],
    "print": ["print"],
    "product_intake": ["process_change"],
    "release_change": ["release_change"],
    "test_infrastructure": ["pipeline_change"],
    "ui_change": ["ui_change"],
}

PRIORITY_RISK = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
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


@contextmanager
def controller_store_lock() -> Any:
    """Serialize local controller updates across separate CLI processes."""
    CONTROLLER_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONTROLLER_LOCK_PATH.open("a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_resources(raw: str) -> list[str]:
    resources = [item.strip() for item in raw.split(",") if item.strip()]
    if len(resources) != len(set(resources)):
        raise PipelineError("resource list contains duplicates")
    for resource in resources:
        if ":" not in resource or resource.startswith(":") or resource.endswith(":"):
            raise PipelineError(f"resource must use kind:name form: {resource}")
    return sorted(resources)


def load_locks() -> dict[str, Any]:
    if not LOCK_STORE_PATH.exists():
        return {"next_fencing_token": 1, "locks": {}}
    payload = load_json(LOCK_STORE_PATH)
    if not isinstance(payload.get("locks"), dict) or not isinstance(payload.get("next_fencing_token"), int):
        raise PipelineError("invalid local lock store")
    return payload


def append_lock_audit(event: dict[str, Any]) -> None:
    LOCK_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), **event}, ensure_ascii=False, sort_keys=True) + "\n")


def expire_locks(lock_store: dict[str, Any]) -> list[dict[str, Any]]:
    expired: list[dict[str, Any]] = []
    current = datetime.now(UTC)
    for resource, lock in list(lock_store["locks"].items()):
        if parse_timestamp(lock["lease_until"]) <= current:
            expired.append({"type": "LOCK_FORCED_EXPIRED", "resource": resource, **lock})
            del lock_store["locks"][resource]
    return expired


def lease_until(args: argparse.Namespace) -> str:
    seconds = args.lease_seconds if args.lease_seconds is not None else args.lease_minutes * 60
    if seconds < 0:
        raise PipelineError("lease duration must be zero or positive")
    until = datetime.now(UTC) + timedelta(seconds=seconds)
    return until.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def task_resources(state: dict[str, Any], raw_resources: str | None) -> list[str]:
    resources = parse_resources(raw_resources) if raw_resources is not None else state.get("resources", [])
    if not resources:
        raise PipelineError(f"{state['task_id']} has no declared resources")
    declared = set(state.get("resources", []))
    if not set(resources).issubset(declared):
        raise PipelineError("requested resources are outside the task resource list")
    return resources


def active_lock(lock_store: dict[str, Any], resource: str, task_id: str, agent: str, fencing_token: int) -> dict[str, Any]:
    lock = lock_store["locks"].get(resource)
    if lock is None:
        raise PipelineError(f"no active lease for {resource}; fencing token {fencing_token} is stale")
    if lock["task_id"] != task_id or lock["agent"] != agent or lock["fencing_token"] != fencing_token:
        raise PipelineError(f"fencing token {fencing_token} is stale for {resource}")
    return lock


def load_external_effects() -> dict[str, Any]:
    if not EXTERNAL_EFFECT_STORE_PATH.exists():
        return {"effects": {}}
    payload = load_json(EXTERNAL_EFFECT_STORE_PATH)
    if not isinstance(payload.get("effects"), dict):
        raise PipelineError("invalid external effect store")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def unsigned_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "signature"}


def type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "null":
        return value is None
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    return True


def schema_errors(schema_name: str, payload: dict[str, Any], label: str) -> list[str]:
    schema = load_json(SCHEMA_PATHS[schema_name])
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in payload:
            errors.append(f"{label}: schema {schema_name} missing {key}")
    for key, rules in schema.get("properties", {}).items():
        if key not in payload:
            continue
        if "const" in rules and payload[key] != rules["const"]:
            errors.append(f"{label}: schema {schema_name} field {key} must be {rules['const']}")
        expected = rules.get("type")
        expected_types = expected if isinstance(expected, list) else [expected]
        if expected and not any(type_matches(payload[key], item) for item in expected_types):
            errors.append(f"{label}: schema {schema_name} field {key} has invalid type")
        if rules.get("type") == "array" and isinstance(payload[key], list):
            item_type = rules.get("items", {}).get("type")
            if item_type:
                for index, item in enumerate(payload[key]):
                    if not type_matches(item, item_type):
                        errors.append(f"{label}: schema {schema_name} field {key}[{index}] has invalid type")
        if rules.get("type") == "integer" and "minimum" in rules and payload[key] < rules["minimum"]:
            errors.append(f"{label}: schema {schema_name} field {key} is below minimum")
    return errors


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


def refresh_contract_binding_if_no_receipts(contract: dict[str, Any], state: dict[str, Any]) -> None:
    if state.get("verdicts"):
        return
    state["pipeline_version"] = contract["pipeline_version"]
    state["pipeline_hash"] = contract_hash()


def source_hash(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def current_branch() -> str:
    return git_output("branch", "--show-current") or "DETACHED"


def current_sha() -> str:
    return git_output("rev-parse", "HEAD")


def parse_traits(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def load_backlog_queue() -> dict[str, Any]:
    payload = load_json(BACKLOG_QUEUE_PATH)
    items = payload.get("items")
    if not isinstance(items, list):
        raise PipelineError("backlog queue must contain items array")
    return payload


def backlog_items_by_id() -> dict[str, dict[str, Any]]:
    items = load_backlog_queue()["items"]
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise PipelineError("backlog queue contains invalid item")
        result[item["id"]] = item
    return result


def load_blocks_registry() -> dict[str, Any]:
    payload = load_json(BLOCKS_REGISTRY_PATH)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise PipelineError("blocks registry must contain entries array")
    return payload


def active_blockers_for_backlog(backlog_id: str) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for entry in load_blocks_registry()["entries"]:
        if not isinstance(entry, dict) or entry.get("status") == "closed":
            continue
        if entry.get("type") in {"backlog", "process_guard"}:
            continue
        affected = entry.get("affected_task_ids")
        if isinstance(affected, list) and backlog_id in affected:
            blockers.append(
                {
                    "id": entry["id"],
                    "title": entry["title"],
                    "status": entry["status"],
                    "type": entry["type"],
                    "owner_role": entry["owner_role"],
                    "resume_stage": entry["resume_stage"],
                    "minimum_closure_artifact": entry["minimum_closure_artifact"],
                }
            )
    return blockers


def unresolved_blockers(state: dict[str, Any]) -> list[dict[str, Any]]:
    resolved = {
        record.get("blocker_id")
        for record in state.get("blocker_resolutions", [])
        if isinstance(record, dict) and isinstance(record.get("blocker_id"), str)
    }
    return [
        blocker
        for blocker in state.get("blocked_by", [])
        if isinstance(blocker, dict) and blocker.get("id") not in resolved
    ]


def blocker_applies_at_stage(blocker: dict[str, Any], stage_id: str) -> bool:
    resume_stage = blocker.get("resume_stage")
    if not isinstance(resume_stage, str) or resume_stage not in TOTAL_ORDER:
        return False
    return TOTAL_ORDER.index(stage_id) >= TOTAL_ORDER.index(resume_stage)


def put_task_on_hold_for_blocker(state: dict[str, Any], blocker: dict[str, Any], stage_id: str) -> None:
    state["status"] = "WAITING"
    state["current_stage"] = stage_id
    state["blocker"] = {
        "type": "OWNER_INPUT",
        "reason_code": "OPEN_BLOCKER",
        "details": f"{blocker['id']}: {blocker['title']}",
        "owner": blocker.get("owner_role", "owner"),
        "created_at": now_iso(),
        "resume_stage": stage_id,
    }
    state["resume_condition"] = {
        "stage": stage_id,
        "condition": f"resolve {blocker['id']} with closure evidence",
    }
    save_state(state, {"type": "TASK_HELD_BY_OPEN_BLOCKER", "blocker_id": blocker["id"], "stage": stage_id})


def enforce_stage_blockers(state: dict[str, Any], stage_id: str) -> None:
    for blocker in unresolved_blockers(state):
        if blocker_applies_at_stage(blocker, stage_id):
            put_task_on_hold_for_blocker(state, blocker, stage_id)
            raise PipelineError(f"{stage_id} is blocked by {blocker['id']}: {blocker['title']}")


def ensure_no_unresolved_blockers_for_close(state: dict[str, Any], status: str) -> None:
    if status == "CANCELLED":
        return
    blockers = unresolved_blockers(state)
    if blockers:
        ids = ", ".join(blocker["id"] for blocker in blockers)
        raise PipelineError(f"{status} is blocked by unresolved blockers: {ids}")


def item_traits(item: dict[str, Any]) -> list[str]:
    traits = list(TYPE_TRAITS.get(item.get("type"), []))
    title = str(item.get("title", "")).lower()
    source = str(item.get("source_section", "")).lower()
    if "wb" in title or "wb" in source or "ozon" in title or "ozon" in source:
        traits.append("external_contract")
    if "селлер" in title or "tenant" in title:
        traits.append("tenant_sensitive")
    return unique_ordered(traits or ["process_change"])


def item_risk(item: dict[str, Any]) -> str:
    return PRIORITY_RISK.get(str(item.get("priority", "medium")), "medium")


def usage_from_args(args: argparse.Namespace, state: dict[str, Any], stage_id: str, role: str) -> dict[str, Any] | None:
    if not state.get("budget_enforced"):
        return None
    missing = [
        name for name in ("input_tokens", "output_tokens", "estimated_usd")
        if getattr(args, name, None) is None
    ]
    if missing:
        return None
    executor = args.executor or "codex"
    packet = {
        "task_id": state["task_id"],
        "stage": stage_id,
        "role": role,
        "status": state["status"],
        "traits": state.get("traits", []),
        "risk_level": state.get("risk_level", "low"),
    }
    model_recommendation = recommendation_for_packet(packet, executor)
    tier = args.tier or model_recommendation["tier"]
    model = args.model or model_recommendation["model"]
    return {
        "task_id": state["task_id"],
        "stage": stage_id,
        "role": role,
        "executor": executor,
        "model": model,
        "tier": tier,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "estimated_usd": args.estimated_usd,
        "agent_id": args.agent,
        "recorded_at": now_iso(),
    }


def task_budget_usage(state: dict[str, Any]) -> dict[str, float | int]:
    usage = state.get("budget_usage")
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "estimated_usd": 0.0}
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "estimated_usd": float(usage.get("estimated_usd", 0.0)),
    }


def wave_budget_usage(wave_id: str, current_task_id: str) -> dict[str, float | int]:
    total = {"input_tokens": 0, "output_tokens": 0, "estimated_usd": 0.0}
    for other in iter_states():
        if other.get("task_id") == current_task_id or other.get("wave_id") != wave_id:
            continue
        usage = task_budget_usage(other)
        total["input_tokens"] += int(usage["input_tokens"])
        total["output_tokens"] += int(usage["output_tokens"])
        total["estimated_usd"] += float(usage["estimated_usd"])
    return total


def put_task_on_budget_hold(state: dict[str, Any], details: str) -> None:
    stage_id = state["current_stage"]
    state["status"] = "WAITING"
    state["blocker"] = {
        "type": "OWNER_INPUT",
        "reason_code": "BUDGET_HARD_STOP",
        "details": details,
        "owner": "owner",
        "created_at": now_iso(),
        "resume_stage": stage_id,
    }
    state["resume_condition"] = {
        "stage": stage_id,
        "condition": "record owner budget override or lower scope before continuing",
    }
    save_state(state, {"type": "TASK_HELD_BY_BUDGET", "details": details, "stage": stage_id})


def enforce_budget(state: dict[str, Any], usage: dict[str, Any] | None) -> None:
    if not state.get("budget_enforced"):
        return
    if usage is None:
        put_task_on_budget_hold(state, "missing usage receipt")
        raise PipelineError("missing usage receipt")
    policy = load_budget_policy()
    required = set(policy["usage_receipt"]["required_fields"])
    missing = sorted(required - usage.keys())
    if missing:
        put_task_on_budget_hold(state, f"usage receipt missing fields: {', '.join(missing)}")
        raise PipelineError(f"usage receipt missing fields: {', '.join(missing)}")
    tier = usage["tier"]
    tier_limit = policy["limits"]["stage_tier"].get(tier)
    if not tier_limit:
        raise PipelineError(f"unknown budget tier: {tier}")
    stage_tokens = int(usage["input_tokens"]) + int(usage["output_tokens"])
    if float(usage["estimated_usd"]) > float(tier_limit["max_usd"]) or stage_tokens > int(tier_limit["max_tokens"]):
        put_task_on_budget_hold(state, f"stage budget exceeded for tier {tier}")
        raise PipelineError(f"stage budget exceeded for tier {tier}")

    current = task_budget_usage(state)
    next_task_usd = float(current["estimated_usd"]) + float(usage["estimated_usd"])
    next_task_tokens = int(current["input_tokens"]) + int(current["output_tokens"]) + stage_tokens
    task_limit = policy["limits"]["task"]
    if next_task_usd > float(task_limit["max_usd"]) or next_task_tokens > int(task_limit["max_tokens"]):
        put_task_on_budget_hold(state, "task budget exceeded")
        raise PipelineError("task budget exceeded")

    wave_id = state.get("wave_id")
    if isinstance(wave_id, str) and wave_id:
        wave_current = wave_budget_usage(wave_id, state["task_id"])
        next_wave_usd = float(wave_current["estimated_usd"]) + next_task_usd
        next_wave_tokens = int(wave_current["input_tokens"]) + int(wave_current["output_tokens"]) + next_task_tokens
        wave_limit = policy["limits"]["wave"]
        if next_wave_usd > float(wave_limit["max_usd"]) or next_wave_tokens > int(wave_limit["max_tokens"]):
            put_task_on_budget_hold(state, "wave budget exceeded")
            raise PipelineError("wave budget exceeded")


def record_budget_usage(state: dict[str, Any], usage: dict[str, Any] | None) -> None:
    if usage is None:
        return
    current = task_budget_usage(state)
    state["budget_usage"] = {
        "input_tokens": int(current["input_tokens"]) + int(usage["input_tokens"]),
        "output_tokens": int(current["output_tokens"]) + int(usage["output_tokens"]),
        "estimated_usd": round(float(current["estimated_usd"]) + float(usage["estimated_usd"]), 6),
    }
    state.setdefault("budget_usage_receipts", []).append(usage)


def invalidate_verdicts(state: dict[str, Any], reason: str, resume_stage: str | None = None) -> None:
    verdicts = state.get("verdicts", {})
    if resume_stage is None:
        invalidated = sorted(verdicts.keys(), key=TOTAL_ORDER.index)
        preserved: dict[str, Any] = {}
    else:
        resume_index = TOTAL_ORDER.index(resume_stage)
        invalidated = sorted(
            (stage for stage in verdicts if TOTAL_ORDER.index(stage) >= resume_index),
            key=TOTAL_ORDER.index,
        )
        preserved = {
            stage: verdict
            for stage, verdict in verdicts.items()
            if TOTAL_ORDER.index(stage) < resume_index
        }
    if not invalidated:
        return
    state.setdefault("invalidations", []).append(
        {
            "at": now_iso(),
            "reason": reason,
            "invalidated_stages": invalidated,
            "last_valid_receipt_before_invalidation": state.get("last_valid_receipt"),
        }
    )
    state["verdicts"] = preserved
    preserved_stages = sorted(preserved.keys(), key=TOTAL_ORDER.index)
    if preserved_stages:
        last_stage = preserved_stages[-1]
        last_verdict = preserved[last_stage]
        state["last_valid_receipt"] = last_verdict.get("receipt_hash") if isinstance(last_verdict, dict) else None
    else:
        state["last_valid_receipt"] = None
    state["current_stage"] = resume_stage or first_missing_stage(state)
    state["status"] = "REWORK"


def command_open(args: argparse.Namespace) -> int:
    contract = load_contract()
    traits = parse_traits(args.traits)
    if "emergency" in traits and (not args.emergency_scope_receipt or not args.emergency_debt_id):
        raise PipelineError("emergency trait requires signed scope receipt and immutable debt id")
    required = required_stages(contract, traits, args.risk_level)
    task_id = args.task_id or "TASK-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    lease_until = datetime.now(UTC) + timedelta(minutes=args.lease_minutes)
    resources = parse_resources(args.resources)

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
        "resources": resources,
        "emergency_scope_receipt": args.emergency_scope_receipt,
        "emergency_debt_id": args.emergency_debt_id,
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
    print(json.dumps({"task_id": task_id, "status": state["status"], "required_stages": required, "resources": resources}, ensure_ascii=False))
    return 0


def command_classify(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    refresh_contract_binding_if_no_receipts(contract, state)
    traits = parse_traits(args.traits)
    risk_level = args.risk_level or state.get("risk_level", "low")
    old_traits = list(state.get("traits", []))
    old_risk_level = state.get("risk_level", "low")
    old_required = state["required_stages"]
    new_required = required_stages(contract, traits, risk_level)
    state["traits"] = traits
    state["risk_level"] = risk_level
    state["required_stages"] = new_required
    invalidated = False
    if state.get("verdicts") and (old_traits != traits or old_risk_level != risk_level or old_required != new_required):
        invalidate_verdicts(state, "profile_changed_after_approval")
        invalidated = True
    if state.get("status") == "WAITING":
        state["current_stage"] = first_missing_stage(state)
    elif invalidated:
        state["current_stage"] = first_missing_stage(state)
    elif not state.get("verdicts"):
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


def receipt_for(
    state: dict[str, Any],
    stage_id: str,
    verdict: str,
    role: str,
    agent: str,
    usage_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
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
    if usage_receipt is not None:
        payload["usage_receipt"] = usage_receipt
    payload["signature"] = stable_hash(payload)
    return payload


def verdict_agent(state: dict[str, Any], stage_id: str) -> str | None:
    record = state.get("verdicts", {}).get(stage_id)
    if not isinstance(record, dict):
        return None
    if isinstance(record.get("agent_identity"), str):
        return record["agent_identity"]
    receipt_path_raw = record.get("receipt_path")
    if not isinstance(receipt_path_raw, str):
        return None
    receipt_path = path_within_root(receipt_path_raw)
    if receipt_path is None or not receipt_path.exists():
        return None
    try:
        receipt = load_json(receipt_path)
    except PipelineError:
        return None
    agent = receipt.get("agent_identity")
    return agent if isinstance(agent, str) else None


def enforce_independent_acceptance(state: dict[str, Any], stage_id: str, agent: str) -> None:
    for producer_stage, acceptor_stage in INCOMPATIBLE_STAGE_PAIRS:
        if stage_id != acceptor_stage:
            continue
        producer_agent = verdict_agent(state, producer_stage)
        if producer_agent and producer_agent == agent:
            raise PipelineError(f"{agent} cannot accept {acceptor_stage}; same identity already produced {producer_stage}")


def red_gold_cases(state: dict[str, Any]) -> list[str]:
    results = state.get("case_results", {})
    if not isinstance(results, dict):
        return []
    return sorted(
        case_id
        for case_id, result in results.items()
        if isinstance(result, dict) and result.get("tier") == "GOLD" and result.get("status") == "red"
    )


def route_failure(state: dict[str, Any], finding: str, details: str, owner: str) -> dict[str, Any]:
    route = FAILURE_ROUTES.get(finding)
    if route is None:
        raise PipelineError(f"unmapped failure verdict: {finding}")
    resume_stage = route["resume_stage"]
    if resume_stage not in state["required_stages"]:
        raise PipelineError(f"failure route {finding} targets non-required stage {resume_stage}")
    invalidate_verdicts(state, f"failure:{finding}", resume_stage)
    state["status"] = route["status"]
    state["current_stage"] = resume_stage
    if route["status"] == "WAITING":
        state["blocker"] = {
            "type": route["blocker_type"],
            "reason_code": finding,
            "details": details,
            "owner": owner,
            "created_at": now_iso(),
            "resume_stage": resume_stage,
        }
        state["resume_condition"] = {"stage": resume_stage, "condition": details}
    else:
        state["blocker"] = None
        state["resume_condition"] = None
    state.setdefault("failure_routes", []).append(
        {"at": now_iso(), "finding": finding, "status": state["status"], "resume_stage": resume_stage, "details": details}
    )
    return route


def command_advance(args: argparse.Namespace) -> int:
    contract = load_contract()
    stages = stage_map(contract)
    state = load_state(args.task_id)
    stage_id = args.stage
    if state.get("status") == "WAITING":
        blocker = state.get("blocker") or {}
        reason = blocker.get("reason_code") or blocker.get("details") or "blocked"
        raise PipelineError(f"{args.task_id} is WAITING ({reason}); run resume before advance")
    if stage_id not in state["required_stages"]:
        raise PipelineError(f"{stage_id} is not required for task {args.task_id}")
    if stage_id != first_missing_stage(state):
        raise PipelineError(f"{stage_id} is not the next missing stage; expected {first_missing_stage(state)}")
    expected_role = ROLE_BY_STAGE.get(stage_id)
    if expected_role and args.role != expected_role:
        raise PipelineError(f"{args.role} cannot advance {stage_id}; expected role {expected_role}")
    if args.verdict not in stages[stage_id]["pass_verdicts"]:
        raise PipelineError(f"{args.verdict} is not an allowed pass verdict for {stage_id}")
    enforce_independent_acceptance(state, stage_id, args.agent)
    enforce_stage_blockers(state, stage_id)
    if stage_id == "S22" and "S19" in state["required_stages"] and not state.get("case_bindings_complete"):
        raise PipelineError("S22 functional testing requires S19 runnable case bindings")
    if stage_id == "S23":
        red_cases = red_gold_cases(state)
        if red_cases:
            raise PipelineError(f"S23 integration is blocked by red GOLD cases: {', '.join(red_cases)}")
    usage_receipt = usage_from_args(args, state, stage_id, args.role)
    enforce_budget(state, usage_receipt)

    receipt = receipt_for(state, stage_id, args.verdict, args.role, args.agent, usage_receipt)
    evidence_dir = ROOT / "docs" / "evidence" / args.task_id
    receipt_path = evidence_dir / f"{stage_id}-{args.verdict}.receipt.json"
    write_json(receipt_path, receipt)

    state["verdicts"][stage_id] = {
        "verdict": args.verdict,
        "receipt_path": str(receipt_path.relative_to(ROOT)),
        "receipt_hash": stable_hash(receipt),
        "role_binding_id": args.role,
        "agent_identity": args.agent,
    }
    state["last_valid_receipt"] = stable_hash(receipt)
    record_budget_usage(state, usage_receipt)
    if stage_id == "S19" and args.verdict == "CASES_EXECUTABLE":
        state["case_bindings_complete"] = True
    if stage_id == "B01" and args.verdict == "NOT_REPRODUCED":
        state.setdefault("observations", []).append(
            {
                "stage": stage_id,
                "verdict": args.verdict,
                "created_at": now_iso(),
                "next_signal": "need observation signal before closure",
            }
        )
        state["status"] = "WAITING"
        state["current_stage"] = "B02" if "B02" in state["required_stages"] else first_missing_stage(state)
        state["blocker"] = {
            "type": "EXTERNAL",
            "reason_code": "OBSERVATION_REQUIRED",
            "details": "NOT_REPRODUCED cannot close the bug; wait for observation signal or oracle triage.",
            "owner": "pipeline-ba",
            "created_at": now_iso(),
            "resume_stage": state["current_stage"],
        }
        state["resume_condition"] = {"stage": state["current_stage"], "condition": "observation signal or oracle decision recorded"}
    elif len(state["verdicts"]) == len(state["required_stages"]):
        state["status"] = "IMPLEMENTATION_DONE"
    else:
        state["status"] = "RUNNING"
        state["current_stage"] = first_missing_stage(state)
    save_state(state, {"type": "STAGE_ADVANCED", "stage_id": stage_id, "verdict": args.verdict})
    print(json.dumps({"task_id": args.task_id, "stage": stage_id, "status": state["status"]}, ensure_ascii=False))
    return 0


def command_case_result(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    state.setdefault("case_results", {})[args.case_id] = {
        "tier": args.tier,
        "status": args.status,
        "mutates_state": args.mutates_state,
        "isolation": args.isolation,
        "ordered_journey": args.ordered_journey,
    }
    if args.status == "red" and args.tier == "GOLD":
        route_failure(state, "GOLD_CASE_RED", f"red GOLD case {args.case_id}", "case-runner")
    elif args.mutates_state and args.isolation not in {"fresh_snapshot", "transaction"} and not args.ordered_journey:
        route_failure(state, "MUTATING_CASE_UNSAFE", f"mutating case {args.case_id} needs isolation or ordered journey", "case-runner")
    else:
        errors = validate_state(contract, state)
        if errors:
            raise PipelineError("; ".join(errors))
    save_state(state, {"type": "CASE_RESULT_RECORDED", "case_id": args.case_id, "tier": args.tier, "status": args.status})
    print(json.dumps({"task_id": args.task_id, "case_id": args.case_id, "status": state["status"]}, ensure_ascii=False))
    return 0


def command_expectation_rewrite(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    if not args.oracle or not args.oracle_version:
        route_failure(state, "ORACLE_REWRITE_WITHOUT_SOURCE", "case expectation rewrite requires versioned oracle", "case-writer")
    else:
        state.setdefault("expectation_rewrites", []).append(
            {"case_id": args.case_id, "oracle": args.oracle, "oracle_version": args.oracle_version, "at": now_iso()}
        )
        errors = validate_state(contract, state)
        if errors:
            raise PipelineError("; ".join(errors))
    save_state(state, {"type": "EXPECTATION_REWRITE_RECORDED", "case_id": args.case_id})
    print(json.dumps({"task_id": args.task_id, "case_id": args.case_id, "status": state["status"]}, ensure_ascii=False))
    return 0


def command_failure(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    route = route_failure(state, args.finding, args.details, args.owner)
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "FAILURE_ROUTED", "finding": args.finding, "route": route})
    print(json.dumps({"task_id": args.task_id, "finding": args.finding, "status": state["status"], "resume_stage": route["resume_stage"]}, ensure_ascii=False))
    return 0


def command_record_release_proof(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    if args.commit:
        state.setdefault("commits", []).append(args.commit)
    if args.pushed_ref:
        state.setdefault("pushed_refs", []).append(args.pushed_ref)
    if args.check:
        state.setdefault("checks_passed", []).append(args.check)
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "RELEASE_PROOF_RECORDED", "commit": args.commit, "pushed_ref": args.pushed_ref, "check": args.check})
    print(json.dumps({"task_id": args.task_id, "commits": state.get("commits", []), "checks_passed": state.get("checks_passed", [])}, ensure_ascii=False))
    return 0


def command_external_effect(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    key = f"{args.task_id}:{args.effect}:{args.idempotency_key}"
    with controller_store_lock():
        effect_store = load_external_effects()
        existing = effect_store["effects"].get(key)
        if existing:
            print(json.dumps({"task_id": args.task_id, "effect": args.effect, "replayed": False, "record": existing}, ensure_ascii=False))
            return 0
        record = {"task_id": args.task_id, "effect": args.effect, "idempotency_key": args.idempotency_key, "created_at": now_iso()}
        effect_store["effects"][key] = record
        write_json(EXTERNAL_EFFECT_STORE_PATH, effect_store)
    append_journal(args.task_id, {"type": "EXTERNAL_EFFECT_COMMITTED", "effect_key": key, "effect": args.effect})
    print(json.dumps({"task_id": args.task_id, "effect": args.effect, "replayed": True, "record": record}, ensure_ascii=False))
    return 0


def path_within_root(relative_path: str) -> Path | None:
    path = Path(relative_path)
    if path.is_absolute():
        return None
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return resolved


def validate_receipts(contract: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    stages = stage_map(contract)
    previous_hash: str | None = None
    for stage_id in state.get("required_stages", []):
        if stage_id not in state.get("verdicts", {}):
            continue
        record = state["verdicts"][stage_id]
        if not isinstance(record, dict):
            errors.append(f"{state['task_id']}: verdict record for {stage_id} must be object")
            continue
        receipt_path_raw = record.get("receipt_path")
        if not isinstance(receipt_path_raw, str):
            errors.append(f"{state['task_id']}: verdict record for {stage_id} is missing receipt_path")
            continue
        receipt_path = path_within_root(receipt_path_raw)
        if receipt_path is None:
            errors.append(f"{state['task_id']}: receipt path for {stage_id} escapes repo root")
            continue
        try:
            receipt = load_json(receipt_path)
        except PipelineError as exc:
            errors.append(str(exc))
            continue
        errors.extend(schema_errors("receipt", receipt, f"{state['task_id']}:{stage_id}"))
        expected_receipt_hash = stable_hash(receipt)
        if record.get("receipt_hash") != expected_receipt_hash:
            errors.append(f"{state['task_id']}: receipt_hash mismatch for {stage_id}")
        if receipt.get("signature") != stable_hash(unsigned_payload(receipt)):
            errors.append(f"{state['task_id']}: invalid receipt signature for {stage_id}")
        if receipt.get("task_id") != state["task_id"]:
            errors.append(f"{state['task_id']}: receipt {stage_id} has wrong task_id")
        if receipt.get("stage_id") != stage_id:
            errors.append(f"{state['task_id']}: receipt {stage_id} has wrong stage_id")
        if receipt.get("pipeline_hash") != contract_hash():
            errors.append(f"{state['task_id']}: receipt {stage_id} has stale pipeline_hash")
        expected_role = ROLE_BY_STAGE.get(stage_id)
        if expected_role and receipt.get("role_binding_id") != expected_role:
            errors.append(f"{state['task_id']}: receipt {stage_id} has wrong role")
        allowed_verdicts = stages.get(stage_id, {}).get("pass_verdicts", [])
        if receipt.get("verdict") not in allowed_verdicts:
            errors.append(f"{state['task_id']}: receipt {stage_id} has invalid verdict")
        if record.get("verdict") != receipt.get("verdict"):
            errors.append(f"{state['task_id']}: verdict record mismatch for {stage_id}")
        if receipt.get("parent_receipt_hash") != previous_hash:
            errors.append(f"{state['task_id']}: receipt chain mismatch at {stage_id}")
        if state.get("budget_enforced"):
            usage = receipt.get("usage_receipt")
            required_usage_fields = set(load_budget_policy()["usage_receipt"]["required_fields"])
            if not isinstance(usage, dict):
                errors.append(f"{state['task_id']}: budget-enforced receipt {stage_id} is missing usage_receipt")
            else:
                missing_usage = sorted(required_usage_fields - usage.keys())
                if missing_usage:
                    errors.append(f"{state['task_id']}: usage_receipt {stage_id} missing {', '.join(missing_usage)}")
        previous_hash = expected_receipt_hash
    if state.get("last_valid_receipt") != previous_hash:
        errors.append(f"{state['task_id']}: last_valid_receipt does not match receipt chain")
    return errors


def validate_state(contract: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(schema_errors("task_state", state, state.get("task_id", "<unknown>")))
    expected_required = required_stages(contract, state.get("traits", []), state.get("risk_level", "low"))
    if state.get("pipeline_version") != contract["pipeline_version"]:
        errors.append(f"{state['task_id']}: stale pipeline_version")
    if state.get("pipeline_hash") != contract_hash():
        errors.append(f"{state['task_id']}: stale pipeline_hash")
    if state.get("required_stages") != expected_required:
        errors.append(f"{state['task_id']}: required_stages do not match traits/risk")
    if state.get("status") not in contract.get("lifecycle_statuses", []):
        errors.append(f"{state['task_id']}: invalid lifecycle status {state.get('status')}")
    if state.get("current_stage") not in TOTAL_ORDER:
        errors.append(f"{state['task_id']}: invalid current_stage")
    if state.get("status") == "DONE" and contract.get("status") != "ACTIVE":
        errors.append(f"{state['task_id']}: DONE is forbidden while pipeline is not ACTIVE")
    if state.get("status") == "DONE" and "S28" not in state.get("verdicts", {}):
        errors.append(f"{state['task_id']}: DONE requires S28 production trace verdict")
    if state.get("status") == "WAITING":
        if not state.get("blocker"):
            errors.append(f"{state['task_id']}: WAITING requires blocker")
        if not state.get("resume_condition"):
            errors.append(f"{state['task_id']}: WAITING requires resume_condition")
    for stage_id in state.get("verdicts", {}):
        if stage_id not in state.get("required_stages", []):
            errors.append(f"{state['task_id']}: verdict for non-required stage {stage_id}")
    errors.extend(validate_receipts(contract, state))
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


def report_line(state: dict[str, Any]) -> dict[str, Any]:
    stage_id = state.get("current_stage") or first_missing_stage(state)
    blocker = state.get("blocker") or {}
    blocker_text = "нет"
    if blocker:
        blocker_text = f"{blocker.get('type', 'UNKNOWN')}/{blocker.get('reason_code', 'UNKNOWN')}"
    verdicts = state.get("verdicts", {})
    evidence = "нет"
    if verdicts:
        last_stage = sorted(verdicts.keys(), key=TOTAL_ORDER.index)[-1]
        evidence = verdicts[last_stage].get("receipt_path") or "нет"
    return {
        "task_id": state["task_id"],
        "status": state["status"],
        "current_stage": stage_id,
        "owner": ROLE_BY_STAGE.get(stage_id, "pipeline-dispatcher"),
        "blocker": blocker_text,
        "evidence": evidence,
    }


def command_report(args: argparse.Namespace) -> int:
    rows = [report_line(state) for state in iter_states()]
    if args.format == "json":
        print(json.dumps({"tasks": rows}, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        print(
            "{task_id}: {status} | current_stage={current_stage} | owner={owner} | "
            "blocker={blocker} | evidence={evidence}".format(**row)
        )
    return 0


def command_hold(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    refresh_contract_binding_if_no_receipts(contract, state)
    resume_stage = args.resume_stage or first_missing_stage(state)
    if resume_stage not in state["required_stages"]:
        raise PipelineError(f"{resume_stage} is not required for task {args.task_id}")
    if args.blocker_type not in contract.get("blocker_types", []):
        raise PipelineError(f"{args.blocker_type} is not declared in pipeline blocker_types")
    state["status"] = "WAITING"
    state["current_stage"] = resume_stage
    state["blocker"] = {
        "type": args.blocker_type,
        "reason_code": args.reason_code,
        "details": args.reason,
        "owner": args.owner,
        "created_at": now_iso(),
        "resume_stage": resume_stage,
    }
    state["resume_condition"] = {
        "stage": resume_stage,
        "condition": args.resume_condition,
    }
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(
        state,
        {
            "type": "TASK_HELD",
            "stage": resume_stage,
            "blocker_type": args.blocker_type,
            "reason_code": args.reason_code,
        },
    )
    print(json.dumps({"task_id": args.task_id, "status": state["status"], "resume_stage": resume_stage}, ensure_ascii=False))
    return 0


def command_resume(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    refresh_contract_binding_if_no_receipts(contract, state)
    if state.get("status") != "WAITING":
        raise PipelineError(f"{args.task_id} is not WAITING")
    resumed_from = state.get("blocker")
    state["blocker"] = None
    state["resume_condition"] = None
    state["current_stage"] = first_missing_stage(state)
    if len(state.get("verdicts", {})) == len(state["required_stages"]):
        state["status"] = "IMPLEMENTATION_DONE"
    elif state.get("verdicts"):
        state["status"] = "RUNNING"
    else:
        state["status"] = "QUEUED"
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "TASK_RESUMED", "resumed_from": resumed_from, "by": args.by})
    print(json.dumps({"task_id": args.task_id, "status": state["status"], "current_stage": state["current_stage"]}, ensure_ascii=False))
    return 0


def next_stage_packet(state: dict[str, Any]) -> dict[str, Any]:
    stage_id = state.get("current_stage") if state.get("status") == "WAITING" else first_missing_stage(state)
    return {
        "task_id": state["task_id"],
        "stage": stage_id,
        "role": ROLE_BY_STAGE.get(stage_id, "pipeline-dispatcher"),
        "status": state["status"],
        "traits": state["traits"],
        "risk_level": state.get("risk_level", "low"),
        "model_policy": "pipeline/model-policy.yml",
        "required_stages": state["required_stages"],
        "done_stages": sorted(state.get("verdicts", {}).keys(), key=TOTAL_ORDER.index),
        "worktree": state["worktree"],
        "branch": state["branch"],
        "base_sha": state["base_sha"],
        "wave_id": state.get("wave_id"),
        "backlog_item_id": state.get("backlog_item_id"),
        "backlog_item": state.get("backlog_item"),
        "budget_enforced": state.get("budget_enforced", False),
        "budget_usage": state.get("budget_usage"),
        "blocked_by": unresolved_blockers(state),
        "blocker": state.get("blocker"),
        "resume_condition": state.get("resume_condition"),
        "rules": [
            "Read AGENTS.md, docs/process/PIPELINE-RU.md and pipeline/pipeline.yml first.",
            "Do not accept your own work.",
            "If status is WAITING, do not advance; report the blocker and wait for resume.",
            "If budget_enforced is true, advance requires usage receipt fields.",
            "If blocked_by is non-empty, do not pass the blocker resume stage without resolve-blocker evidence.",
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
    ensure_no_unresolved_blockers_for_close(state, args.status)
    if args.status in {"READY_FOR_RELEASE", "DONE"}:
        missing: list[str] = []
        if len(state.get("verdicts", {})) != len(state.get("required_stages", [])):
            missing.append("all required stage verdicts")
        if not state.get("commits"):
            missing.append("commit SHA")
        if not state.get("pushed_refs"):
            missing.append("pushed ref")
        if not state.get("checks_passed"):
            missing.append("passing checks")
        if missing:
            raise PipelineError(f"{args.status} requires {', '.join(missing)}")
    state["status"] = args.status
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "TASK_CLOSED", "status": args.status})
    print(json.dumps({"task_id": args.task_id, "status": args.status}, ensure_ascii=False))
    return 0


def command_resolve_blocker(args: argparse.Namespace) -> int:
    contract = load_contract()
    state = load_state(args.task_id)
    blocker_ids = {blocker.get("id") for blocker in state.get("blocked_by", []) if isinstance(blocker, dict)}
    if args.blocker_id not in blocker_ids:
        raise PipelineError(f"{args.blocker_id} is not attached to task {args.task_id}")
    evidence_path = path_within_root(args.evidence)
    if evidence_path is None:
        raise PipelineError("blocker evidence path escapes repo root")
    if not evidence_path.exists():
        raise PipelineError(f"blocker evidence does not exist: {args.evidence}")
    state.setdefault("blocker_resolutions", []).append(
        {
            "blocker_id": args.blocker_id,
            "evidence": args.evidence,
            "by": args.by,
            "resolved_at": now_iso(),
        }
    )
    if state.get("status") == "WAITING" and (state.get("blocker") or {}).get("reason_code") == "OPEN_BLOCKER":
        state["blocker"] = None
        state["resume_condition"] = None
        state["current_stage"] = first_missing_stage(state)
        state["status"] = "RUNNING" if state.get("verdicts") else "QUEUED"
    errors = validate_state(contract, state)
    if errors:
        raise PipelineError("; ".join(errors))
    save_state(state, {"type": "BLOCKER_RESOLVED", "blocker_id": args.blocker_id, "evidence": args.evidence, "by": args.by})
    print(json.dumps({"task_id": args.task_id, "blocker_id": args.blocker_id, "status": state["status"]}, ensure_ascii=False))
    return 0


def command_lock_acquire(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    resources = task_resources(state, args.resources)
    with controller_store_lock():
        lock_store = load_locks()
        expired = expire_locks(lock_store)
        conflicts = [
            resource for resource in resources
            if resource in lock_store["locks"]
            and (lock_store["locks"][resource]["task_id"] != args.task_id or lock_store["locks"][resource]["agent"] != args.agent)
        ]
        if conflicts:
            for event in expired:
                append_lock_audit(event)
            write_json(LOCK_STORE_PATH, lock_store)
            raise PipelineError(f"resource lease conflict: {', '.join(conflicts)}")
        issued: dict[str, int] = {}
        for resource in resources:
            existing = lock_store["locks"].get(resource)
            if existing:
                issued[resource] = existing["fencing_token"]
                continue
            token = lock_store["next_fencing_token"]
            lock_store["next_fencing_token"] = token + 1
            lock = {
                "task_id": args.task_id,
                "agent": args.agent,
                "fencing_token": token,
                "lease_until": lease_until(args),
            }
            lock_store["locks"][resource] = lock
            issued[resource] = token
            append_lock_audit({"type": "LOCK_ACQUIRED", "resource": resource, **lock})
        for event in expired:
            append_lock_audit(event)
        write_json(LOCK_STORE_PATH, lock_store)
    append_journal(args.task_id, {"type": "RESOURCE_LOCKS_ACQUIRED", "resources": resources, "agent": args.agent, "fencing_tokens": issued})
    print(json.dumps({"task_id": args.task_id, "resources": resources, "fencing_tokens": issued}, ensure_ascii=False))
    return 0


def command_lock_renew(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    resources = task_resources(state, args.resources)
    with controller_store_lock():
        lock_store = load_locks()
        expired = expire_locks(lock_store)
        for event in expired:
            append_lock_audit(event)
        if expired:
            write_json(LOCK_STORE_PATH, lock_store)
        for resource in resources:
            active_lock(lock_store, resource, args.task_id, args.agent, args.fencing_token)
        new_lease_until = lease_until(args)
        for resource in resources:
            lock_store["locks"][resource]["lease_until"] = new_lease_until
            append_lock_audit({"type": "LOCK_RENEWED", "resource": resource, **lock_store["locks"][resource]})
        write_json(LOCK_STORE_PATH, lock_store)
    append_journal(args.task_id, {"type": "RESOURCE_LOCKS_RENEWED", "resources": resources, "agent": args.agent, "fencing_token": args.fencing_token})
    print(json.dumps({"task_id": args.task_id, "resources": resources, "fencing_token": args.fencing_token, "lease_until": new_lease_until}, ensure_ascii=False))
    return 0


def command_lock_release(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    resources = task_resources(state, args.resources)
    with controller_store_lock():
        lock_store = load_locks()
        expired = expire_locks(lock_store)
        for event in expired:
            append_lock_audit(event)
        if expired:
            write_json(LOCK_STORE_PATH, lock_store)
        for resource in resources:
            active_lock(lock_store, resource, args.task_id, args.agent, args.fencing_token)
        for resource in resources:
            lock = lock_store["locks"].pop(resource)
            append_lock_audit({"type": "LOCK_RELEASED", "resource": resource, **lock})
        write_json(LOCK_STORE_PATH, lock_store)
    append_journal(args.task_id, {"type": "RESOURCE_LOCKS_RELEASED", "resources": resources, "agent": args.agent, "fencing_token": args.fencing_token})
    print(json.dumps({"task_id": args.task_id, "released": resources, "fencing_token": args.fencing_token}, ensure_ascii=False))
    return 0


def command_worker_claim(args: argparse.Namespace) -> int:
    state = load_state(args.task_id)
    if args.queue != state["celery_queue"]:
        raise PipelineError(f"worker queue {args.queue} is not assigned to task {args.task_id}")
    resource = args.resource or f"queue:{args.queue}"
    if resource not in state.get("resources", []):
        raise PipelineError(f"worker resource {resource} is not declared for task {args.task_id}")
    with controller_store_lock():
        lock_store = load_locks()
        expired = expire_locks(lock_store)
        for event in expired:
            append_lock_audit(event)
        if expired:
            write_json(LOCK_STORE_PATH, lock_store)
        active_lock(lock_store, resource, args.task_id, args.agent, args.fencing_token)
        write_json(LOCK_STORE_PATH, lock_store)
    append_journal(args.task_id, {"type": "WORKER_QUEUE_CLAIMED", "queue": args.queue, "resource": resource, "agent": args.agent, "fencing_token": args.fencing_token})
    print(json.dumps({"task_id": args.task_id, "queue": args.queue, "resource": resource, "fencing_token": args.fencing_token}, ensure_ascii=False))
    return 0


def parse_backlog_ids(raw: str) -> list[str]:
    ids = [part.strip() for part in raw.split(",") if part.strip()]
    if not ids:
        raise PipelineError("start-wave requires at least one backlog id")
    if len(ids) != len(set(ids)):
        raise PipelineError("start-wave backlog ids contain duplicates")
    return ids


def wave_id_for(backlog_ids: list[str]) -> str:
    raw = json.dumps(backlog_ids, ensure_ascii=False, separators=(",", ":")).encode()
    return "wave-" + hashlib.sha256(raw).hexdigest()[:12]


def backlog_task_id(backlog_id: str, prefix: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", backlog_id).strip("-")
    if not clean:
        raise PipelineError(f"cannot derive task id from backlog id {backlog_id}")
    return f"{prefix}{clean}" if prefix else clean


def validate_wave_selection(items: dict[str, dict[str, Any]], backlog_ids: list[str], allow_missing_dependencies: bool) -> list[dict[str, Any]]:
    unknown = [backlog_id for backlog_id in backlog_ids if backlog_id not in items]
    if unknown:
        raise PipelineError(f"unknown backlog ids: {', '.join(unknown)}")
    selected = {backlog_id for backlog_id in backlog_ids}
    selected_items = [items[backlog_id] for backlog_id in backlog_ids]
    if not allow_missing_dependencies:
        missing_dependencies = sorted(
            {
                dependency
                for item in selected_items
                for dependency in item.get("dependencies", [])
                if dependency not in selected
            }
        )
        if missing_dependencies:
            raise PipelineError(f"wave is missing dependencies: {', '.join(missing_dependencies)}")
    return selected_items


def state_from_backlog_item(
    contract: dict[str, Any],
    item: dict[str, Any],
    task_id: str,
    wave_id: str,
    owner: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    traits = item_traits(item)
    risk_level = item_risk(item)
    required = required_stages(contract, traits, risk_level)
    lease_until = datetime.now(UTC) + timedelta(minutes=args.lease_minutes)
    resources = sorted({f"backlog:{item['id'].lower()}", "file:docs/product/backlog-queue.json"})
    if args.resources:
        resources = sorted(set(resources + parse_resources(args.resources)))
    return {
        "task_id": task_id,
        "backlog_item_id": item["id"],
        "backlog_title": item["title"],
        "backlog_item": copy.deepcopy(item),
        "source_hash": source_hash(json.dumps(item, ensure_ascii=False, sort_keys=True)),
        "source_excerpt": item["title"][:240],
        "pipeline_version": contract["pipeline_version"],
        "pipeline_hash": contract_hash(),
        "traits": traits,
        "risk_level": risk_level,
        "required_stages": required,
        "current_stage": "S01",
        "status": "QUEUED",
        "base_sha": args.base_sha or current_sha(),
        "branch": args.branch or current_branch(),
        "worktree": str(ROOT),
        "environment_id": args.environment_id,
        "database": args.database,
        "redis_namespace": args.redis_namespace,
        "celery_queue": args.celery_queue or f"{wave_id}-{item['id']}".lower(),
        "emulator_namespace": args.emulator_namespace,
        "resources": resources,
        "owner_agent": owner,
        "attempt": 1,
        "lease_until": lease_until.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "heartbeat_at": now_iso(),
        "last_valid_receipt": None,
        "blocker": None,
        "resume_condition": None,
        "verdicts": {},
        "commits": [],
        "wave_id": wave_id,
        "budget_enforced": True,
        "budget_usage": {"input_tokens": 0, "output_tokens": 0, "estimated_usd": 0.0},
        "budget_usage_receipts": [],
        "blocked_by": active_blockers_for_backlog(item["id"]),
        "blocker_resolutions": [],
    }


def command_start_wave(args: argparse.Namespace) -> int:
    if not args.owner_approved_by:
        raise PipelineError("start-wave requires --owner-approved-by")
    contract = load_contract()
    backlog_ids = parse_backlog_ids(args.backlog_ids)
    items = backlog_items_by_id()
    selected_items = validate_wave_selection(items, backlog_ids, args.allow_missing_dependencies)
    wave_id = args.wave_id or wave_id_for(backlog_ids)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", wave_id):
        raise PipelineError("wave-id may contain only letters, digits, underscore and hyphen")

    planned: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    for item in selected_items:
        task_id = backlog_task_id(item["id"], args.task_prefix)
        state_path, _, _ = task_paths(task_id)
        if state_path.exists() and not args.skip_existing:
            raise PipelineError(f"task already exists: {task_id}")
        state = state_from_backlog_item(contract, item, task_id, wave_id, args.owner_approved_by, args)
        states.append(state)
        planned.append(
            {
                "task_id": task_id,
                "backlog_item_id": item["id"],
                "title": item["title"],
                "readiness": item["readiness"],
                "traits": state["traits"],
                "risk_level": state["risk_level"],
                "required_stages": state["required_stages"],
                "blocked_by": [blocker["id"] for blocker in state.get("blocked_by", [])],
            }
        )

    manifest = {
        "wave_id": wave_id,
        "created_at": now_iso(),
        "owner_approved_by": args.owner_approved_by,
        "base_sha": args.base_sha or current_sha(),
        "backlog_ids": backlog_ids,
        "budget_policy": "pipeline/budget-policy.yml",
        "tasks": planned,
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **manifest}, ensure_ascii=False, indent=2))
        return 0

    with controller_store_lock():
        for state in states:
            state_path, _, _ = task_paths(state["task_id"])
            if state_path.exists() and args.skip_existing:
                continue
            save_state(state, {"type": "TASK_OPENED_FROM_BACKLOG_WAVE", "wave_id": wave_id, "backlog_item_id": state["backlog_item_id"]})
        write_json(WAVE_STORE_ROOT / f"{wave_id}.json", manifest)
        write_json(WAVE_SNAPSHOT_ROOT / f"{wave_id}.json", {**manifest, "_snapshot_note": "Read-only Git snapshot; controller state lives in .pipeline-state/."})
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
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
    open_p.add_argument("--resources", default="", help="comma-separated canonical resource ids, e.g. file:pipeline/controller.py,queue:task-1")
    open_p.add_argument("--emergency-scope-receipt")
    open_p.add_argument("--emergency-debt-id")
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
    advance_p.add_argument("--executor", choices=["codex", "claude", "cursor"], default="codex")
    advance_p.add_argument("--model")
    advance_p.add_argument("--tier", choices=["cheap", "moderate", "expensive"])
    advance_p.add_argument("--input-tokens", type=int)
    advance_p.add_argument("--output-tokens", type=int)
    advance_p.add_argument("--estimated-usd", type=float)
    advance_p.set_defaults(func=command_advance)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--task-id")
    validate_p.set_defaults(func=command_validate)

    status_p = sub.add_parser("status")
    status_p.add_argument("--task-id", required=True)
    status_p.set_defaults(func=command_status)

    report_p = sub.add_parser("report")
    report_p.add_argument("--format", choices=["text", "json"], default="text")
    report_p.set_defaults(func=command_report)

    hold_p = sub.add_parser("hold")
    hold_p.add_argument("--task-id", required=True)
    hold_p.add_argument("--blocker-type", choices=BLOCKER_TYPES, required=True)
    hold_p.add_argument("--reason-code", required=True)
    hold_p.add_argument("--reason", required=True)
    hold_p.add_argument("--resume-condition", required=True)
    hold_p.add_argument("--resume-stage")
    hold_p.add_argument("--owner", default="owner")
    hold_p.set_defaults(func=command_hold)

    resume_p = sub.add_parser("resume")
    resume_p.add_argument("--task-id", required=True)
    resume_p.add_argument("--by", default="owner")
    resume_p.set_defaults(func=command_resume)

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

    resolve_blocker_p = sub.add_parser("resolve-blocker")
    resolve_blocker_p.add_argument("--task-id", required=True)
    resolve_blocker_p.add_argument("--blocker-id", required=True)
    resolve_blocker_p.add_argument("--evidence", required=True)
    resolve_blocker_p.add_argument("--by", required=True)
    resolve_blocker_p.set_defaults(func=command_resolve_blocker)

    start_wave_p = sub.add_parser("start-wave")
    start_wave_p.add_argument("--backlog-ids", required=True, help="comma-separated backlog IDs from docs/product/backlog-queue.json")
    start_wave_p.add_argument("--owner-approved-by", required=True)
    start_wave_p.add_argument("--wave-id")
    start_wave_p.add_argument("--task-prefix", default="")
    start_wave_p.add_argument("--base-sha")
    start_wave_p.add_argument("--branch")
    start_wave_p.add_argument("--environment-id", default="local")
    start_wave_p.add_argument("--database", default="local")
    start_wave_p.add_argument("--redis-namespace", default="local")
    start_wave_p.add_argument("--celery-queue")
    start_wave_p.add_argument("--emulator-namespace", default="local")
    start_wave_p.add_argument("--resources", default="", help="comma-separated extra canonical resource ids")
    start_wave_p.add_argument("--lease-minutes", type=int, default=60)
    start_wave_p.add_argument("--allow-missing-dependencies", action="store_true")
    start_wave_p.add_argument("--skip-existing", action="store_true")
    start_wave_p.add_argument("--dry-run", action="store_true")
    start_wave_p.set_defaults(func=command_start_wave)

    def add_lock_arguments(lock_parser: argparse.ArgumentParser, *, include_lease: bool) -> None:
        lock_parser.add_argument("--task-id", required=True)
        lock_parser.add_argument("--agent", required=True)
        lock_parser.add_argument("--resources", help="comma-separated subset of resources declared when the task opened")
        if include_lease:
            lock_parser.add_argument("--lease-minutes", type=int, default=60)
            lock_parser.add_argument("--lease-seconds", type=int)

    lock_acquire_p = sub.add_parser("lock-acquire")
    add_lock_arguments(lock_acquire_p, include_lease=True)
    lock_acquire_p.set_defaults(func=command_lock_acquire)

    lock_renew_p = sub.add_parser("lock-renew")
    add_lock_arguments(lock_renew_p, include_lease=True)
    lock_renew_p.add_argument("--fencing-token", type=int, required=True)
    lock_renew_p.set_defaults(func=command_lock_renew)

    lock_release_p = sub.add_parser("lock-release")
    add_lock_arguments(lock_release_p, include_lease=False)
    lock_release_p.add_argument("--fencing-token", type=int, required=True)
    lock_release_p.set_defaults(func=command_lock_release)

    worker_claim_p = sub.add_parser("worker-claim")
    worker_claim_p.add_argument("--task-id", required=True)
    worker_claim_p.add_argument("--queue", required=True)
    worker_claim_p.add_argument("--agent", required=True)
    worker_claim_p.add_argument("--fencing-token", type=int, required=True)
    worker_claim_p.add_argument("--resource")
    worker_claim_p.set_defaults(func=command_worker_claim)

    case_result_p = sub.add_parser("case-result")
    case_result_p.add_argument("--task-id", required=True)
    case_result_p.add_argument("--case-id", required=True)
    case_result_p.add_argument("--tier", choices=["GOLD", "SILVER", "QUESTION"], required=True)
    case_result_p.add_argument("--status", choices=["green", "red"], required=True)
    case_result_p.add_argument("--mutates-state", action="store_true")
    case_result_p.add_argument("--isolation", choices=["none", "fresh_snapshot", "transaction"], default="none")
    case_result_p.add_argument("--ordered-journey")
    case_result_p.set_defaults(func=command_case_result)

    expectation_rewrite_p = sub.add_parser("expectation-rewrite")
    expectation_rewrite_p.add_argument("--task-id", required=True)
    expectation_rewrite_p.add_argument("--case-id", required=True)
    expectation_rewrite_p.add_argument("--oracle")
    expectation_rewrite_p.add_argument("--oracle-version")
    expectation_rewrite_p.set_defaults(func=command_expectation_rewrite)

    failure_p = sub.add_parser("failure")
    failure_p.add_argument("--task-id", required=True)
    failure_p.add_argument("--finding", required=True)
    failure_p.add_argument("--details", default="pipeline failure routed by controller")
    failure_p.add_argument("--owner", default="pipeline-controller")
    failure_p.set_defaults(func=command_failure)

    release_proof_p = sub.add_parser("record-release-proof")
    release_proof_p.add_argument("--task-id", required=True)
    release_proof_p.add_argument("--commit")
    release_proof_p.add_argument("--pushed-ref")
    release_proof_p.add_argument("--check")
    release_proof_p.set_defaults(func=command_record_release_proof)

    external_effect_p = sub.add_parser("external-effect")
    external_effect_p.add_argument("--task-id", required=True)
    external_effect_p.add_argument("--effect", required=True)
    external_effect_p.add_argument("--idempotency-key", required=True)
    external_effect_p.set_defaults(func=command_external_effect)

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
