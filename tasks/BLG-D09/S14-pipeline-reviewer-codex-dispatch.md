# WMS Pipeline Dispatch

Executor: `codex`
Task: `BLG-D09`
Stage: `S14`
Role: `pipeline-reviewer`
Recommended model: `gpt-5.6-sol` (`expensive`)

## Read First

- `.codex/skills/wms-pipeline-autopilot/SKILL.md`
- `AGENTS.md`
- `docs/process/PIPELINE-RU.md`
- `pipeline/pipeline.yml`
- `pipeline/model-policy.yml`
- `pipeline/budget-policy.yml`
- `tasks/BLG-D09/state.json`

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
- stage S14 / role pipeline-reviewer default tier is expensive

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
  "task_id": "BLG-D09",
  "stage": "S14",
  "role": "pipeline-reviewer",
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
    "S13"
  ],
  "worktree": "/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2",
  "branch": "codex/wms-pipeline-unified-v2-20260820",
  "base_sha": "69c271678782d7dcfa39df97cd905cbee1678727",
  "wave_id": "wave-a1b311d18f07",
  "backlog_item_id": "BLG-D09",
  "backlog_item": {
    "id": "BLG-D09",
    "title": "Сделать prod-update exact-SHA и проверять смену bundle",
    "source_section": "D9, I18",
    "business_meaning": "Текущий процесс обновления production может собрать не тот коммит или оставить браузеру старый фронтенд-пакет, хотя команда обновления завершилась без ошибки. Тогда команда считает исправление выкаченным, а оператор продолжает работать на прежней версии. Обновление должно принимать точный Git SHA, подтверждать именно этот SHA на сервере и проверять, что браузер действительно получил новый bundle, то есть новый собранный пакет интерфейса.",
    "type": "release_change",
    "priority": "high",
    "status": "queued",
    "readiness": "needs_release_contract",
    "dependencies": [],
    "suggested_roles": [
      "solution-architect",
      "DevOps",
      "reviewer"
    ],
    "suggested_stages": [
      "S02",
      "S12",
      "S18",
      "S25",
      "S28"
    ]
  },
  "budget_enforced": true,
  "budget_usage": {
    "input_tokens": 165300,
    "output_tokens": 12900,
    "estimated_usd": 1.0725
  },
  "blocked_by": [
    {
      "id": "BLK-RELEASE-001",
      "title": "Cache-control/D12 не включён в browser/release proof",
      "status": "open",
      "type": "release",
      "owner_role": "release-owner",
      "resume_stage": "S23",
      "minimum_closure_artifact": "browser/release receipt with exact SHA, asset URL/hash, cache headers and hard reload proof"
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
python3 scripts/pipeline/run.py next --task-id BLG-D09
python3 scripts/pipeline/run.py validate --task-id BLG-D09
```

## Required Finish

Only after completing the owned stage:

```bash
python3 scripts/pipeline/run.py advance --task-id BLG-D09 --stage S14 --verdict <ALLOWED_VERDICT> --role pipeline-reviewer --agent <agent-id> --executor codex --model gpt-5.6-sol --tier expensive --input-tokens <INPUT_TOKENS> --output-tokens <OUTPUT_TOKENS> --estimated-usd <USD>
python3 scripts/pipeline/run.py packet --task-id BLG-D09
python3 scripts/pipeline/dispatch.py --task-id BLG-D09 --executor codex
```
