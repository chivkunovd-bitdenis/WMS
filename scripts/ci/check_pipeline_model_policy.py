#!/usr/bin/env python3
"""Validate Pipeline v2 model selection policy and dispatch integration."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.controller import ROLE_BY_STAGE, TOTAL_ORDER  # noqa: E402
from pipeline.model_policy import recommend_model  # noqa: E402


POLICY_PATH = ROOT / "pipeline" / "model-policy.yml"
EXPECTED_TIERS = ["cheap", "moderate", "expensive"]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []
    policy = load_policy()

    require(policy.get("$schema") == "./model-policy.schema.json", "model policy must point to its schema", errors)
    require(policy.get("tiers") == EXPECTED_TIERS, "model policy tiers must be cheap/moderate/expensive in order", errors)
    for executor in ("codex", "claude", "cursor"):
        models = policy.get("executors", {}).get(executor)
        require(isinstance(models, dict), f"executor {executor} must be declared", errors)
        if isinstance(models, dict):
            for tier in EXPECTED_TIERS:
                require(bool(models.get(tier)), f"executor {executor} must declare {tier} model", errors)

    declared_roles = set(policy.get("default_tier_by_role", {}))
    controller_roles = set(ROLE_BY_STAGE.values())
    require(declared_roles == controller_roles, "model policy roles must match controller ROLE_BY_STAGE roles", errors)
    require(set(policy.get("stage_overrides", {})) == set(TOTAL_ORDER), "model policy must declare every controller stage", errors)

    expensive_roles = {"solution-architect", "pipeline-product", "pipeline-reviewer", "pipeline-browser-product"}
    for role in expensive_roles:
        require(policy["default_tier_by_role"].get(role) == "expensive", f"{role} must default to expensive", errors)
    require(policy["default_tier_by_role"].get("pipeline-dev") == "cheap", "pipeline-dev must default to cheap", errors)
    require(policy["default_tier_by_role"].get("pipeline-dispatcher") == "moderate", "pipeline-dispatcher must default to moderate", errors)
    require(policy["default_tier_by_role"].get("pipeline-ba") == "moderate", "pipeline-ba must default to moderate", errors)

    fixtures = [
        (
            {"stage": "S18", "role": "pipeline-dev", "traits": ["ui_change"], "risk_level": "low"},
            "codex",
            "cheap",
            "gpt-5.6-luna",
        ),
        (
            {"stage": "S18", "role": "pipeline-dev", "traits": ["database_change"], "risk_level": "high"},
            "codex",
            "moderate",
            "gpt-5.6-terra",
        ),
        (
            {"stage": "S13", "role": "solution-architect", "traits": ["new_domain"], "risk_level": "critical"},
            "claude",
            "expensive",
            "opus",
        ),
        (
            {"stage": "S25", "role": "pipeline-browser-product", "traits": ["ui_change"], "risk_level": "medium"},
            "cursor",
            "expensive",
            "sol-or-opus-equivalent",
        ),
        (
            {"stage": "S01", "role": "pipeline-dispatcher", "traits": ["bug"], "risk_level": "low"},
            "claude",
            "moderate",
            "sonnet",
        ),
    ]
    for packet, executor, tier, model in fixtures:
        actual = recommend_model(policy, packet, executor)
        require(actual["tier"] == tier, f"{packet['stage']} for {executor} must recommend tier {tier}", errors)
        require(actual["model"] == model, f"{packet['stage']} for {executor} must recommend model {model}", errors)

    dispatch = (ROOT / "scripts" / "pipeline" / "dispatch.py").read_text(encoding="utf-8")
    require("recommendation_for_packet" in dispatch, "dispatch must calculate model recommendation", errors)
    require("pipeline/model-policy.yml" in dispatch, "dispatch prompt must mention model policy path", errors)

    claude_dev = (ROOT / ".claude" / "agents" / "pipeline-dev.md").read_text(encoding="utf-8")
    require("model: haiku" in claude_dev, "Claude pipeline-dev default must be cheap haiku", errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("pipeline model policy ok: cheap code, moderate dispatch, expensive judgment stages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
