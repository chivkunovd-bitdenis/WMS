"""Model selection policy for Pipeline v2 dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_POLICY_PATH = ROOT / "pipeline" / "model-policy.yml"
TIER_ORDER = {"cheap": 0, "moderate": 1, "expensive": 2}


def load_model_policy() -> dict[str, Any]:
    return json.loads(MODEL_POLICY_PATH.read_text(encoding="utf-8"))


def max_tier(left: str, right: str) -> str:
    return left if TIER_ORDER[left] >= TIER_ORDER[right] else right


def rule_matches(rule: dict[str, Any], packet: dict[str, Any]) -> bool:
    roles = rule.get("roles")
    stages = rule.get("stages")
    traits = rule.get("traits")
    risk_levels = rule.get("risk_levels")
    if roles and packet.get("role") not in roles:
        return False
    if stages and packet.get("stage") not in stages:
        return False
    if traits and not set(packet.get("traits", [])).intersection(traits):
        return False
    if risk_levels and packet.get("risk_level") not in risk_levels:
        return False
    return True


def recommend_model(policy: dict[str, Any], packet: dict[str, Any], executor: str) -> dict[str, Any]:
    if executor not in policy["executors"]:
        raise ValueError(f"unknown executor for model policy: {executor}")
    stage = packet["stage"]
    role = packet["role"]
    tier = policy["stage_overrides"].get(stage) or policy["default_tier_by_role"][role]
    reasons = [f"stage {stage} / role {role} default tier is {tier}"]
    for rule in policy.get("escalation_rules", []):
        if not rule_matches(rule, packet):
            continue
        old_tier = tier
        tier = max_tier(tier, rule["minimum_tier"])
        if tier != old_tier:
            reasons.append(f"{rule['id']}: {rule['reason']}")
    return {
        "policy_path": "pipeline/model-policy.yml",
        "executor": executor,
        "tier": tier,
        "model": policy["executors"][executor][tier],
        "reasons": reasons,
        "rules": policy.get("rules", []),
    }


def recommendation_for_packet(packet: dict[str, Any], executor: str) -> dict[str, Any]:
    return recommend_model(load_model_policy(), packet, executor)
