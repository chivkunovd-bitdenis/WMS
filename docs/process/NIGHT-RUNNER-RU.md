# Night-runner Pipeline v2

`scripts/pipeline/night_runner.py` — исполнительный host-loop поверх WMS Pipeline v2 controller.
Он закрывает дыру между `start-wave`/`dispatch.py` и реальной ночной работой: сам берёт
`next`, делает безопасные механические переходы, создаёт handoff prompt для роли, при наличии
executor hook запускает внешнего исполнителя и после каждого шага валидирует task state.

## Что он делает

Runner работает только через публичные команды контроллера:

```bash
python3 scripts/pipeline/run.py next --task-id <task-id>
python3 scripts/pipeline/run.py advance --task-id <task-id> ...
python3 scripts/pipeline/run.py validate --task-id <task-id>
python3 scripts/pipeline/dispatch.py --task-id <task-id> --executor codex
```

Он автоматически продвигает только содержательно безопасные dispatcher stages:

- `S01` → `TASK_INTAKE_READY`;
- `S02` → `IMPACT_CLASSIFIED`.

BA, Product, Research, Architecture, Dev, Review и Browser Product stages runner не
закрывает “зелёной кнопкой”. Для них он пишет dispatch prompt и, если передан
`--executor-command`, запускает внешний executor с переменными окружения:

- `WMS_PIPELINE_TASK_ID`;
- `WMS_PIPELINE_STAGE`;
- `WMS_PIPELINE_ROLE`;
- `WMS_PIPELINE_DISPATCH`;
- `WMS_PIPELINE_EXECUTOR`;
- `WMS_PIPELINE_AGENT_ID`.

Именно внешний executor должен прочитать dispatch prompt, создать stage artifact и вызвать
`advance` с usage receipt. Если executor command не задан, runner оставляет stage в состоянии
`handoff_ready`, а не имитирует работу роли.

## Команды

План/dispatch без изменения state:

```bash
python3 scripts/pipeline/night_runner.py --wave-id wave-a1b311d18f07 --max-workers 8 --max-cycles 1
```

Исполнительный цикл с автоматическим S01/S02 и handoff для остальных ролей:

```bash
python3 scripts/pipeline/night_runner.py \
  --wave-id wave-a1b311d18f07 \
  --execute \
  --max-workers 8 \
  --max-cycles 100 \
  --sleep-seconds 5 \
  --json-lines
```

Подключение реального executor command:

```bash
python3 scripts/pipeline/night_runner.py \
  --wave-id wave-a1b311d18f07 \
  --execute \
  --max-workers 8 \
  --max-cycles 100 \
  --executor-command 'scripts/pipeline/run_external_agent.sh "$WMS_PIPELINE_DISPATCH"'
```

`--executor-command` выполняется параллельно по независимым task IDs до `--max-workers`.
Команда должна быть идемпотентной: если stage уже advanced другим агентом, она обязана
перечитать `next` и не создавать повторный receipt.

## Защита чужой работы

По умолчанию включён `--git-dirty-guard`. Если в `tasks/<task-id>/` или
`docs/evidence/<task-id>/` уже есть незакоммиченные изменения, runner пропускает эту карточку:

```text
action=skipped_dirty_task
```

Это нужно для ночной параллельной работы: один агент не должен поверх чужого незакоммиченного
BA/Product artifact генерировать новый packet или receipt. Взять такую карточку под управление
можно только явно:

```bash
python3 scripts/pipeline/night_runner.py --task-id BLG-D01 --execute --allow-dirty-task
```

## Границы

Runner не делает live deploy, не открывает кабинеты ключей, не ходит в live WB/Ozon и не
меняет production. Release stages остаются под отдельным exact-SHA owner approval.

Runner также не снимает архитектурный blocker внешнего durable store: это локальный host-loop.
Он восстанавливается по controller state на этой машине, но не является распределённым
controller-owned store для нескольких hosts.

CI smoke:

```bash
python3 scripts/ci/check_pipeline_night_runner_smoke.py
```
