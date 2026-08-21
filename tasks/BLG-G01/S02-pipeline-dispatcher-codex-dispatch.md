# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-G01`
Stage: `S02`
Role: `pipeline-dispatcher`
Recommended model: `gpt-5.6-terra` (`moderate`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-G01/state.json`

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
- stage S02 / role pipeline-dispatcher default tier is moderate

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
  "task_id": "BLG-G01",
  "stage": "S02",
  "role": "pipeline-dispatcher",
  "status": "RUNNING",
  "traits": [
    "new_domain",
    "external_contract"
  ],
  "risk_level": "medium",
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
    "S01"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-G01",
  "backlog_item": {
    "id": "BLG-G01",
    "title": "Подготовить архитектурное решение для запуска Ozon",
    "source_section": "G",
    "business_meaning": "Подключение Ozon вводит новый маркетплейс с собственными заказами, статусами, складами, этикетками и ограничениями API. Если сразу копировать текущую логику Wildberries, различия контрактов быстро разойдутся по экранам и данным и приведут к дорогой переделке. Сначала нужно описать бизнес-процесс Ozon, границы общей и отдельной логики, варианты архитектуры, риски интеграции и первую полезную версию, а код начинать только после решения владельца.",
    "type": "new_domain",
    "priority": "medium",
    "status": "queued",
    "readiness": "needs_architecture_decision",
    "dependencies": [
      "BLG-F01"
    ],
    "suggested_roles": [
      "solution-architect",
      "Product",
      "BA"
    ],
    "suggested_stages": [
      "S01",
      "S02",
      "S12"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 120,
    "output_tokens": 40,
    "estimated_usd": 0.001
  },
  "blocked_by": [
    {
      "id": "BLK-ARCH-003",
      "title": "Ozon и аналитический модуль требуют dossier/ARCH до разработки",
      "status": "open",
      "type": "architecture",
      "owner_role": "solution-architect",
      "resume_stage": "S03",
      "minimum_closure_artifact": "research dossier, role needs, data-source/freshness/access contract and ARCH approval before Dev"
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
python3 scripts/pipeline/run.py next --task-id BLG-G01
python3 scripts/pipeline/run.py validate --task-id BLG-G01
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-G01 --stage S02 --verdict <ALLOWED_VERDICT> --role pipeline-dispatcher --agent <agent-id> --executor codex --model gpt-5.6-terra --tier moderate --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-G01
python3 scripts/pipeline/dispatch.py --task-id BLG-G01 --executor codex
```
