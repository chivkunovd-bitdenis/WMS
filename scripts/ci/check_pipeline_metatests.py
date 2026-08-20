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
    require("command_hold" in controller, "controller must support owner hold before execution", errors)
    require("command_resume" in controller, "controller must support explicit resume after owner hold", errors)
    require('state.get("status") == "WAITING"' in controller, "controller must block advance while task is WAITING", errors)
    require("BLOCKER_TYPES" in controller, "controller must bind hold choices to pipeline blocker types", errors)
    for blocker_type in contract["blocker_types"]:
        require(f'"{blocker_type}"' in controller, f"controller blocker choices must include {blocker_type}", errors)
    require((ROOT / "scripts" / "pipeline" / "dispatch.py").exists(), "dispatch prompt writer must exist", errors)
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
        hold_result = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "hold",
                "--task-id",
                "TASK-METATEST",
                "--blocker-type",
                "OWNER_INPUT",
                "--reason-code",
                "METATEST_OWNER_HOLD",
                "--reason",
                "metatest hold",
                "--resume-condition",
                "metatest resume",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(hold_result.returncode == 0, f"pipeline hold failed: {hold_result.stderr}", errors)
        blocked_advance = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "advance",
                "--task-id",
                "TASK-METATEST",
                "--stage",
                "S01",
                "--verdict",
                "DISPATCH_READY",
                "--role",
                "pipeline-dispatcher",
                "--agent",
                "metatest",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(blocked_advance.returncode != 0, "WAITING task must reject advance", errors)
        resume_result = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "resume",
                "--task-id",
                "TASK-METATEST",
                "--by",
                "metatest",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(resume_result.returncode == 0, f"pipeline resume failed: {resume_result.stderr}", errors)
        if resume_result.returncode == 0:
            resumed = json.loads(resume_result.stdout)
            require(resumed["status"] == "QUEUED", "resume before verdicts must return task to QUEUED", errors)
        wrong_role_advance = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "advance",
                "--task-id",
                "TASK-METATEST",
                "--stage",
                "S01",
                "--verdict",
                "TASK_INTAKE_READY",
                "--role",
                "pipeline-dev",
                "--agent",
                "metatest",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(wrong_role_advance.returncode != 0, "stage must reject a mismatched role", errors)
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
