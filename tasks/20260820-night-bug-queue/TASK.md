# TASK — 20260820-night-bug-queue: ночная очередь WMS-багов на 2026-08-21

Статус: подготовка task cards для Pipeline v2. Pipeline v2 ещё не `ACTIVE`, поэтому
эти карточки не заменяют старый Product gate и не дают права на live deploy.

Источник фактуры:

- `docs/process/PIPELINE-HOLES-RU.md` — P0-дыры перед активацией Pipeline v2;
- `pipeline/pipeline.yml` — разрешённые stages, traits и risk-level;
- `docs/process/INCIDENTS-REGISTRY-RU.md` — боевые WMS-инциденты 19–20.08.2026;
- наблюдённые FBS/Честный знак и test-stack сбои 20.08.2026.

## Цель на завтра

К утру 2026-08-21 у dispatcher-а должна быть короткая исполнимая очередь из пяти
атомарных bug cards. Каждая карточка открывается отдельной командой
`python3 scripts/pipeline/run.py open ...`, получает свой pipeline profile и не
смешивается с соседней карточкой.

## Очередь

1. `BUG-WMS-PV2-001` — exact-SHA deploy: закрыть остаток build-once promotion.
2. `BUG-WMS-PV2-002` — fail-closed test egress для WB/Ozon.
3. `BUG-WMS-TESTSTACK-001` — честный test-stack: migrations вместо `create_all`.
4. `BUG-WMS-FBS-CZ-001` — FBS/Честный знак: eligibility перед dispatch.
5. `BUG-WMS-FBS-PRINT-001` — печать labels: количество и scope поставки.

Порядок намеренный: сначала защита конвейера и тестовой среды, затем баги
операторского FBS-потока. Ни одна карточка не требует live deploy или доступа к
секретам.

## Границы

- Не выполнять production deploy, Railway/Railway-like secret updates и реальные
  вызовы WB/Ozon.
- Не открывать кабинеты ключей, не читать и не выводить секреты.
- Не править runtime state вручную. `tasks/<task-id>/state.json` создаёт только
  controller после явного запуска `open`.
- Один bug card — один владелец stage/role, один scope и отдельная ветка после
  выделения workspace.

Детали карточек лежат в `BUG-CARDS.md`, порядок запуска и handoff — в
`AGENT-RUNBOOK.md`.
