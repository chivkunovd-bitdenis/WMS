# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-D19`
Stage: `S01`
Role: `pipeline-dispatcher`
Recommended model: `gpt-5.6-terra` (`moderate`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-D19/state.json`

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
- stage S01 / role pipeline-dispatcher default tier is moderate

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
  "task_id": "BLG-D19",
  "stage": "S01",
  "role": "pipeline-dispatcher",
  "status": "QUEUED",
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
  "done_stages": [],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-D19",
  "backlog_item": {
    "id": "BLG-D19",
    "title": "Исправить пагинацию импорта каталога WB",
    "source_section": "D19",
    "business_meaning": "Импорт каталога Wildberries сейчас может останавливаться после первой сотни карточек из-за неверного понимания поля cursor.total. В результате продавец видит в WMS только часть ассортимента и не может выбрать отсутствующие товары в складских операциях. Импорт должен последовательно забирать все страницы до фактического конца выдачи и быть проверен на каталогах ровно из 100, 101 и большого количества карточек.",
    "type": "external_contract",
    "priority": "critical",
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
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_usd": 0.0
  },
  "blocked_by": [
    {
      "id": "BLK-RESEARCH-001",
      "title": "Внешние контракты WB/ЧЗ не собраны по полям и статусам",
      "status": "open",
      "type": "research",
      "owner_role": "pipeline-research",
      "resume_stage": "S03",
      "minimum_closure_artifact": "versioned external-contract dossier with fields, statuses, pagination, errors and emulator/sandbox proof"
    },
    {
      "id": "BLK-INTEGRATION-001",
      "title": "Импорт WB ограничен и не поддерживает автономную актуализацию каталога",
      "status": "open",
      "type": "integration",
      "owner_role": "pipeline-product",
      "resume_stage": "S03",
      "minimum_closure_artifact": "WB pagination/search/sync contract and e2e for item outside first page"
    }
  ],
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
python3 scripts/pipeline/run.py next --task-id BLG-D19
python3 scripts/pipeline/run.py validate --task-id BLG-D19
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-D19 --stage S01 --verdict <ALLOWED_VERDICT> --role pipeline-dispatcher --agent <agent-id> --executor codex --model gpt-5.6-terra --tier moderate --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-D19
python3 scripts/pipeline/dispatch.py --task-id BLG-D19 --executor codex
```
