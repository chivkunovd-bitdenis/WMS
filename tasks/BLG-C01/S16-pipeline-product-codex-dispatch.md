# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-C01`
Stage: `S16`
Role: `pipeline-product`
Recommended model: `gpt-5.6-sol` (`expensive`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-C01/state.json`

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
- stage S16 / role pipeline-product default tier is expensive

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
  "task_id": "BLG-C01",
  "stage": "S16",
  "role": "pipeline-product",
  "status": "RUNNING",
  "traits": [
    "release_change"
  ],
  "risk_level": "high",
  "model_policy": "pipeline/model-policy.yml",
  "required_stages": [
    "S01",
    "S02",
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
    "S26",
    "S27",
    "S28"
  ],
  "done_stages": [
    "S01",
    "S02",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-C01",
  "backlog_item": {
    "id": "BLG-C01",
    "title": "Выкатить необязательную упаковку FBS после owner decision",
    "source_section": "C1",
    "business_meaning": "Изменение, позволяющее проводить часть FBS-поставок без обязательного задания упаковки, уже подготовлено в отдельной ветке, но ещё не подтверждено как работающее в production. Оно должно убрать искусственную остановку там, где упаковка не является обязательным этапом бизнес-процесса, не ломая поставки, которым упаковка действительно нужна. После отдельного разрешения владельца требуется выкатить точный одобренный SHA, применить необходимые миграции и пройти живой операторский сценарий без упаковки; сама карточка не является разрешением на deploy.",
    "type": "release_change",
    "priority": "high",
    "status": "ready_for_release",
    "readiness": "waiting_owner_release",
    "dependencies": [],
    "suggested_roles": [
      "Product",
      "DevOps",
      "reviewer"
    ],
    "suggested_stages": [
      "S15",
      "S25",
      "S28"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 375300,
    "output_tokens": 25000,
    "estimated_usd": 2.3525
  },
  "blocked_by": [],
  "blocker": null,
  "resume_condition": null,
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
python3 scripts/pipeline/run.py next --task-id BLG-C01
python3 scripts/pipeline/run.py validate --task-id BLG-C01
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-C01 --stage S16 --verdict <ALLOWED_VERDICT> --role pipeline-product --agent <agent-id> --executor codex --model gpt-5.6-sol --tier expensive --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-C01
python3 scripts/pipeline/dispatch.py --task-id BLG-C01 --executor codex
```
