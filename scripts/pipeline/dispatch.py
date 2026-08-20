#!/usr/bin/env python3
"""Write a role handoff prompt for Codex, Claude or Cursor.

This script does not launch agents. It turns the controller's next-stage packet
into a copy-pasteable prompt and stores it under tasks/<task-id>/.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.controller import load_state, next_stage_packet, write_json  # noqa: E402
from pipeline.budget_policy import recommendation_for_tier  # noqa: E402
from pipeline.model_policy import recommendation_for_packet  # noqa: E402


EXECUTOR_GUIDES = {
    "codex": [
        "Use .codex/skills/wms-pipeline-autopilot/SKILL.md if present; otherwise read AGENTS.md directly.",
        "If the user explicitly allowed multi-agents, spawn a worker only for this role and disjoint scope.",
        "Tell subagents not to push unless the owner explicitly asks for that.",
    ],
    "claude": [
        "Use the matching .claude/agents/<role>.md instruction.",
        "Launch only the role named in this packet; do not let Dev act as Product or Reviewer.",
        "Do not use Playwright as Product Browser acceptance.",
    ],
    "cursor": [
        "Use .cursor/skills/wms-pipeline-autopilot/SKILL.md.",
        "Follow controller next/advance commands exactly; do not edit state files manually.",
        "Keep task scope isolated from unrelated queue cards.",
    ],
}


def existing_guides(role: str, executor: str) -> list[str]:
    candidates = {
        "codex": [
            ".codex/skills/wms-pipeline-autopilot/SKILL.md",
            "AGENTS.md",
        ],
        "claude": [
            f".claude/agents/{role}.md",
            "AGENTS.md",
        ],
        "cursor": [
            ".cursor/skills/wms-pipeline-autopilot/SKILL.md",
            "AGENTS.md",
        ],
    }[executor]
    return [path for path in candidates if (ROOT / path).exists()]


def build_prompt(task_id: str, executor: str) -> tuple[dict, str]:
    state = load_state(task_id)
    packet = next_stage_packet(state)
    model_recommendation = recommendation_for_packet(packet, executor)
    budget_recommendation = recommendation_for_tier(model_recommendation["tier"])
    guides = existing_guides(packet["role"], executor)
    guide_lines = "\n".join(f"- `{path}`" for path in guides) or "- `AGENTS.md`"
    executor_lines = "\n".join(f"- {line}" for line in EXECUTOR_GUIDES[executor])
    model_reason_lines = "\n".join(f"- {line}" for line in model_recommendation["reasons"])
    model_rule_lines = "\n".join(f"- {line}" for line in model_recommendation["rules"])
    budget_rule_lines = "\n".join(f"- {line}" for line in budget_recommendation["rules"])
    usage_fields = ", ".join(f"`{field}`" for field in budget_recommendation["usage_receipt_required_fields"])
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    prompt = f"""# WMS Pipeline Dispatch

Executor: `{executor}`
Task: `{task_id}`
Stage: `{packet["stage"]}`
Role: `{packet["role"]}`
Recommended model: `{model_recommendation["model"]}` (`{model_recommendation["tier"]}`)

## Read First

{guide_lines}
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/{task_id}/state.json`

## Executor Rules

{executor_lines}
- Do not fix bugs unless this exact stage and role authorize implementation.
- If packet status is `WAITING`, stop after the required start checks and report the blocker.
- Do not set `DONE` while `pipeline/pipeline.yml` status is not `ACTIVE`.
- Do not touch secrets, live deploy, or live WB/Ozon.

## Model Policy

Policy: `{model_recommendation["policy_path"]}`
Tier: `{model_recommendation["tier"]}`
Recommended model: `{model_recommendation["model"]}`

Reasons:
{model_reason_lines}

Rules:
{model_rule_lines}

## Budget Policy

Policy: `{budget_recommendation["policy_path"]}`
Stage tier budget: `{budget_recommendation["stage_max_usd"]} {budget_recommendation["currency"]}` / `{budget_recommendation["stage_max_tokens"]}` tokens
Task budget: `{budget_recommendation["task_max_usd"]} {budget_recommendation["currency"]}` / `{budget_recommendation["task_max_tokens"]}` tokens
Wave budget: `{budget_recommendation["wave_max_usd"]} {budget_recommendation["currency"]}` / `{budget_recommendation["wave_max_tokens"]}` tokens
Hard stop: `{budget_recommendation["hard_stop"]["enabled"]}`; reason code `{budget_recommendation["hard_stop"]["reason_code"]}`
Owner override marker: `{budget_recommendation["owner_override"]["marker"]}`
Usage receipt fields: {usage_fields}

Rules:
{budget_rule_lines}

## Controller Packet

```json
{packet_json}
```

## Required Start

```bash
python3 scripts/pipeline/run.py next --task-id {task_id}
python3 scripts/pipeline/run.py validate --task-id {task_id}
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id {task_id} --stage {packet["stage"]} --verdict <ALLOWED_VERDICT> --role {packet["role"]} --agent <agent-id> --executor {executor} --model {model_recommendation["model"]} --tier {model_recommendation["tier"]} --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id {task_id}
python3 scripts/pipeline/dispatch.py --task-id {task_id} --executor {executor}
```
"""
    return packet, prompt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--executor", choices=sorted(EXECUTOR_GUIDES), required=True)
    args = parser.parse_args(argv)

    packet, prompt = build_prompt(args.task_id, args.executor)
    out_path = ROOT / "tasks" / args.task_id / f"{packet['stage']}-{packet['role']}-{args.executor}-dispatch.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")
    write_json(ROOT / "tasks" / args.task_id / f"{packet['stage']}-{packet['role']}-packet.json", packet)
    print(str(out_path.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
