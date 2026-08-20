#!/usr/bin/env python3
"""Contract-level metatests for the first Pipeline v2 implementation slice."""

from __future__ import annotations

import fcntl
import json
import os
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


def pipeline_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/pipeline/run.py", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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


def cleanup_task(task_id: str) -> None:
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / task_id, ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / task_id, ignore_errors=True)
    shutil.rmtree(ROOT / "docs" / "evidence" / task_id, ignore_errors=True)


def cleanup_wave(wave_id: str) -> None:
    (ROOT / ".pipeline-state" / "waves" / f"{wave_id}.json").unlink(missing_ok=True)
    (ROOT / "tasks" / "_waves" / f"{wave_id}.json").unlink(missing_ok=True)


def advance_until(
    task_id: str,
    target_stage: str,
    pass_verdicts: dict[str, str],
    errors: list[str],
    *,
    agent_by_stage: dict[str, str] | None = None,
) -> dict | None:
    agent_by_stage = agent_by_stage or {}
    for _ in range(40):
        status = pipeline_command("status", "--task-id", task_id)
        if status.returncode != 0:
            errors.append(f"{task_id}: cannot read state: {status.stderr}")
            return None
        state = json.loads(status.stdout)
        current = state["current_stage"]
        if current == target_stage:
            return state
        if current not in state["required_stages"]:
            errors.append(f"{task_id}: current stage {current} is outside required stages")
            return state
        if target_stage not in state["required_stages"]:
            errors.append(f"{task_id}: target stage {target_stage} is not required")
            return state
        if state["required_stages"].index(current) > state["required_stages"].index(target_stage):
            errors.append(f"{task_id}: passed target stage {target_stage}; now at {current}")
            return state
        advance = pipeline_command(
            "advance",
            "--task-id", task_id,
            "--stage", current,
            "--verdict", pass_verdicts[current],
            "--role", ROLE_BY_STAGE[current],
            "--agent", agent_by_stage.get(current, f"metatest-{current.lower()}"),
        )
        if advance.returncode != 0:
            errors.append(f"{task_id}: advance {current} failed: {advance.stderr}")
            return None
    errors.append(f"{task_id}: did not reach {target_stage}")
    return None


def main() -> int:
    errors: list[str] = []
    contract = load_contract()
    stage_order = [stage["id"] for stage in contract["stages"]]
    pass_verdicts = {stage["id"]: stage["pass_verdicts"][0] for stage in contract["stages"]}
    traits = contract["traits"]

    require(contract["status"] == "IMPLEMENTATION_IN_PROGRESS", "pipeline must be in implementation mode", errors)
    require(contract["activation"]["implementation_approved"] is True, "implementation approval must be recorded", errors)
    require(contract["activation"]["activation_approved"] is False, "activation must remain false", errors)

    # MT01: Dev workspace cannot be before Product approval in the declared order.
    require(stage_order.index("S16") < stage_order.index("S17"), "S16 must precede S17", errors)

    # MT02/MT03: control-plane paths are protected and require explicit authorization.
    require("pipeline/**" in contract["control_plane_protected_paths"], "pipeline/** must be protected", errors)
    require(
        "scripts/ci/check_pipeline_scope_guard.py" in contract["control_plane_protected_paths"],
        "pipeline scope guard must protect itself",
        errors,
    )
    scope_guard = ROOT / "scripts" / "ci" / "check_pipeline_scope_guard.py"
    require(scope_guard.exists(), "pipeline scope guard must exist", errors)
    if scope_guard.exists():
        ordinary_change = subprocess.run(
            [sys.executable, str(scope_guard), "--changed-path", "pipeline/pipeline.yml"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(ordinary_change.returncode == 1, "ordinary task must not modify pipeline.yml", errors)
        workflow_change = subprocess.run(
            [sys.executable, str(scope_guard), "--changed-path", ".github/workflows/ci.yml"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(workflow_change.returncode == 1, "ordinary task must not modify workflows", errors)
        allowed_by_env = subprocess.run(
            [sys.executable, str(scope_guard), "--changed-path", "scripts/deploy/prod-update.sh"],
            cwd=ROOT, env={**os.environ, "PIPELINE_SCOPE_ALLOW": "pipeline_change"}, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(allowed_by_env.returncode == 0, "pipeline_change env must authorize protected path", errors)
        allowed_by_label = subprocess.run(
            [sys.executable, str(scope_guard), "--changed-path", "tasks/TASK-42/state.json"],
            cwd=ROOT, env={**os.environ, "PR_LABELS": "control-plane"}, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(allowed_by_label.returncode == 0, "control-plane label must authorize protected path", errors)
        allowed_by_marker = subprocess.run(
            [sys.executable, str(scope_guard), "--changed-path", "pipeline/pipeline.yml"],
            cwd=ROOT, env={**os.environ, "PR_BODY": "PIPELINE_SCOPE_ALLOW: pipeline_change"}, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(allowed_by_marker.returncode == 0, "pipeline change marker must authorize protected path", errors)
    ci_workflow = read(".github/workflows/ci.yml")
    require("check_pipeline_scope_guard.py" in ci_workflow, "CI must run pipeline scope guard", errors)
    require("check_pipeline_model_policy.py" in ci_workflow, "CI must run pipeline model policy check", errors)
    require("check_pipeline_budget_policy.py" in ci_workflow, "CI must run pipeline budget policy check", errors)
    require("check_backlog_queue.py" in ci_workflow, "CI must run backlog queue check", errors)
    require("check_blockers_registry.py" in ci_workflow, "CI must run blocker registry check", errors)
    require("check_pipeline_policy_metatests.py" in ci_workflow, "CI must run pipeline policy metatests", errors)
    require("check_pipeline_replay_metatests.py" in ci_workflow, "CI must run pipeline replay metatests", errors)
    require("scripts/ui/ui_guard.py" in ci_workflow, "CI must run UI canon ratchet for product changes", errors)
    require("scripts/ui/ui_kit_usage_guard.py" in ci_workflow, "CI must run W12 ui-kit usage guard for product changes", errors)
    model_policy_check = subprocess.run(
        [sys.executable, "scripts/ci/check_pipeline_model_policy.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(model_policy_check.returncode == 0, f"pipeline model policy check failed: {model_policy_check.stderr}", errors)
    budget_policy_check = subprocess.run(
        [sys.executable, "scripts/ci/check_pipeline_budget_policy.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(budget_policy_check.returncode == 0, f"pipeline budget policy check failed: {budget_policy_check.stderr}", errors)
    backlog_queue_check = subprocess.run(
        [sys.executable, "scripts/ci/check_backlog_queue.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(backlog_queue_check.returncode == 0, f"backlog queue check failed: {backlog_queue_check.stderr}", errors)
    blockers_registry_check = subprocess.run(
        [sys.executable, "scripts/ci/check_blockers_registry.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(blockers_registry_check.returncode == 0, f"blockers registry check failed: {blockers_registry_check.stderr}", errors)
    ui_kit_usage_guard = ROOT / "scripts" / "ui" / "ui_kit_usage_guard.py"
    require(ui_kit_usage_guard.exists(), "W12 ui-kit usage guard must exist", errors)
    if ui_kit_usage_guard.exists():
        current_ui_usage = subprocess.run(
            [sys.executable, str(ui_kit_usage_guard)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(current_ui_usage.returncode == 0, f"W12 ui-kit usage guard failed on current tree: {current_ui_usage.stderr}", errors)
        temp_screen = ROOT / "frontend" / "src" / "screens" / "__UiKitMetatestScreen.tsx"
        try:
            temp_screen.write_text(
                "import { Button } from '@mui/material'\n"
                "export function __UiKitMetatestScreen() {\n"
                "  return <Button>Плохо</Button>\n"
                "}\n",
                encoding="utf-8",
            )
            blocked_new_screen = subprocess.run(
                [sys.executable, str(ui_kit_usage_guard)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(blocked_new_screen.returncode != 0, "W12 guard must reject a new screen without ui-kit import", errors)
            temp_screen.write_text(
                "import { Button } from '@mui/material'\n"
                "import { ScreenHeader } from '../ui-kit'\n"
                "export function __UiKitMetatestScreen() {\n"
                "  return <><ScreenHeader title=\"Тест\" /><Button>Плохо</Button></>\n"
                "}\n",
                encoding="utf-8",
            )
            blocked_raw_ui = subprocess.run(
                [sys.executable, str(ui_kit_usage_guard)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(blocked_raw_ui.returncode != 0, "W12 guard must reject raw MUI even when a screen imports ui-kit", errors)
            temp_screen.write_text(
                "import { ScreenHeader } from '../ui-kit'\n"
                "export function __UiKitMetatestScreen() {\n"
                "  return <ScreenHeader title=\"Тест\" />\n"
                "}\n",
                encoding="utf-8",
            )
            allowed_new_screen = subprocess.run(
                [sys.executable, str(ui_kit_usage_guard)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(allowed_new_screen.returncode == 0, f"W12 guard must allow a new screen with ui-kit import: {allowed_new_screen.stderr}", errors)
        finally:
            temp_screen.unlink(missing_ok=True)
    ui_inventory = read("scripts/ui/ui_inventory.py")
    require("UI_KIT_COMPONENTS" in ui_inventory and '"components": components' in ui_inventory, "ui inventory must expose machine-readable ui-kit components", errors)
    require(
        all(item.get("status") == "automated_green" for item in contract.get("required_metatests", [])),
        "all declared pipeline metatests must be automated_green before this implementation slice is accepted",
        errors,
    )

    # MT24 and MT31: controller refuses DONE while not ACTIVE, and no-traffic is not DONE.
    controller = read("pipeline/controller.py")
    require('contract.get("status") != "ACTIVE"' in controller, "controller must forbid DONE before ACTIVE", errors)
    require("ROLE_BY_STAGE" in controller, "controller must map stages to agent roles", errors)
    require("command_packet" in controller, "controller must produce agent handoff packets", errors)
    require("command_hold" in controller, "controller must support owner hold before execution", errors)
    require("command_resume" in controller, "controller must support explicit resume after owner hold", errors)
    require("command_start_wave" in controller, "controller must support owner-approved backlog wave start", errors)
    require("command_resolve_blocker" in controller, "controller must support blocker closure evidence", errors)
    require("budget_enforced" in controller, "controller must enforce usage receipts for wave tasks", errors)
    require('state.get("status") == "WAITING"' in controller, "controller must block advance while task is WAITING", errors)
    require("BLOCKER_TYPES" in controller, "controller must bind hold choices to pipeline blocker types", errors)
    for blocker_type in contract["blocker_types"]:
        require(f'"{blocker_type}"' in controller, f"controller blocker choices must include {blocker_type}", errors)
    require((ROOT / "scripts" / "pipeline" / "dispatch.py").exists(), "dispatch prompt writer must exist", errors)
    require('"MONITORING_NO_TRAFFIC"' in read("pipeline/pipeline.yml"), "MONITORING_NO_TRAFFIC verdict must be declared", errors)

    # MT33: entrypoint inventory is guarded by the contract checker.
    checker = read("scripts/ci/check_pipeline_contract.py")
    require("STATUS_POINTER_FILES" in checker, "contract checker must validate entrypoint pointers", errors)
    secret_scan = ROOT / "scripts" / "ci" / "check_pipeline_evidence_secrets.py"
    require(secret_scan.exists(), "pipeline evidence secret scan must exist", errors)
    require("check_pipeline_evidence_secrets.py" in read(".github/workflows/ci.yml"), "CI must run pipeline evidence secret scan", errors)
    if secret_scan.exists():
        current_scan = subprocess.run(
            [sys.executable, str(secret_scan)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(current_scan.returncode == 0, f"pipeline evidence secret scan failed: {current_scan.stderr}", errors)
        secret_fixture = ROOT / "docs" / "evidence" / "TASK-METATEST-SECRET" / "leak.txt"
        secret_fixture.parent.mkdir(parents=True, exist_ok=True)
        secret_fixture.write_text("Authorization: Bearer sk-0123456789abcdef0123456789abcdef\n", encoding="utf-8")
        blocked_secret = subprocess.run(
            [sys.executable, str(secret_scan), "docs/evidence/TASK-METATEST-SECRET"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(blocked_secret.returncode != 0, "pipeline evidence secret scan must reject raw bearer tokens", errors)
        shutil.rmtree(secret_fixture.parent, ignore_errors=True)

    # MT38: every trait declares all machine dimensions.
    for name, trait in traits.items():
        for key in ("required_stages", "required_receipts", "case_dimensions", "acceptance_surfaces"):
            require(bool(trait.get(key)), f"trait {name} must declare {key}", errors)

    # MT18, MT19, MT20, MT28, MT30, MT39: important trait routing is encoded in the contract.
    require(
        not any(stage in traits["ui_change"]["required_stages"] for stage in ["S03", "S04", "S05", "S06", "S07"]),
        "small ui_change must not require full domain research",
        errors,
    )
    require(stage_order.index("S24") < stage_order.index("S25"), "S24 must precede S25 for UI acceptance", errors)
    require({"S03", "S04", "S15"}.issubset(set(traits["external_contract"]["required_stages"])), "external_contract must require research, critic and cases", errors)
    require("emulator_or_allowed_sandbox" in traits["external_contract"]["required_receipts"], "external_contract must require emulator or allowed sandbox receipt", errors)
    require({"S03", "S04", "S05", "S06", "S07", "S13", "S14"}.issubset(set(traits["new_domain"]["required_stages"])), "new_domain must require research/process/product/arch path", errors)
    require({"S03", "S04", "S05", "S06", "S07", "S13", "S14"}.issubset(set(traits["new_module"]["required_stages"])), "new_module must require research/process/product/arch path", errors)
    require({"S13", "S15", "S22", "S23", "S26"}.issubset(set(traits["database_change"]["required_stages"])), "database_change must require arch/cases/tests/regression/release auth", errors)
    for receipt in ["migration_compatibility", "restore_rollback_rehearsal"]:
        require(receipt in traits["database_change"]["required_receipts"], f"database_change must require {receipt}", errors)

    # MT13: the reusable test runner must deny live marketplace hosts by default.
    egress_guard = ROOT / "scripts" / "testing" / "test_egress_guard.py"
    require(egress_guard.exists(), "test egress guard must exist", errors)
    require(
        (ROOT / "scripts" / "testing" / "test_egress_node.cjs").exists(),
        "Node test egress hook must exist",
        errors,
    )
    if egress_guard.exists():
        allowed = subprocess.run(
            [
                sys.executable,
                str(egress_guard),
                "--",
                sys.executable,
                "-c",
                "import socket; socket.getaddrinfo('127.0.0.1', 9)",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(allowed.returncode == 0, f"test egress guard blocked loopback: {allowed.stderr}", errors)
        blocked = subprocess.run(
            [
                sys.executable,
                str(egress_guard),
                "--",
                sys.executable,
                "-c",
                "import socket; socket.getaddrinfo('content-api.wildberries.ru', 443)",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(blocked.returncode != 0, "test egress guard must block live Wildberries before DNS", errors)
        live_url_env = os.environ.copy()
        live_url_env["WILDBERRIES_CONTENT_API_BASE"] = "https://content-api.wildberries.ru"
        live_url = subprocess.run(
            [sys.executable, str(egress_guard), "--check"],
            cwd=ROOT,
            env=live_url_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(live_url.returncode != 0, "test egress guard must reject live URL configuration", errors)
        opt_in_env = live_url_env.copy()
        opt_in_env["WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES"] = "1"
        opt_in = subprocess.run(
            [sys.executable, str(egress_guard), "--check"],
            cwd=ROOT,
            env=opt_in_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(opt_in.returncode == 0, "explicit live marketplace opt-in must be recognized", errors)
        opt_in_subdomain = subprocess.run(
            [
                sys.executable,
                str(egress_guard),
                "--",
                sys.executable,
                "-c",
                "import sitecustomize; assert sitecustomize._matches_allowlist('content-api.wildberries.ru')",
            ],
            cwd=ROOT,
            env=opt_in_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(opt_in_subdomain.returncode == 0, "explicit live marketplace opt-in must include subdomains", errors)
    ci_workflow = read(".github/workflows/ci.yml")
    require("scripts/testing/test_egress_guard.py -- bash -lc 'cd backend && pytest'" in ci_workflow, "backend pytest CI must run through test egress guard", errors)
    require("scripts/testing/test_egress_guard.py -- bash -lc 'cd frontend && npx playwright test'" in ci_workflow, "frontend Playwright CI must run through test egress guard", errors)

    deploy_workflow = read(".github/workflows/deploy.yml")
    prod_update = read("scripts/deploy/prod-update.sh")
    require("release_sha" in deploy_workflow, "deploy workflow must require release_sha input", errors)
    require("branches: [main]" not in deploy_workflow, "deploy workflow must not auto-deploy push to main", errors)
    require("git checkout main" not in deploy_workflow + prod_update, "deploy must not checkout main", errors)
    require("WMS_RELEASE_SHA" in prod_update, "prod-update must require WMS_RELEASE_SHA", errors)
    require("build-offline-release-artifact.sh" in deploy_workflow, "deploy workflow must build offline release artifact once in CI", errors)
    require("actions/upload-artifact" in deploy_workflow and "actions/download-artifact" in deploy_workflow, "deploy workflow must promote the uploaded exact-SHA artifact", errors)
    require("WMS_RELEASE_MANIFEST" in prod_update, "prod-update must require release manifest", errors)
    require("docker load" in prod_update, "prod-update must load prebuilt images", errors)
    require("build: null" in prod_update, "prod-update compose override must null service build definitions", errors)
    require("--no-build" in prod_update, "prod-update must start application services with --no-build", errors)
    require("docker compose prod build" not in prod_update and 'build "$service"' not in prod_update, "prod-update must not build production images on server", errors)
    require("artifact_digest" in deploy_workflow and "WMS_ARTIFACT_DIGEST" in prod_update, "deploy smoke must verify artifact digest", errors)
    manifest_test = subprocess.run(
        ["bash", "scripts/deploy/test-release-manifest.sh"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(manifest_test.returncode == 0, f"release manifest test failed: {manifest_test.stderr}", errors)

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
        independent = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "open",
                "--task-id",
                "TASK-METATEST-INDEPENDENT",
                "--source",
                "metatest independent",
                "--traits",
                "pipeline_change",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(independent.returncode == 0, f"independent task open failed: {independent.stderr}", errors)
        if independent.returncode == 0:
            independent_advance = subprocess.run(
                [
                    sys.executable,
                    "scripts/pipeline/run.py",
                    "advance",
                    "--task-id",
                    "TASK-METATEST-INDEPENDENT",
                    "--stage",
                    "S01",
                    "--verdict",
                    "TASK_INTAKE_READY",
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
            require(independent_advance.returncode == 0, f"independent task must advance while another task waits: {independent_advance.stderr}", errors)
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
        good_advance = subprocess.run(
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
                "pipeline-dispatcher",
                "--agent",
                "metatest",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(good_advance.returncode == 0, f"valid S01 advance failed: {good_advance.stderr}", errors)
        if good_advance.returncode == 0:
            valid_state = subprocess.run(
                [sys.executable, "scripts/pipeline/run.py", "validate", "--task-id", "TASK-METATEST"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(valid_state.returncode == 0, f"valid receipt chain failed validation: {valid_state.stderr}", errors)
            receipt_path = ROOT / "docs" / "evidence" / "TASK-METATEST" / "S01-TASK_INTAKE_READY.receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["role_binding_id"] = "pipeline-dev"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tampered_state = subprocess.run(
                [sys.executable, "scripts/pipeline/run.py", "validate", "--task-id", "TASK-METATEST"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(tampered_state.returncode != 0, "tampered receipt must fail validation", errors)
            receipt["role_binding_id"] = "pipeline-dispatcher"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report_result = subprocess.run(
                [sys.executable, "scripts/pipeline/run.py", "report", "--format", "json"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            require(report_result.returncode == 0, f"machine report failed: {report_result.stderr}", errors)
            if report_result.returncode == 0:
                report = json.loads(report_result.stdout)
                require(any(row["task_id"] == "TASK-METATEST" for row in report["tasks"]), "machine report must include controller state", errors)
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / "TASK-METATEST", ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / "TASK-METATEST", ignore_errors=True)
    shutil.rmtree(ROOT / "docs" / "evidence" / "TASK-METATEST", ignore_errors=True)
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / "TASK-METATEST-INDEPENDENT", ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / "TASK-METATEST-INDEPENDENT", ignore_errors=True)
    shutil.rmtree(ROOT / "docs" / "evidence" / "TASK-METATEST-INDEPENDENT", ignore_errors=True)

    # MT05, MT14, MT27: controller-owned resource leases serialize conflicts,
    # bind workers to their own queues, and reject stale fencing tokens.
    lock_prefix = f"TASK-METATEST-LOCK-{os.getpid()}"
    lock_a, lock_b, lock_c, lock_d = [f"{lock_prefix}-{suffix}" for suffix in "ABCD"]
    queue_a = f"metatest-{os.getpid()}-a"
    queue_b = f"metatest-{os.getpid()}-b"
    queue_expiry = f"metatest-{os.getpid()}-expiry"
    file_resource = f"file:metatest/{os.getpid()}.txt"
    process_resource = f"process:metatest-worker-{os.getpid()}"
    table_resource = f"table:metatest_orders_{os.getpid()}"
    lock_a_resources = f"{file_resource},{process_resource},queue:{queue_a},{table_resource}"
    lock_b_resources = f"{file_resource},{process_resource},queue:{queue_b},{table_resource}"
    lock_tasks = [lock_a, lock_b, lock_c, lock_d]
    try:
        open_a = pipeline_command(
            "open", "--task-id", lock_a, "--source", "lock metatest A", "--traits", "pipeline_change",
            "--celery-queue", queue_a, "--resources", lock_a_resources,
        )
        open_b = pipeline_command(
            "open", "--task-id", lock_b, "--source", "lock metatest B", "--traits", "pipeline_change",
            "--celery-queue", queue_b, "--resources", lock_b_resources,
        )
        require(open_a.returncode == 0 and open_b.returncode == 0, "lock metatest tasks must open", errors)
        if open_a.returncode == 0 and open_b.returncode == 0:
            acquired_a = pipeline_command("lock-acquire", "--task-id", lock_a, "--agent", "metatest-a")
            require(acquired_a.returncode == 0, f"MT05 initial lock acquire failed: {acquired_a.stderr}", errors)
            tokens_a = json.loads(acquired_a.stdout).get("fencing_tokens", {}) if acquired_a.returncode == 0 else {}
            conflict = pipeline_command("lock-acquire", "--task-id", lock_b, "--agent", "metatest-b")
            require(conflict.returncode != 0, "MT05 conflicting file/table/process locks must serialize agents", errors)
            file_token = tokens_a.get(file_resource)
            queue_a_token = tokens_a.get(f"queue:{queue_a}")
            if isinstance(file_token, int):
                renewed = pipeline_command(
                    "lock-renew", "--task-id", lock_a, "--agent", "metatest-a",
                    "--resources", file_resource, "--fencing-token", str(file_token), "--lease-seconds", "120",
                )
                require(renewed.returncode == 0, f"lock renew failed: {renewed.stderr}", errors)
                released = pipeline_command(
                    "lock-release", "--task-id", lock_a, "--agent", "metatest-a",
                    "--resources", file_resource, "--fencing-token", str(file_token),
                )
                require(released.returncode == 0, f"lock release failed: {released.stderr}", errors)
                acquired_b_file = pipeline_command(
                    "lock-acquire", "--task-id", lock_b, "--agent", "metatest-b",
                    "--resources", file_resource,
                )
                require(acquired_b_file.returncode == 0, f"released resource must be acquirable: {acquired_b_file.stderr}", errors)
            else:
                errors.append("MT05 acquire must return file fencing token")
            if isinstance(queue_a_token, int):
                own_queue = pipeline_command(
                    "worker-claim", "--task-id", lock_a, "--queue", queue_a, "--agent", "metatest-a",
                    "--fencing-token", str(queue_a_token),
                )
                other_queue = pipeline_command(
                    "worker-claim", "--task-id", lock_a, "--queue", queue_b, "--agent", "metatest-a",
                    "--fencing-token", str(queue_a_token),
                )
                require(own_queue.returncode == 0, f"MT14 worker must claim its own task queue: {own_queue.stderr}", errors)
                require(other_queue.returncode != 0, "MT14 worker must reject another task queue", errors)
            else:
                errors.append("MT14 acquire must return queue fencing token")

        open_c = pipeline_command(
            "open", "--task-id", lock_c, "--source", "lock metatest C", "--traits", "pipeline_change",
            "--celery-queue", queue_expiry, "--resources", f"queue:{queue_expiry}",
        )
        open_d = pipeline_command(
            "open", "--task-id", lock_d, "--source", "lock metatest D", "--traits", "pipeline_change",
            "--celery-queue", queue_expiry, "--resources", f"queue:{queue_expiry}",
        )
        require(open_c.returncode == 0 and open_d.returncode == 0, "expiry metatest tasks must open", errors)
        if open_c.returncode == 0 and open_d.returncode == 0:
            expired_acquire = pipeline_command(
                "lock-acquire", "--task-id", lock_c, "--agent", "metatest-c", "--lease-seconds", "0",
            )
            old_token = json.loads(expired_acquire.stdout).get("fencing_tokens", {}).get(f"queue:{queue_expiry}") if expired_acquire.returncode == 0 else None
            fresh_acquire = pipeline_command("lock-acquire", "--task-id", lock_d, "--agent", "metatest-d")
            fresh_token = json.loads(fresh_acquire.stdout).get("fencing_tokens", {}).get(f"queue:{queue_expiry}") if fresh_acquire.returncode == 0 else None
            require(expired_acquire.returncode == 0 and fresh_acquire.returncode == 0, "expiry must permit a fresh lease", errors)
            if isinstance(old_token, int) and isinstance(fresh_token, int):
                stale_claim = pipeline_command(
                    "worker-claim", "--task-id", lock_d, "--queue", queue_expiry, "--agent", "metatest-d",
                    "--fencing-token", str(old_token),
                )
                fresh_claim = pipeline_command(
                    "worker-claim", "--task-id", lock_d, "--queue", queue_expiry, "--agent", "metatest-d",
                    "--fencing-token", str(fresh_token),
                )
                require(old_token != fresh_token, "expired lease must receive a new fencing token", errors)
                require(stale_claim.returncode != 0, "MT27 stale fencing token must be rejected", errors)
                require(fresh_claim.returncode == 0, f"fresh fencing token must be accepted: {fresh_claim.stderr}", errors)
            else:
                errors.append("MT27 lease acquire must return old and fresh fencing tokens")
    finally:
        for task_id in lock_tasks:
            cleanup_task(task_id)
        controller_lock = ROOT / ".pipeline-state" / "controller.lock"
        controller_lock.parent.mkdir(parents=True, exist_ok=True)
        with controller_lock.open("a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                lock_store_path = ROOT / ".pipeline-state" / "locks.json"
                if lock_store_path.exists():
                    lock_store = json.loads(lock_store_path.read_text(encoding="utf-8"))
                    locks = lock_store.get("locks")
                    if isinstance(locks, dict):
                        lock_store["locks"] = {
                            resource: lock for resource, lock in locks.items()
                            if not isinstance(lock, dict) or lock.get("task_id") not in lock_tasks
                        }
                        lock_store_path.write_text(json.dumps(lock_store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    controller_prefix = f"TASK-METATEST-CTL-{os.getpid()}"
    controller_tasks: list[str] = []
    try:
        def open_task(suffix: str, traits_value: str = "") -> str:
            task_id = f"{controller_prefix}-{suffix}"
            controller_tasks.append(task_id)
            opened = pipeline_command("open", "--task-id", task_id, "--source", f"controller metatest {suffix}", "--traits", traits_value)
            require(opened.returncode == 0, f"{task_id}: open failed: {opened.stderr}", errors)
            return task_id

        # MT07 and MT36: Product rejection/failure findings route to the owning stage and block downstream.
        product_task = open_task("PRODUCT", "ui_change")
        product_reject = pipeline_command("failure", "--task-id", product_task, "--finding", "PRODUCT_REJECTED", "--details", "mockup rejected")
        require(product_reject.returncode == 0, f"MT07 product reject route failed: {product_reject.stderr}", errors)
        if product_reject.returncode == 0:
            product_state = json.loads(pipeline_command("status", "--task-id", product_task).stdout)
            require(product_state["status"] == "REWORK" and product_state["current_stage"] == "S09", "MT07: Product rejection must return to S09 and block Dev", errors)
            downstream = pipeline_command("advance", "--task-id", product_task, "--stage", "S17", "--verdict", "WORKSPACE_READY", "--role", "pipeline-dispatcher", "--agent", "metatest")
            require(downstream.returncode != 0, "MT07: downstream workspace must not start after Product rejection", errors)
        unmapped_failure = pipeline_command("failure", "--task-id", product_task, "--finding", "UNMAPPED_FAILURE")
        require(unmapped_failure.returncode != 0, "MT36: unmapped failure verdict must be rejected", errors)

        # MT08 and MT37: changing task inputs/profile after a receipt invalidates the dependent chain.
        invalidation_task = open_task("INVALIDATION", "ui_change")
        s01 = pipeline_command("advance", "--task-id", invalidation_task, "--stage", "S01", "--verdict", "TASK_INTAKE_READY", "--role", "pipeline-dispatcher", "--agent", "metatest")
        require(s01.returncode == 0, f"MT08 setup S01 failed: {s01.stderr}", errors)
        reprofile = pipeline_command("classify", "--task-id", invalidation_task, "--traits", "ui_change,external_contract")
        require(reprofile.returncode == 0, f"MT08 reclassify failed: {reprofile.stderr}", errors)
        if reprofile.returncode == 0:
            invalidated = json.loads(pipeline_command("status", "--task-id", invalidation_task).stdout)
            require(invalidated["status"] == "REWORK", "MT08: profile change after approval must enter REWORK", errors)
            require(not invalidated["verdicts"], "MT37: dependency invalidation must clear old verdicts", errors)
            require(bool(invalidated.get("invalidations")), "MT37: dependency invalidation must be recorded", errors)

        # MT09: expectation rewrite without a versioned oracle waits on oracle conflict.
        rewrite_task = open_task("REWRITE")
        rewrite_block = pipeline_command("expectation-rewrite", "--task-id", rewrite_task, "--case-id", "CASE-1")
        require(rewrite_block.returncode == 0, f"MT09 rewrite block command failed: {rewrite_block.stderr}", errors)
        if rewrite_block.returncode == 0:
            rewrite_state = json.loads(pipeline_command("status", "--task-id", rewrite_task).stdout)
            require(rewrite_state["status"] == "WAITING" and rewrite_state["current_stage"] == "S15", "MT09: expectation rewrite without oracle must wait at S15", errors)

        # MT10: a red GOLD case routes back before integration.
        gold_task = open_task("GOLD")
        gold_red = pipeline_command("case-result", "--task-id", gold_task, "--case-id", "GOLD-1", "--tier", "GOLD", "--status", "red")
        require(gold_red.returncode == 0, f"MT10 red GOLD command failed: {gold_red.stderr}", errors)
        if gold_red.returncode == 0:
            gold_state = json.loads(pipeline_command("status", "--task-id", gold_task).stdout)
            require(gold_state["status"] == "REWORK" and gold_state["current_stage"] == "S18", "MT10: red GOLD must route to S18 before integration", errors)

        # MT11: snapshot/baseline drift waits for triage, not release.
        snapshot_task = open_task("SNAPSHOT", "ui_change")
        snapshot_changed = pipeline_command("failure", "--task-id", snapshot_task, "--finding", "SNAPSHOT_CHANGED", "--details", "visual baseline changed")
        require(snapshot_changed.returncode == 0, f"MT11 snapshot route failed: {snapshot_changed.stderr}", errors)
        if snapshot_changed.returncode == 0:
            snapshot_state = json.loads(pipeline_command("status", "--task-id", snapshot_task).stdout)
            require(snapshot_state["status"] == "WAITING" and snapshot_state["current_stage"] == "S24", "MT11: snapshot change must wait for S24 triage", errors)

        # MT16: a regression after a fix reopens root-cause/escape history.
        regression_task = open_task("REGRESSION", "bug")
        regression = pipeline_command("failure", "--task-id", regression_task, "--finding", "REGRESSION_DETECTED", "--details", "closed incident reproduced")
        require(regression.returncode == 0, f"MT16 regression route failed: {regression.stderr}", errors)
        if regression.returncode == 0:
            regression_state = json.loads(pipeline_command("status", "--task-id", regression_task).stdout)
            require(regression_state["status"] == "REWORK" and regression_state["current_stage"] == "B03", "MT16: regression must reopen B03 history", errors)

        # MT17: NOT_REPRODUCED creates observation instead of closing the bug.
        nr_task = open_task("NOTREPRO", "bug")
        advance_until(nr_task, "B01", pass_verdicts, errors)
        nr = pipeline_command("advance", "--task-id", nr_task, "--stage", "B01", "--verdict", "NOT_REPRODUCED", "--role", "pipeline-ba", "--agent", "metatest-ba")
        require(nr.returncode == 0, f"MT17 NOT_REPRODUCED advance failed: {nr.stderr}", errors)
        if nr.returncode == 0:
            nr_state = json.loads(pipeline_command("status", "--task-id", nr_task).stdout)
            require(nr_state["status"] == "WAITING" and nr_state.get("observations"), "MT17: NOT_REPRODUCED must create observation WAITING state", errors)

        # MT23: the producer identity cannot accept its own result.
        self_accept_task = open_task("SELFACCEPT")
        advance_until(self_accept_task, "S18", pass_verdicts, errors)
        dev_done = pipeline_command("advance", "--task-id", self_accept_task, "--stage", "S18", "--verdict", "DEV_DONE", "--role", "pipeline-dev", "--agent", "same-agent")
        require(dev_done.returncode == 0, f"MT23 setup S18 failed: {dev_done.stderr}", errors)
        s19 = pipeline_command("advance", "--task-id", self_accept_task, "--stage", "S19", "--verdict", "CASES_EXECUTABLE", "--role", "pipeline-dev", "--agent", "automation-agent")
        require(s19.returncode == 0, f"MT23 setup S19 failed: {s19.stderr}", errors)
        self_review = pipeline_command("advance", "--task-id", self_accept_task, "--stage", "S20", "--verdict", "CODE_REVIEW_PASSED", "--role", "pipeline-reviewer", "--agent", "same-agent")
        require(self_review.returncode != 0, "MT23: worker identity must not accept its own result", errors)

        # MT24: release-ready/DONE require commit, push, checks and final verdicts.
        close_task = open_task("CLOSE")
        close_ready = pipeline_command("close", "--task-id", close_task, "--status", "READY_FOR_RELEASE")
        close_done = pipeline_command("close", "--task-id", close_task, "--status", "DONE")
        require(close_ready.returncode != 0, "MT24: READY_FOR_RELEASE must require commit/push/tests/verdicts", errors)
        require(close_done.returncode != 0, "MT24: DONE must be forbidden without final release proof", errors)

        # MT29 and MT36: required case without runnable binding is routed to S19.
        binding_task = open_task("BINDING")
        no_binding = pipeline_command("failure", "--task-id", binding_task, "--finding", "REQUIRED_CASE_WITHOUT_BINDING", "--details", "CASE-1 has no executable_ref")
        require(no_binding.returncode == 0, f"MT29 binding route failed: {no_binding.stderr}", errors)
        if no_binding.returncode == 0:
            binding_state = json.loads(pipeline_command("status", "--task-id", binding_task).stdout)
            require(binding_state["status"] == "WAITING" and binding_state["current_stage"] == "S19", "MT29: missing runnable binding must wait at S19", errors)

        # MT34: emergency cannot even open without signed scope/debt.
        emergency_block = pipeline_command("open", "--task-id", f"{controller_prefix}-EMERGENCY-BLOCK", "--source", "emergency", "--traits", "emergency")
        require(emergency_block.returncode != 0, "MT34: emergency without signed scope/debt must be blocked", errors)
        emergency_ok = pipeline_command(
            "open", "--task-id", f"{controller_prefix}-EMERGENCY-OK", "--source", "emergency", "--traits", "emergency",
            "--emergency-scope-receipt", "docs/evidence/emergency-scope.receipt.json", "--emergency-debt-id", "DEBT-PIPELINE-METATEST",
        )
        require(emergency_ok.returncode == 0, f"MT34: signed emergency profile should open: {emergency_ok.stderr}", errors)
        if emergency_ok.returncode == 0:
            controller_tasks.append(f"{controller_prefix}-EMERGENCY-OK")

        # MT35: mutating cases need isolation or an ordered journey group.
        mutating_task = open_task("MUTATING")
        unsafe_case = pipeline_command("case-result", "--task-id", mutating_task, "--case-id", "MUT-1", "--tier", "SILVER", "--status", "green", "--mutates-state")
        require(unsafe_case.returncode == 0, f"MT35 unsafe mutating case command failed: {unsafe_case.stderr}", errors)
        if unsafe_case.returncode == 0:
            mutating_state = json.loads(pipeline_command("status", "--task-id", mutating_task).stdout)
            require(mutating_state["status"] == "WAITING" and mutating_state["current_stage"] == "S15", "MT35: unsafe mutating case must wait at S15", errors)

        # MT40: controller-side idempotency key fences external side effects.
        effect_task = open_task("EFFECT")
        first_effect = pipeline_command("external-effect", "--task-id", effect_task, "--effect", "deploy-comment", "--idempotency-key", "same-key")
        second_effect = pipeline_command("external-effect", "--task-id", effect_task, "--effect", "deploy-comment", "--idempotency-key", "same-key")
        require(first_effect.returncode == 0 and second_effect.returncode == 0, "MT40: external effect command must be replayable", errors)
        if first_effect.returncode == 0 and second_effect.returncode == 0:
            first_payload = json.loads(first_effect.stdout)
            second_payload = json.loads(second_effect.stdout)
            require(first_payload["replayed"] is True and second_payload["replayed"] is False, "MT40: repeated effect key must not run twice", errors)
    finally:
        for task_id in controller_tasks:
            cleanup_task(task_id)
        effect_store_path = ROOT / ".pipeline-state" / "external-effects.json"
        if effect_store_path.exists():
            effect_store = json.loads(effect_store_path.read_text(encoding="utf-8"))
            effects = effect_store.get("effects")
            if isinstance(effects, dict):
                effect_store["effects"] = {
                    key: value for key, value in effects.items()
                    if not isinstance(value, dict) or value.get("task_id") not in controller_tasks
                }
                effect_store_path.write_text(json.dumps(effect_store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reclass = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline/run.py",
            "open",
            "--task-id",
            "TASK-METATEST-RECLASS",
            "--source",
            "metatest reclass",
            "--traits",
            "ui_change",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(reclass.returncode == 0, f"reclass task open failed: {reclass.stderr}", errors)
    if reclass.returncode == 0:
        reclassified = subprocess.run(
            [
                sys.executable,
                "scripts/pipeline/run.py",
                "classify",
                "--task-id",
                "TASK-METATEST-RECLASS",
                "--traits",
                "ui_change,external_contract",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(reclassified.returncode == 0, f"reclass task classify failed: {reclassified.stderr}", errors)
        if reclassified.returncode == 0:
            profile = json.loads(reclassified.stdout)
            require({"S03", "S04", "S15"}.issubset(set(profile["required_stages"])), "reclassification must expand required stages", errors)
    shutil.rmtree(ROOT / ".pipeline-state" / "tasks" / "TASK-METATEST-RECLASS", ignore_errors=True)
    shutil.rmtree(ROOT / "tasks" / "TASK-METATEST-RECLASS", ignore_errors=True)

    # MT41-MT43: owner-approved backlog wave creates budget-enforced tasks,
    # missing usage holds the task, and open blockers stop the owning stage.
    wave_prefix = f"TASK-METATEST-WAVE-{os.getpid()}-"
    budget_wave = f"metatest-budget-{os.getpid()}"
    budget_task = f"{wave_prefix}BLG-I04"
    blocker_wave = f"metatest-blocker-{os.getpid()}"
    blocker_task = f"{wave_prefix}BLG-D19"
    try:
        budget_start = pipeline_command(
            "start-wave",
            "--backlog-ids", "BLG-I04",
            "--owner-approved-by", "metatest-owner",
            "--wave-id", budget_wave,
            "--task-prefix", wave_prefix,
        )
        require(budget_start.returncode == 0, f"MT41 start-wave failed: {budget_start.stderr}", errors)
        if budget_start.returncode == 0:
            budget_state = json.loads(pipeline_command("status", "--task-id", budget_task).stdout)
            require(budget_state.get("budget_enforced") is True, "MT41: start-wave task must enforce budget usage receipts", errors)
            no_usage = pipeline_command(
                "advance", "--task-id", budget_task, "--stage", "S01", "--verdict", "TASK_INTAKE_READY",
                "--role", "pipeline-dispatcher", "--agent", "metatest",
            )
            require(no_usage.returncode != 0, "MT42: budget-enforced advance without usage must fail", errors)
            held = json.loads(pipeline_command("status", "--task-id", budget_task).stdout)
            require(held["status"] == "WAITING" and held.get("blocker", {}).get("reason_code") == "BUDGET_HARD_STOP", "MT42: missing usage must hold task with BUDGET_HARD_STOP", errors)
            resumed_budget = pipeline_command("resume", "--task-id", budget_task, "--by", "metatest-owner")
            require(resumed_budget.returncode == 0, f"MT42 resume budget task failed: {resumed_budget.stderr}", errors)
            with_usage = pipeline_command(
                "advance", "--task-id", budget_task, "--stage", "S01", "--verdict", "TASK_INTAKE_READY",
                "--role", "pipeline-dispatcher", "--agent", "metatest", "--executor", "codex",
                "--input-tokens", "100", "--output-tokens", "50", "--estimated-usd", "0.01",
            )
            require(with_usage.returncode == 0, f"MT42 advance with usage failed: {with_usage.stderr}", errors)

        blocker_start = pipeline_command(
            "start-wave",
            "--backlog-ids", "BLG-D19",
            "--owner-approved-by", "metatest-owner",
            "--wave-id", blocker_wave,
            "--task-prefix", wave_prefix,
        )
        require(blocker_start.returncode == 0, f"MT43 blocker start-wave failed: {blocker_start.stderr}", errors)
        if blocker_start.returncode == 0:
            blocker_state = json.loads(pipeline_command("status", "--task-id", blocker_task).stdout)
            require(any(blocker.get("id") == "BLK-RESEARCH-001" for blocker in blocker_state.get("blocked_by", [])), "MT43: BLG-D19 must bind BLK-RESEARCH-001", errors)
            for stage, verdict, role in [
                ("S01", "TASK_INTAKE_READY", "pipeline-dispatcher"),
                ("S02", "IMPACT_CLASSIFIED", "pipeline-dispatcher"),
            ]:
                advanced = pipeline_command(
                    "advance", "--task-id", blocker_task, "--stage", stage, "--verdict", verdict,
                    "--role", role, "--agent", "metatest", "--executor", "codex",
                    "--input-tokens", "100", "--output-tokens", "50", "--estimated-usd", "0.01",
                )
                require(advanced.returncode == 0, f"MT43 setup {stage} failed: {advanced.stderr}", errors)
            blocked = pipeline_command(
                "advance", "--task-id", blocker_task, "--stage", "S03", "--verdict", "RESEARCH_READY",
                "--role", "pipeline-ba", "--agent", "metatest", "--executor", "codex",
                "--input-tokens", "100", "--output-tokens", "50", "--estimated-usd", "0.01",
            )
            require(blocked.returncode != 0, "MT43: open blocker must stop its resume stage", errors)
            held_by_blocker = json.loads(pipeline_command("status", "--task-id", blocker_task).stdout)
            require(held_by_blocker["status"] == "WAITING" and held_by_blocker.get("blocker", {}).get("reason_code") == "OPEN_BLOCKER", "MT43: open blocker must hold task", errors)
    finally:
        cleanup_task(budget_task)
        cleanup_task(blocker_task)
        cleanup_wave(budget_wave)
        cleanup_wave(blocker_wave)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline metatests ok: implementation slice is executable, activation still closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
