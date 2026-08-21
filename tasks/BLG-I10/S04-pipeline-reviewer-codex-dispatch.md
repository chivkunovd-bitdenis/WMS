# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-I10`
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
- `tasks/BLG-I10/state.json`

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
  "task_id": "BLG-I10",
  "stage": "S04",
  "role": "pipeline-reviewer",
  "status": "WAITING",
  "traits": [
    "new_module"
  ],
  "risk_level": "high",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
    "S03",
    "S04",
    "S05",
    "S06",
    "S07",
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
  "backlog_item_id": "BLG-I10",
  "backlog_item": {
    "id": "BLG-I10",
    "title": "Сформировать продуктовую модель склад плюс ячейка",
    "source_section": "I10",
    "business_meaning": "Сейчас склад и ячейка участвуют в разных операциях непоследовательно: где-то система заставляет выбирать их без пользы, а где-то позволяет работать с остатком не того склада. В сценарии одного реального склада оператор не должен делать лишний выбор, а при нескольких складах система должна явно учитывать место хранения и не позволять создавать или отгружать товар со склада, где его нет. Ячейка должна помогать найти товар и учитывать размещение, но не должна быть обязательным полем короба или блокировать проведение фактической отгрузки без отдельной бизнес-причины.",
    "type": "new_module",
    "priority": "high",
    "status": "blocked",
    "readiness": "needs_product_decision",
    "dependencies": [],
    "suggested_roles": [
      "Product",
      "BA",
      "solution-architect"
    ],
    "suggested_stages": [
      "S01",
      "S02",
      "S12"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 60300,
    "output_tokens": 10100,
    "estimated_usd": 0.4525
  },
  "blocked_by": [],
  "blocker": {
    "type": "ORACLE_CONFLICT",
    "reason_code": "RESEARCH_REWORK_WAREHOUSE_POOL_BOUNDARIES",
    "details": "S04 RESEARCH_REWORK: S03 does not close many-to-one WB-to-physical stock allocation and publish safety, legacy auto-created FBS WB warehouse migration, cross-warehouse cell scan semantics, warehouse-context switch boundaries, or marking-pool versus physical-reserve ownership.",
    "owner": "pipeline-ba",
    "created_at": "2026-08-21T00:48:56Z",
    "resume_stage": "S04"
  },
  "resume_condition": {
    "stage": "S04",
    "condition": "Revise MODULE-DOSSIER and its capability matrix with explicit allocation/publish/reserve cardinality, legacy FBS WB warehouse reconciliation and rollback, cross-warehouse scan policy, context source-of-truth and switch boundaries, and marking-pool/box applicability; then resume S04 for independent re-review."
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
python3 scripts/pipeline/run.py next --task-id BLG-I10
python3 scripts/pipeline/run.py validate --task-id BLG-I10
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-I10 --stage S04 --verdict <ALLOWED_VERDICT> --role pipeline-reviewer --agent <agent-id> --executor codex --model gpt-5.6-sol --tier expensive --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-I10
python3 scripts/pipeline/dispatch.py --task-id BLG-I10 --executor codex
```
