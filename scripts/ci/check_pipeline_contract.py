#!/usr/bin/env python3
"""Validate the WMS pipeline v2 contract without third-party dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = ROOT / "pipeline" / "pipeline.yml"
PIPELINE_SCHEMA_PATH = ROOT / "pipeline" / "pipeline.schema.json"

EXPECTED_STAGE_IDS = [
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

EXPECTED_TRAITS = {
    "bug",
    "ui_change",
    "process_change",
    "external_contract",
    "new_domain",
    "new_module",
    "database_change",
    "background_worker",
    "print",
    "mobile_contract",
    "tenant_sensitive",
    "release_change",
    "emergency",
    "pipeline_change",
}

EXPECTED_LIFECYCLE_STATUSES = {
    "QUEUED",
    "RUNNING",
    "WAITING",
    "REWORK",
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

EXPECTED_BLOCKER_TYPES = {
    "OWNER_INPUT",
    "ENV",
    "FIXTURE",
    "EXTERNAL",
    "ORACLE_CONFLICT",
    "BASELINE",
    "ACCESS",
    "SECURITY",
    "RELEASE",
}

STATUS_POINTER_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".github/pull_request_template.md",
    ".dev/PROCESS.md",
    ".dev/.dev/PROCESS.md",
    ".cursor/skills/feature-test-coverage/SKILL.md",
    "docs/CURSOR_PIPELINE_REFERENCE_RU.md",
    "docs/WMS_FEATURE_GATE_PROTOCOL_RU.md",
    "docs/WMS_PRODUCT_AGENT_RU.md",
    "docs/process/PIPELINE-ADDITIONS-RU.md",
    "docs/process/PIPELINE-DESIGN-RU.md",
    "docs/process/TASK-PIPELINE-ARCHITECT-RU.md",
]

SUPERSEDED_POINTER_FILES = {
    ".dev/PROCESS.md",
    ".dev/.dev/PROCESS.md",
    "docs/CURSOR_PIPELINE_REFERENCE_RU.md",
    "docs/WMS_FEATURE_GATE_PROTOCOL_RU.md",
    "docs/WMS_PRODUCT_AGENT_RU.md",
    "docs/process/PIPELINE-ADDITIONS-RU.md",
    "docs/process/PIPELINE-DESIGN-RU.md",
    "docs/process/TASK-PIPELINE-ARCHITECT-RU.md",
}

REQUIRED_SCHEMA_FILES = [
    "pipeline/pipeline.schema.json",
    "pipeline/task-state.schema.json",
    "pipeline/receipt.schema.json",
    "pipeline/evidence.schema.json",
    "pipeline/case.schema.json",
    "pipeline/incident.schema.json",
]


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AssertionError(f"missing file: {path.relative_to(ROOT)}") from None
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{path.relative_to(ROOT)} is not valid JSON/YAML-subset: {exc}") from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def get_owner_line_state(source_text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", source_text, flags=re.MULTILINE)
    if not match:
        return "missing"
    value = match.group(1).strip()
    if value in {"<дата или нет>", "нет", "<date or no>", "no"}:
        return "not_approved"
    return "approved"


def validate_contract(data: dict[str, Any], *, strict_activation: bool) -> list[str]:
    errors: list[str] = []

    require(data.get("pipeline_version") == "2.0", "pipeline_version must be 2.0", errors)
    require(
        data.get("status") in {"TARGET_PIPELINE_NOT_ENFORCED", "IMPLEMENTATION_IN_PROGRESS", "ACTIVE"},
        "status must be TARGET_PIPELINE_NOT_ENFORCED, IMPLEMENTATION_IN_PROGRESS or ACTIVE",
        errors,
    )
    require(
        data.get("canonical_source") == "docs/process/PIPELINE-RU.md",
        "canonical_source must point to docs/process/PIPELINE-RU.md",
        errors,
    )

    source_path = ROOT / str(data.get("canonical_source", ""))
    if source_path.exists():
        actual_hash = sha256_file(source_path)
        require(
            data.get("canonical_source_sha256") == actual_hash,
            "canonical_source_sha256 is stale; update pipeline/pipeline.yml after editing PIPELINE-RU.md",
            errors,
        )
        source_text = source_path.read_text(encoding="utf-8")
        if data.get("status") == "ACTIVE":
            require(
                "Статус: **ACTIVE" in source_text,
                "ACTIVE machine contract requires ACTIVE status in PIPELINE-RU.md header",
                errors,
            )
            require(
                "ещё не активирована" not in source_text,
                "ACTIVE PIPELINE-RU.md cannot claim that the pipeline is not activated",
                errors,
            )
        activation_line = get_owner_line_state(source_text, "PIPELINE_ACTIVATION_APPROVED")
        implementation_line = get_owner_line_state(source_text, "PIPELINE_IMPLEMENTATION_APPROVED")
        activation = data.get("activation", {})
        if implementation_line == "approved":
            require(
                activation.get("implementation_approved") is True,
                "PIPELINE_IMPLEMENTATION_APPROVED is set in docs but activation.implementation_approved is false",
                errors,
            )
        if activation_line == "approved":
            require(
                activation.get("activation_approved") is True and data.get("status") == "ACTIVE",
                "PIPELINE_ACTIVATION_APPROVED is set in docs but pipeline status is not ACTIVE",
                errors,
            )
    else:
        errors.append("canonical_source file is missing")

    for schema_path in REQUIRED_SCHEMA_FILES:
        schema = load_json_file(ROOT / schema_path)
        require(schema.get("$schema"), f"{schema_path} must declare $schema", errors)
        require(schema.get("title"), f"{schema_path} must declare title", errors)
        require(schema.get("type") == "object", f"{schema_path} must describe an object", errors)

    stage_ids = [stage.get("id") for stage in data.get("stages", []) if isinstance(stage, dict)]
    require(stage_ids == EXPECTED_STAGE_IDS, "stages must match PIPELINE-RU.md section 19.1 order", errors)
    for stage in data.get("stages", []):
        if not isinstance(stage, dict):
            errors.append("each stage must be an object")
            continue
        require(bool(stage.get("name")), f"{stage.get('id', '<unknown>')} is missing name", errors)
        require(bool(stage.get("enabled_when")), f"{stage.get('id', '<unknown>')} is missing enabled_when", errors)
        require(
            bool(stage.get("pass_verdicts")),
            f"{stage.get('id', '<unknown>')} must declare pass_verdicts",
            errors,
        )
        require(bool(stage.get("next_on_pass")), f"{stage.get('id', '<unknown>')} is missing next_on_pass", errors)

    trait_names = set(data.get("traits", {}).keys())
    require(trait_names == EXPECTED_TRAITS, "traits must match PIPELINE-RU.md section 9", errors)
    for trait_name, trait in data.get("traits", {}).items():
        if not isinstance(trait, dict):
            errors.append(f"trait {trait_name} must be an object")
            continue
        for field in ("required_stages", "required_receipts", "case_dimensions", "acceptance_surfaces"):
            require(bool(trait.get(field)), f"trait {trait_name} must declare {field}", errors)

    require(
        set(data.get("lifecycle_statuses", [])) == EXPECTED_LIFECYCLE_STATUSES,
        "lifecycle_statuses must match PIPELINE-RU.md section 7",
        errors,
    )
    require(
        set(data.get("blocker_types", [])) == EXPECTED_BLOCKER_TYPES,
        "blocker_types must match PIPELINE-RU.md section 7",
        errors,
    )

    metatest_ids = [item.get("id") for item in data.get("required_metatests", []) if isinstance(item, dict)]
    expected_metatest_ids = [f"MT{i:02d}" for i in range(1, 41)]
    require(metatest_ids == expected_metatest_ids, "required_metatests must declare MT01..MT40 in order", errors)
    for item in data.get("required_metatests", []):
        if not isinstance(item, dict):
            errors.append("each required_metatest must be an object")
            continue
        require(bool(item.get("title")), f"{item.get('id', '<unknown>')} is missing title", errors)
        require(
            item.get("status") in {"declared_pending_controller", "automated_green"},
            f"{item.get('id', '<unknown>')} has invalid status",
            errors,
        )

    for rel_path in STATUS_POINTER_FILES:
        text = (ROOT / rel_path).read_text(encoding="utf-8")
        require(
            "PIPELINE-RU.md" in text and "pipeline/pipeline.yml" in text,
            f"{rel_path} must point to docs/process/PIPELINE-RU.md and pipeline/pipeline.yml",
            errors,
        )
        if data.get("status") == "ACTIVE":
            require("ACTIVE" in text, f"{rel_path} must declare ACTIVE pipeline status", errors)
        if rel_path in SUPERSEDED_POINTER_FILES:
            require(
                len(text.splitlines()) <= 30,
                f"{rel_path} must be a short pointer, not a competing process",
                errors,
            )

    active = data.get("status") == "ACTIVE" or bool(data.get("activation", {}).get("activation_approved"))
    if strict_activation or active:
        pending = [
            item["id"]
            for item in data.get("required_metatests", [])
            if isinstance(item, dict) and item.get("status") != "automated_green"
        ]
        require(not pending, "ACTIVE pipeline requires all metatests automated_green", errors)
        require(
            not data.get("activation_blockers"),
            "ACTIVE pipeline cannot keep activation_blockers",
            errors,
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-activation",
        action="store_true",
        help="fail unless the contract is ready for PIPELINE_ACTIVATION_APPROVED",
    )
    args = parser.parse_args()

    data = load_json_file(PIPELINE_PATH)
    load_json_file(PIPELINE_SCHEMA_PATH)
    errors = validate_contract(data, strict_activation=args.strict_activation)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    status = data["status"]
    blockers = data.get("activation_blockers", [])
    metatests = data.get("required_metatests", [])
    pending = sum(1 for item in metatests if item.get("status") != "automated_green")
    print(f"pipeline contract ok: version={data['pipeline_version']} status={status}")
    if status != "ACTIVE":
        print(
            "activation remains blocked: "
            f"{len(blockers)} blockers listed, {pending}/{len(metatests)} metatests pending"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
