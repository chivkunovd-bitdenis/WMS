#!/usr/bin/env python3
"""Validate Pipeline v2 model budget policy and dispatch integration."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "pipeline" / "budget-policy.yml"
EXPECTED_TIERS = ["cheap", "moderate", "expensive"]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    require(policy.get("$schema") == "./budget-policy.schema.json", "budget policy must point to its schema", errors)
    require(policy.get("status") == "ACTIVE_FOR_DISPATCH", "budget policy must be active for dispatch", errors)
    limits = policy.get("limits", {})
    for scope in ("wave", "task", "card"):
        scoped = limits.get(scope, {})
        require(scoped.get("max_usd", 0) > 0, f"{scope} max_usd must be positive", errors)
        require(scoped.get("max_tokens", 0) > 0, f"{scope} max_tokens must be positive", errors)
        require(0 < scoped.get("warning_ratio", 0) < 1, f"{scope} warning_ratio must be between 0 and 1", errors)
        require(scoped.get("hard_stop_ratio") == 1.0, f"{scope} hard_stop_ratio must be 1.0", errors)

    stage_tier = limits.get("stage_tier", {})
    require(list(stage_tier) == EXPECTED_TIERS, "budget policy must declare cheap/moderate/expensive tier limits in order", errors)
    previous_usd = 0.0
    previous_tokens = 0
    for tier in EXPECTED_TIERS:
        tier_limit = stage_tier.get(tier, {})
        max_usd = tier_limit.get("max_usd", 0)
        max_tokens = tier_limit.get("max_tokens", 0)
        require(max_usd > previous_usd, f"{tier} max_usd must grow by tier", errors)
        require(max_tokens > previous_tokens, f"{tier} max_tokens must grow by tier", errors)
        previous_usd = max_usd
        previous_tokens = max_tokens

    hard_stop = policy.get("hard_stop", {})
    require(hard_stop.get("enabled") is True, "budget hard stop must be enabled", errors)
    require(hard_stop.get("on_budget_exceeded") == "hold_task", "budget exceeded must hold task", errors)
    require(hard_stop.get("on_missing_usage_receipt") == "block_next_stage", "missing usage receipt must block next stage", errors)
    require(hard_stop.get("reason_code") == "BUDGET_HARD_STOP", "budget hard stop reason code must be stable", errors)
    require(policy.get("accounting", {}).get("runtime_receipt_required") is True, "runtime usage receipt requirement must be explicit", errors)
    require(policy.get("accounting", {}).get("runtime_enforcement_implemented") is False, "scoped patch must not claim runtime enforcement", errors)

    required_fields = set(policy.get("usage_receipt", {}).get("required_fields", []))
    for field in ("task_id", "stage", "role", "executor", "model", "tier", "estimated_usd", "recorded_at"):
        require(field in required_fields, f"usage receipt must require {field}", errors)
    recovery_fields = set(policy.get("recovery_packet", {}).get("required_fields", []))
    require({"wave_id", "card_id", "stage", "tier", "limit", "observed_or_projected_usage", "next_action"} <= recovery_fields, "recovery packet fields are incomplete", errors)

    override = policy.get("owner_override", {})
    require("PIPELINE_BUDGET_OVERRIDE" in override.get("marker", ""), "owner override marker must be explicit", errors)
    require(override.get("requires_reason") is True, "owner override must require reason", errors)
    require(override.get("requires_new_limit") is True, "owner override must require new limit", errors)

    dispatch = (ROOT / "scripts" / "pipeline" / "dispatch.py").read_text(encoding="utf-8")
    require("recommendation_for_tier" in dispatch, "dispatch must calculate budget recommendation", errors)
    require("pipeline/budget-policy.yml" in dispatch, "dispatch prompt must mention budget policy path", errors)
    require("Usage receipt fields" in dispatch, "dispatch prompt must include usage receipt fields", errors)

    metatests = (ROOT / "scripts" / "ci" / "check_pipeline_metatests.py").read_text(encoding="utf-8")
    require("check_pipeline_budget_policy.py" in metatests, "pipeline metatests must run budget policy check", errors)
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    require("check_pipeline_budget_policy.py" in workflow, "CI must run budget policy check", errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline budget policy ok: per-wave/task/tier limits and hard stop are declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
