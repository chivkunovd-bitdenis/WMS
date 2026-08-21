# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-D01`
Stage: `B01`
Role: `pipeline-ba`
Recommended model: `gpt-5.6-terra` (`moderate`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-D01/state.json`

## Executor Rules

- Use .codex/skills/wms-pipeline-autopilot/SKILL.md if present; otherwise read AGENTS.md directly.
- If the user explicitly allowed multi-agents, spawn a worker only for this role and disjoint scope.
- Tell subagents not to push unless the owner explicitly asks for that.
- Do not fix bugs unless this exact stage and role authorize implementation.
- If packet status is `WAITING`, stop after the required start checks and report the blocker.
- Do not set `DONE` while `pipeline/pipeline.yml` status is not `ACTIVE`.
- Do not touch secrets, live deploy, or live WB/Ozon.

## Model Policy

Policy: `pipeline/model-policy.yml`
Tier: `moderate`
Recommended model: `gpt-5.6-terra`

Reasons:
- stage B01 / role pipeline-ba default tier is moderate

Rules:
- Do not upgrade above the recommendation unless the packet, owner, or fresh evidence shows a higher-risk class.
- Do not downgrade product, research, architecture, review or Product Browser stages.
- Simple implementation defaults to cheap; dangerous implementation escalates to moderate, not automatically to expensive.
- If the executor cannot select the exact named model, use the cheapest available equivalent at the same tier.

## Budget Policy

Policy: `pipeline/budget-policy.yml`
Stage tier budget: `1.25 USD` / `600000` tokens
Task budget: `8.0 USD` / `2500000` tokens
Wave budget: `35.0 USD` / `12000000` tokens
Hard stop: `True`; reason code `BUDGET_HARD_STOP`
Owner override marker: `PIPELINE_BUDGET_OVERRIDE: owner-approved`
Usage receipt fields: `task_id`, `stage`, `role`, `executor`, `model`, `tier`, `input_tokens`, `output_tokens`, `estimated_usd`, `agent_id`, `recorded_at`

Rules:
- Dispatcher includes the stage budget in every handoff prompt.
- A stage that reaches warning_ratio reports usage in its receipt.
- A stage that reaches hard_stop_ratio must stop and request owner override before more expensive work.
- Product, research, architecture, review and browser stages remain expensive when model-policy says so; budget pressure cannot downgrade judgment gates.

## Controller Packet

```json
{
  "task_id": "BLG-D01",
  "stage": "B01",
  "role": "pipeline-ba",
  "status": "WAITING",
  "traits": [
    "bug"
  ],
  "risk_level": "high",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
    "B01",
    "B02",
    "B03",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
    "S16",
    "S17",
    "S18",
    "S19",
    "S20",
    "S21",
    "S22",
    "S23",
    "S26"
  ],
  "done_stages": [
    "S01",
    "S02"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-D01",
  "backlog_item": {
    "id": "BLG-D01",
    "title": "Сбрасывать выбор заказов при смене фильтра и показывать состав пачки",
    "source_section": "D1",
    "business_meaning": "На экране списка заказов оператор может отметить заказы, затем сменить фильтр и сохранить невидимый выбор из предыдущей выборки. Из-за этого в одну поставку можно случайно собрать заказы разных селлеров или складов, хотя на экране видна только текущая часть списка. При смене фильтра система должна либо сбрасывать выбор, либо явно показывать весь состав будущей пачки и запрещать несовместимое объединение до создания поставки.",
    "type": "bug",
    "priority": "high",
    "status": "queued",
    "readiness": "needs_product_contract",
    "dependencies": [],
    "suggested_roles": [
      "BA",
      "Product",
      "screen-dev",
      "reviewer"
    ],
    "suggested_stages": [
      "S01",
      "S08",
      "S12",
      "S18"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 300,
    "output_tokens": 100,
    "estimated_usd": 0.0025
  },
  "blocked_by": [
    {
      "id": "BLK-PROD-002",
      "title": "Часть backlog описана как дефект, но не имеет полного контракта результата",
      "status": "open",
      "type": "product",
      "owner_role": "pipeline-ba",
      "resume_stage": "S08",
      "minimum_closure_artifact": "atomic feature cards with Given/When/Then, roles, data, negatives and visible business result"
    }
  ],
  "blocker": {
    "type": "FIXTURE",
    "reason_code": "REPRO_FIXTURE_REQUIRED",
    "details": "B01 requires isolated baseline reproduction fixture for: Сбрасывать выбор заказов при смене фильтра и показывать состав пачки. Backlog business_meaning describes the symptom, but no runnable fixture, test case, screen state, or observation log was supplied in the task packet.",
    "owner": "pipeline-ba",
    "created_at": "2026-08-21T00:27:44Z",
    "resume_stage": "B01"
  },
  "resume_condition": {
    "stage": "B01",
    "condition": "Provide runnable reproduction fixture or observation packet with baseline SHA, test data/screen, steps, expected/actual result and evidence path; then resume B01."
  },
  "rules": [
    "Read AGENTS.md, docs/process/PIPELINE-RU.md and pipeline/pipeline.yml first.",
    "Do not accept your own work.",
    "If status is WAITING, do not advance; report the blocker and wait for resume.",
    "If budget_enforced is true, advance requires usage receipt fields.",
    "If blocked_by is non-empty, do not pass the blocker resume stage without resolve-blocker evidence.",
    "Use python3 scripts/pipeline/run.py advance only for the stage you own.",
    "Do not set DONE while pipeline status is not ACTIVE."
  ]
}
```

## Required Start

```bash
python3 scripts/pipeline/run.py next --task-id BLG-D01
python3 scripts/pipeline/run.py validate --task-id BLG-D01
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-D01 --stage B01 --verdict <ALLOWED_VERDICT> --role pipeline-ba --agent <agent-id> --executor codex --model gpt-5.6-terra --tier moderate --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-D01
python3 scripts/pipeline/dispatch.py --task-id BLG-D01 --executor codex
```
