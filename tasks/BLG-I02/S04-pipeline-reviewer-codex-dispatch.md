# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-I02`
Stage: `S04`
Role: `pipeline-reviewer`
Recommended model: `gpt-5.6-sol` (`expensive`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-I02/state.json`

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
Tier: `expensive`
Recommended model: `gpt-5.6-sol`

Reasons:
- stage S04 / role pipeline-reviewer default tier is expensive

Rules:
- Do not upgrade above the recommendation unless the packet, owner, or fresh evidence shows a higher-risk class.
- Do not downgrade product, research, architecture, review or Product Browser stages.
- Simple implementation defaults to cheap; dangerous implementation escalates to moderate, not automatically to expensive.
- If the executor cannot select the exact named model, use the cheapest available equivalent at the same tier.

## Budget Policy

Policy: `pipeline/budget-policy.yml`
Stage tier budget: `3.0 USD` / `900000` tokens
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
  "task_id": "BLG-I02",
  "stage": "S04",
  "role": "pipeline-reviewer",
  "status": "WAITING",
  "traits": [
    "external_contract"
  ],
  "risk_level": "critical",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
    "S03",
    "S04",
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
    "S02",
    "S03"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-I02",
  "backlog_item": {
    "id": "BLG-I02",
    "title": "Сохранять вердикты WB и запрещать оптимистичный dispatch",
    "source_section": "I2",
    "business_meaning": "Система может продолжать отгрузку, не сохранив точный ответ Wildberries о проверке маркировки, и фактически считать отсутствие ошибки разрешением. Это создаёт ложный зелёный статус: оператор думает, что заказ допустим к сдаче, хотя подтверждения маркетплейса нет. Каждый вердикт Wildberries нужно хранить вместе со временем и причиной, а dispatch, то есть передача заказа дальше, должен разрешаться только по явно подтверждённому положительному состоянию.",
    "type": "external_contract",
    "priority": "critical",
    "status": "queued",
    "readiness": "needs_product_contract",
    "dependencies": [
      "BLG-I01",
      "BLG-D03"
    ],
    "suggested_roles": [
      "Product",
      "BA",
      "solution-architect",
      "screen-dev",
      "reviewer"
    ],
    "suggested_stages": [
      "S01",
      "S02",
      "S12",
      "S18",
      "S26"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 32300,
    "output_tokens": 7100,
    "estimated_usd": 0.6525
  },
  "blocked_by": [],
  "blocker": {
    "type": "ORACLE_CONFLICT",
    "reason_code": "RESEARCH_REWORK_WB_VERDICT_CONTRACT",
    "details": "S04 RESEARCH_REWORK: 409 MetaValidationFail is a partial negative delivery-attempt result, not a complete projection replacement; the S03 required per-observation shape cannot represent bodyless 204 or errors without inventing meta verdicts; current WB docs apply x10 accounting to all 4XX and the metaDetails release note is misdated.",
    "owner": "pipeline-ba",
    "created_at": "2026-08-21T00:48:50Z",
    "resume_stage": "S04"
  },
  "resume_condition": {
    "stage": "S04",
    "condition": "Revise S03 to separate attempt outcomes from zero-or-more verdict rows, preserve 409 as an append-only partial negative result, record 204 without synthetic per-key decisions, correct all-4XX x10 accounting and the 31.03.2026 FBS release-note provenance; then rerun independent S04."
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
python3 scripts/pipeline/run.py next --task-id BLG-I02
python3 scripts/pipeline/run.py validate --task-id BLG-I02
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-I02 --stage S04 --verdict <ALLOWED_VERDICT> --role pipeline-reviewer --agent <agent-id> --executor codex --model gpt-5.6-sol --tier expensive --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-I02
python3 scripts/pipeline/dispatch.py --task-id BLG-I02 --executor codex
```
