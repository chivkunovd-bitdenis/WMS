#!/usr/bin/env python3
"""Executable, fail-closed policy metatests for Pipeline v2 failure lanes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.policies import (  # noqa: E402
    FAILURE_ROUTES,
    bug_reproduction_route,
    development_gate,
    emergency_gate,
    expectation_rewrite_gate,
    failure_route,
    functional_gate,
    integration_gate,
)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def decision_is_blocked(decision, target: str) -> bool:
    return not decision.allowed and decision.target == target


def main() -> int:
    errors: list[str] = []

    # Keep executable assertions tied to the declared Pipeline v2 scenarios.
    contract = json.loads((ROOT / "pipeline" / "pipeline.yml").read_text(encoding="utf-8"))
    declared = {item["id"] for item in contract["required_metatests"]}
    for metatest in ("MT07", "MT09", "MT10", "MT17", "MT29", "MT34", "MT36"):
        require(metatest in declared, f"{metatest} must remain declared in pipeline.yml", errors)

    # MT07: any rejection, including a mockup rejection, holds all downstream work at S16.
    require(decision_is_blocked(development_gate("PRODUCT_CARD_REWORK"), "S16"), "MT07: Product rework must block development", errors)
    require(decision_is_blocked(development_gate("PRODUCT_CARD_BLOCKED"), "S16"), "MT07: blocked Product verdict must block development", errors)
    require(development_gate("PRODUCT_APPROVED_FOR_DEV").allowed, "MT07: Product approval must permit workspace allocation", errors)

    # MT17: non-reproduction creates observation and cannot use B04 closure.
    not_reproduced = bug_reproduction_route("NOT_REPRODUCED")
    require(not_reproduced.disposition == "OBSERVATION_REQUIRED", "MT17: NOT_REPRODUCED must require observation", errors)
    require(not_reproduced.target != "B04", "MT17: NOT_REPRODUCED must not close through B04", errors)

    # MT36: each declared failure lane reaches repair, rework, or rollback; unknown lanes wait closed.
    for (stage, finding), (target, disposition) in FAILURE_ROUTES.items():
        actual = failure_route(stage, finding)
        require(actual.target == target and actual.disposition == disposition and not actual.allowed, f"MT36: {stage}/{finding} lost its owning route", errors)
    require(decision_is_blocked(failure_route("S22", "UNCLASSIFIED"), "WAITING"), "MT36: unmapped failure must block in WAITING", errors)

    # MT34: neither a merely named bypass nor mutable debt opens the emergency profile.
    valid_scope = {
        "approval": "EMERGENCY_BYPASS_USER_APPROVED",
        "signed_by": "owner",
        "reason": "production incident",
        "expires_at": "2026-08-21T12:00:00Z",
        "stage_exceptions": ["S03"],
    }
    valid_debt = {"debt_id": "DEBT-1", "owner": "owner", "due_at": "2026-08-22", "resume_stage": "S03", "immutable": True}
    require(decision_is_blocked(emergency_gate({}, valid_debt), "S01"), "MT34: unsigned scope must block emergency", errors)
    mutable_debt = dict(valid_debt, immutable=False)
    require(decision_is_blocked(emergency_gate(valid_scope, mutable_debt), "S01"), "MT34: mutable debt must block emergency", errors)
    require(emergency_gate(valid_scope, valid_debt).allowed, "MT34: signed scope and immutable debt must permit the declared profile", errors)

    # MT10: one red GOLD case is sufficient to hold integration.
    require(decision_is_blocked(integration_gate([{"id": "GOLD-1", "status": "GOLD", "result": "FAILED"}]), "S22"), "MT10: red GOLD must block integration", errors)
    require(integration_gate([{"id": "GOLD-1", "status": "GOLD", "result": "PASSED"}]).allowed, "MT10: green GOLD may proceed", errors)

    # MT09: a changed expectation is valid only with a confirmed, versioned oracle.
    require(decision_is_blocked(expectation_rewrite_gate(None), "S15"), "MT09: missing oracle must block expectation rewrite", errors)
    require(decision_is_blocked(expectation_rewrite_gate({"confirmed": True, "reference": "contract"}), "S15"), "MT09: unversioned oracle must block expectation rewrite", errors)
    require(expectation_rewrite_gate({"confirmed": True, "reference": "contract-v2", "version": "2026-08-21"}).allowed, "MT09: confirmed versioned oracle must permit expectation rewrite", errors)

    # MT29: every required case has a real runnable reference before functional testing.
    require(decision_is_blocked(functional_gate([{"id": "CASE-1", "required": True}]), "S19"), "MT29: required case without binding must block functional", errors)
    require(decision_is_blocked(functional_gate([{"id": "CASE-1", "required": True, "binding": {"status": "RUNNABLE"}}]), "S19"), "MT29: runnable status without executable reference must block functional", errors)
    require(functional_gate([{"id": "CASE-1", "required": True, "binding": {"status": "RUNNABLE", "executable_ref": "pytest tests/test_case.py::test_case"}}]).allowed, "MT29: runnable required case must permit functional", errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline policy metatests ok: failure lane remains fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
