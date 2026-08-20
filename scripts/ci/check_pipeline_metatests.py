#!/usr/bin/env python3
"""Contract-level metatests for the first Pipeline v2 implementation slice."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load_contract() -> dict:
    return json.loads(read("pipeline/pipeline.yml"))


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    contract = load_contract()
    stage_order = [stage["id"] for stage in contract["stages"]]

    require(contract["status"] == "IMPLEMENTATION_IN_PROGRESS", "pipeline must be in implementation mode", errors)
    require(contract["activation"]["implementation_approved"] is True, "implementation approval must be recorded", errors)
    require(contract["activation"]["activation_approved"] is False, "activation must remain false", errors)

    # MT01: Dev workspace cannot be before Product approval in the declared order.
    require(stage_order.index("S16") < stage_order.index("S17"), "S16 must precede S17", errors)

    # MT03: pipeline.yml is explicitly control-plane protected.
    require("pipeline/**" in contract["control_plane_protected_paths"], "pipeline/** must be protected", errors)

    # MT24 and MT31: controller refuses DONE while not ACTIVE, and no-traffic is not DONE.
    controller = read("pipeline/controller.py")
    require('contract.get("status") != "ACTIVE"' in controller, "controller must forbid DONE before ACTIVE", errors)
    require("ROLE_BY_STAGE" in controller, "controller must map stages to agent roles", errors)
    require("command_packet" in controller, "controller must produce agent handoff packets", errors)
    require('"MONITORING_NO_TRAFFIC"' in read("pipeline/pipeline.yml"), "MONITORING_NO_TRAFFIC verdict must be declared", errors)

    # MT33: entrypoint inventory is guarded by the contract checker.
    checker = read("scripts/ci/check_pipeline_contract.py")
    require("STATUS_POINTER_FILES" in checker, "contract checker must validate entrypoint pointers", errors)

    # MT38: every trait declares all machine dimensions.
    for name, trait in contract["traits"].items():
        for key in ("required_stages", "required_receipts", "case_dimensions", "acceptance_surfaces"):
            require(bool(trait.get(key)), f"trait {name} must declare {key}", errors)

    deploy_workflow = read(".github/workflows/deploy.yml")
    prod_update = read("scripts/deploy/prod-update.sh")
    require("release_sha" in deploy_workflow, "deploy workflow must require release_sha input", errors)
    require("branches: [main]" not in deploy_workflow, "deploy workflow must not auto-deploy push to main", errors)
    require("git checkout main" not in deploy_workflow + prod_update, "deploy must not checkout main", errors)
    require("WMS_RELEASE_SHA" in prod_update, "prod-update must require WMS_RELEASE_SHA", errors)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline/run.py",
            "open",
            "--task-id",
            "TASK-METATEST",
            "--source",
            "metatest",
            "--traits",
            "pipeline_change",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(result.returncode == 0, f"pipeline open failed: {result.stderr}", errors)
    if result.returncode == 0:
        opened = json.loads(result.stdout)
        require("S16" in opened["required_stages"], "opened task must require Product before dev", errors)
        require("S20" in opened["required_stages"], "opened task must require Code Review", errors)
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / "TASK-METATEST", ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / "TASK-METATEST", ignore_errors=True)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline metatests ok: implementation slice is executable, activation still closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
