#!/usr/bin/env python3
"""Contract-level metatests for the first Pipeline v2 implementation slice."""

from __future__ import annotations

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


def main() -> int:
    errors: list[str] = []
    contract = load_contract()
    stage_order = [stage["id"] for stage in contract["stages"]]
    traits = contract["traits"]

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

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline metatests ok: implementation slice is executable, activation still closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
