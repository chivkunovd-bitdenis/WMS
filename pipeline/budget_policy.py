"""Budget guardrails for Pipeline v2 dispatch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUDGET_POLICY_PATH = ROOT / "pipeline" / "budget-policy.yml"


def load_budget_policy() -> dict[str, Any]:
    return json.loads(BUDGET_POLICY_PATH.read_text(encoding="utf-8"))


def budget_for_tier(policy: dict[str, Any], tier: str) -> dict[str, Any]:
    tier_limit = policy["limits"]["stage_tier"][tier]
    return {
        "policy_path": "pipeline/budget-policy.yml",
        "currency": policy["currency"],
        "tier": tier,
        "stage_max_usd": tier_limit["max_usd"],
        "stage_max_tokens": tier_limit["max_tokens"],
        "task_max_usd": policy["limits"]["task"]["max_usd"],
        "task_max_tokens": policy["limits"]["task"]["max_tokens"],
        "wave_max_usd": policy["limits"]["wave"]["max_usd"],
        "wave_max_tokens": policy["limits"]["wave"]["max_tokens"],
        "warning_ratio": policy["limits"]["task"]["warning_ratio"],
        "hard_stop": policy["hard_stop"],
        "usage_receipt_required_fields": policy["usage_receipt"]["required_fields"],
        "owner_override": policy["owner_override"],
        "rules": policy["rules"],
    }


def recommendation_for_tier(tier: str) -> dict[str, Any]:
    return budget_for_tier(load_budget_policy(), tier)
