"""Fail-closed policy decisions for Pipeline v2 failure lanes.

This module deliberately has no controller or filesystem dependency.  The
controller can adopt the decisions later without duplicating the business
rules, while the companion metatest can exercise them now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class PolicyDecision:
    """A deterministic allow, block, or route decision for one pipeline fact."""

    allowed: bool
    disposition: str
    target: str
    reason: str


def allow(disposition: str = "ALLOW", target: str = "next_enabled_stage") -> PolicyDecision:
    return PolicyDecision(True, disposition, target, "")


def block(target: str, reason: str) -> PolicyDecision:
    return PolicyDecision(False, "BLOCKED", target, reason)


def development_gate(product_verdict: str) -> PolicyDecision:
    """Keep S17/S18 and every later stage closed until Product approves the card."""

    if product_verdict == "PRODUCT_APPROVED_FOR_DEV":
        return allow("DEVELOPMENT_ALLOWED", "S17")
    return block("S16", "development requires PRODUCT_APPROVED_FOR_DEV")


def bug_reproduction_route(verdict: str) -> PolicyDecision:
    """Route non-reproduction into observation; it is never a B04 closure."""

    if verdict == "NOT_REPRODUCED":
        return PolicyDecision(False, "OBSERVATION_REQUIRED", "B02", "signal and deadline are required before closure")
    if verdict == "REPRODUCED":
        return allow("CONTINUE", "B02")
    if verdict == "INTERMITTENT":
        return PolicyDecision(False, "OBSERVABILITY_ACTIVE", "B01", "resume B01 when the declared signal arrives")
    return block("B01", f"unknown bug reproduction verdict: {verdict}")


FAILURE_ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    ("S20", "CONTRACT"): ("S08", "REWORK"),
    ("S20", "PLAN"): ("S13", "REWORK"),
    ("S20", "IMPLEMENTATION"): ("S18", "REWORK"),
    ("S20", "AUTOMATION"): ("S19", "REWORK"),
    ("S20", "MIGRATION"): ("OWNING_DATABASE_RECEIPT", "REWORK"),
    ("S22", "PRODUCT_DEFECT"): ("S18", "REWORK"),
    ("S22", "CASE_DEFECT"): ("S15", "REWORK"),
    ("S22", "FIXTURE_DEFECT"): ("S22_REPAIR", "REPAIR"),
    ("S22", "ENV_DEFECT"): ("S22_REPAIR", "REPAIR"),
    ("S22", "FLAKY"): ("FLAKE_REMEDIATION", "REPAIR"),
    ("S24", "IMPLEMENTATION"): ("S18", "REWORK"),
    ("S24", "MOCKUP"): ("S09", "REWORK"),
    ("S24", "PROCESS"): ("S05", "REWORK"),
    ("S25", "PRODUCT_DEFECT"): ("S18", "REWORK"),
    ("S25", "UX_DEFECT"): ("S09", "REWORK"),
    ("S25", "BEHAVIOR_DEFECT"): ("S08", "REWORK"),
    ("S25", "PROCESS_DEFECT"): ("S05", "REWORK"),
    ("S27", "DEPLOY_FAILURE"): ("ROLLBACK", "ROLLBACK"),
    ("S28", "TRACE_FAILURE"): ("ROLLBACK", "ROLLBACK"),
}


def failure_route(stage: str, finding: str) -> PolicyDecision:
    """Return the owning repair path, or block rather than silently dropping it."""

    route = FAILURE_ROUTES.get((stage, finding))
    if route is None:
        return block("WAITING", f"unmapped failure route for {stage}/{finding}")
    target, disposition = route
    return PolicyDecision(False, disposition, target, "failure must leave the current stage")


def emergency_gate(scope: Mapping[str, object], debt: Mapping[str, object]) -> PolicyDecision:
    """Require the signed bypass scope and immutable post-emergency debt."""

    required_scope = ("approval", "signed_by", "reason", "expires_at", "stage_exceptions")
    required_debt = ("debt_id", "owner", "due_at", "resume_stage", "immutable")
    missing_scope = [field for field in required_scope if not scope.get(field)]
    missing_debt = [field for field in required_debt if not debt.get(field)]
    if scope.get("approval") != "EMERGENCY_BYPASS_USER_APPROVED":
        missing_scope.append("EMERGENCY_BYPASS_USER_APPROVED")
    if debt.get("immutable") is not True and "immutable" not in missing_debt:
        missing_debt.append("immutable=true")
    if missing_scope or missing_debt:
        details = ", ".join([*missing_scope, *missing_debt])
        return block("S01", f"emergency profile requires signed scope and immutable debt: {details}")
    return allow("EMERGENCY_PROFILE_ALLOWED", "S08")


def integration_gate(cases: Iterable[Mapping[str, object]]) -> PolicyDecision:
    """A failed GOLD case blocks S23 regardless of other passing results."""

    for case in cases:
        if case.get("status") == "GOLD" and case.get("result") != "PASSED":
            case_id = case.get("id", "unknown")
            return block("S22", f"red GOLD case blocks integration: {case_id}")
    return allow("INTEGRATION_ALLOWED", "S23")


def expectation_rewrite_gate(oracle: Mapping[str, object] | None) -> PolicyDecision:
    """Expectation changes need a newly confirmed, versioned oracle."""

    if not oracle or oracle.get("confirmed") is not True or not oracle.get("reference") or not oracle.get("version"):
        return block("S15", "case expectation rewrite requires a confirmed versioned oracle")
    return allow("EXPECTATION_REWRITE_ALLOWED", "S15")


def functional_gate(cases: Iterable[Mapping[str, object]]) -> PolicyDecision:
    """Every required case needs a runnable binding before S22 can start."""

    for case in cases:
        if not case.get("required", False):
            continue
        binding = case.get("binding")
        if not isinstance(binding, Mapping) or binding.get("status") != "RUNNABLE" or not binding.get("executable_ref"):
            case_id = case.get("id", "unknown")
            return block("S19", f"required case has no runnable binding: {case_id}")
    return allow("FUNCTIONAL_ALLOWED", "S22")
