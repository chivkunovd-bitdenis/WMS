# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-I16`
Stage: `S13`
Role: `solution-architect`
Recommended model: `gpt-5.6-sol` (`expensive`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-I16/state.json`

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
- stage S13 / role solution-architect default tier is expensive

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
  "task_id": "BLG-I16",
  "stage": "S13",
  "role": "solution-architect",
  "status": "WAITING",
  "traits": [
    "database_change",
    "background_worker"
  ],
  "risk_level": "medium",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
    "S11",
    "S12",
    "S13",
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
    "S11",
    "S12"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-I16",
  "backlog_item": {
    "id": "BLG-I16",
    "title": "Сделать массовое завершение упаковки одной серверной операцией",
    "source_section": "I16",
    "business_meaning": "Кнопка «Всё упаковано» последовательно отправляет отдельный запрос для каждой строки задания и ждёт каждый ответ. На крупной поставке экран на десятки секунд выглядит зависшим, оператор не видит прогресс и может повторно нажать кнопку или решить, что операция сорвалась. Нужна одна серверная массовая операция с защитой от повторов, корректной обработкой частичных ошибок и видимым прогрессом или быстрым итогом для всей поставки.",
    "type": "performance",
    "priority": "medium",
    "status": "queued",
    "readiness": "needs_technical_contract",
    "dependencies": [],
    "suggested_roles": [
      "solution-architect",
      "screen-dev",
      "reviewer"
    ],
    "suggested_stages": [
      "S02",
      "S12",
      "S18",
      "S23"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 89300,
    "output_tokens": 6500,
    "estimated_usd": 0.8925
  },
  "blocked_by": [],
  "blocker": {
    "type": "OWNER_INPUT",
    "reason_code": "IMPACT_PROFILE_INCOMPLETE",
    "details": "S13 cannot pass: runtime S08 and ui_change stages S09/S10/S24/S25 are absent from the controller profile although the accepted operation requires durable runtime behavior and visible accepted/progress/partial/final read-back.",
    "owner": "pipeline-dispatcher",
    "created_at": "2026-08-21T02:36:58Z",
    "resume_stage": "S13"
  },
  "resume_condition": {
    "stage": "S13",
    "condition": "Pipeline dispatcher reclassifies BLG-I16 through the controller, adds S08 and ui_change stages, obtains valid S08/S09/S10 and any invalidated S11/S12 receipts, then returns a refreshed packet to S13."
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
python3 scripts/pipeline/run.py next --task-id BLG-I16
python3 scripts/pipeline/run.py validate --task-id BLG-I16
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-I16 --stage S13 --verdict <ALLOWED_VERDICT> --role solution-architect --agent <agent-id> --executor codex --model gpt-5.6-sol --tier expensive --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-I16
python3 scripts/pipeline/dispatch.py --task-id BLG-I16 --executor codex
```
