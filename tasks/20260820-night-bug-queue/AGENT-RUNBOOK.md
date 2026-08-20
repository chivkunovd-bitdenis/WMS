# AGENT-RUNBOOK — ночная очередь WMS-багов на 2026-08-21

Этот runbook для завтрашнего `pipeline-dispatcher`. Очередь имеет статус
`WAITING` с блокером `OWNER_INPUT/QUEUED_NOT_STARTED`: баги не начаты, receipts
и verdicts отсутствуют. Runbook не запускает live deploy и не требует секретов.

## 0. Перед стартом

1. Работать из `/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2`.
2. Проверить `git status`; не stage-ить чужие изменения вне своей карточки и
   pipeline-файлов, которые прямо требуются текущей стадией.
3. Прочитать `AGENTS.md`, `docs/process/PIPELINE-HOLES-RU.md`,
   `pipeline/pipeline.yml`, `docs/process/INCIDENTS-REGISTRY-RU.md`.
4. Помнить: Pipeline v2 в `IMPLEMENTATION_IN_PROGRESS`, значит старый Product
   gate всё ещё действует до `PIPELINE_ACTIVATION_APPROVED`.

## 1. Граница owner approval

До письменного owner approval на конкретный `<task-id>` не выполнять команды из
следующего раздела: не делать `resume`, не переводить стадию и не создавать
receipt. Одобрение на исследование не является одобрением на фикс.

После открытия карточки разрешены только S01/S02 и bug-исследование B01–B03.
Разработчик не начинает `S18 DEVELOPMENT`, пока есть оба условия:

1. controller receipt `PRODUCT_APPROVED_FOR_DEV`;
2. отдельное письменное owner approval на начало исправления именно этой карточки.

## 2. Снять удержание с одобренной карточки без фикса

После owner approval запускать только одну выбранную карточку. Команды снимут
`WAITING`, покажут следующий stage и запишут dispatch prompt для выбранного
исполнителя; они не вносят фикс.

```bash
python3 scripts/pipeline/run.py resume --task-id <task-id> --by owner
python3 scripts/pipeline/run.py next --task-id <task-id>
python3 scripts/pipeline/dispatch.py --task-id <task-id> --executor <codex|claude|cursor>
```

## 3. Роли и переходы

- `pipeline-dispatcher`: открыть карточку, проверить traits/risk, выдать
  workspace только после нужных receipts.
- `pipeline-ba`: воспроизвести баг, зафиксировать expected behavior и oracle.
- `pipeline-dev`: чинить ровно один card scope и только после product receipt и
  отдельного owner approval на начало исправления.
- `pipeline-reviewer`: проверить diff, тесты, границы, миграции и egress guard.
- `pipeline-browser-product`: принимать только реальный operator/internal flow;
  Playwright и curl не заменяют browser verdict.

Если stage не применим, он закрывается только controller receipt с причиной, а
не текстовой пометкой в чате.

## 4. Ночные ограничения

- No live deploy. Для release-карточки допустимы только manifest, dry-run,
  staging/local smoke и typed blockers.
- No live WB/Ozon calls. Внешний контракт проверяется emulator/sandbox target,
  явно записанным в evidence.
- No secrets. Evidence очищается от токенов, cookies и API keys.
- No mixed fixes. Если карточка тянет соседний баг, dispatcher открывает новый
  card или возвращает в `S12 TASK_CUT`.

## 5. Утренний отчёт

К 2026-08-21 утром по каждой карточке отдать одну строку:

```bash
python3 scripts/pipeline/run.py report
```

```text
<task-id>: <status> · current_stage=<stage> · owner=<role> · blocker=<нет|тип> · evidence=<path|нет>
```

Статус “готово” разрешён только при commit SHA, зелёных обязательных проверках и
нужных Product/Browser verdicts. Для release-карточки production deploy отдельно
требует owner approval exact SHA.
