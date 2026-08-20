# AGENT-RUNBOOK — ночная очередь WMS-багов на 2026-08-21

Этот runbook для завтрашнего `pipeline-dispatcher`. Он не запускает live deploy
и не требует секретов.

## 0. Перед стартом

1. Работать из `/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2`.
2. Проверить `git status`; не stage-ить чужие изменения вне
   `tasks/20260820-night-bug-queue/`.
3. Прочитать `AGENTS.md`, `docs/process/PIPELINE-HOLES-RU.md`,
   `pipeline/pipeline.yml`, `docs/process/INCIDENTS-REGISTRY-RU.md`.
4. Помнить: Pipeline v2 в `IMPLEMENTATION_IN_PROGRESS`, значит старый Product
   gate всё ещё действует до `PIPELINE_ACTIVATION_APPROVED`.

## 1. Открыть карточки

Запускать команды по одной. Каждая создаст controller state и snapshot
`tasks/<task-id>/state.json`.

```bash
python3 scripts/pipeline/run.py open --task-id BUG-WMS-PV2-001 --source "2026-08-21 night queue: exact-SHA deploy residue from PIPELINE-HOLES P0 and incidents I15-I17; no live deploy" --traits bug,pipeline_change,release_change --risk-level critical

python3 scripts/pipeline/run.py open --task-id BUG-WMS-PV2-002 --source "2026-08-21 night queue: fail-closed WB/Ozon test egress; no live marketplace calls" --traits bug,external_contract,background_worker,pipeline_change --risk-level critical

python3 scripts/pipeline/run.py open --task-id BUG-WMS-TESTSTACK-001 --source "2026-08-21 night queue: honest WMS test stack, WMS_AUTO_CREATE_SCHEMA/create_all must not replace migrations" --traits bug,database_change,pipeline_change --risk-level high

python3 scripts/pipeline/run.py open --task-id BUG-WMS-FBS-CZ-001 --source "2026-08-21 night queue: FBS Chestny Znak marking dispatch eligibility, preserve WB/CZ oracle, no live WB calls" --traits bug,external_contract,tenant_sensitive,ui_change --risk-level critical

python3 scripts/pipeline/run.py open --task-id BUG-WMS-FBS-PRINT-001 --source "2026-08-21 night queue: FBS label print quantity and supply scope, no live deploy" --traits bug,ui_change,print --risk-level high
```

## 2. Роли и переходы

- `pipeline-dispatcher`: открыть карточку, проверить traits/risk, выдать
  workspace только после нужных receipts.
- `pipeline-ba`: воспроизвести баг, зафиксировать expected behavior и oracle.
- `pipeline-dev`: чинить только после Product approval, ровно один card scope.
- `pipeline-reviewer`: проверить diff, тесты, границы, миграции и egress guard.
- `pipeline-browser-product`: принимать только реальный operator/internal flow;
  Playwright и curl не заменяют browser verdict.

Если stage не применим, он закрывается только controller receipt с причиной, а
не текстовой пометкой в чате.

## 3. Ночные ограничения

- No live deploy. Для release-карточки допустимы только manifest, dry-run,
  staging/local smoke и typed blockers.
- No live WB/Ozon calls. Внешний контракт проверяется emulator/sandbox target,
  явно записанным в evidence.
- No secrets. Evidence очищается от токенов, cookies и API keys.
- No mixed fixes. Если карточка тянет соседний баг, dispatcher открывает новый
  card или возвращает в `S12 TASK_CUT`.

## 4. Утренний отчёт

К 2026-08-21 утром по каждой карточке отдать одну строку:

```text
<task-id>: <status> · current_stage=<stage> · owner=<role> · blocker=<нет|тип> · evidence=<path|нет>
```

Статус “готово” разрешён только при commit SHA, зелёных обязательных проверках и
нужных Product/Browser verdicts. Для release-карточки production deploy отдельно
требует owner approval exact SHA.
