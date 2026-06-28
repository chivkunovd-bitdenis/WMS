# Очередь autopilot

**Канонический backlog:** **`docs/PARALLEL_AGENT_TASKS.md`** (ЧЗ, lanes, depends_on).

Этот файл — краткая справка по статусам. Задачи ведутся в PARALLEL (таблицы + ` done` / ` blocked` на id).

**Планирование:** `docs/CURSOR_QUEUE_LANES_RU.md`

## Статусы (в PARALLEL_AGENT_TASKS)

| Состояние | Как писать |
|-----------|------------|
| Закрыто | `PACK-01 done` в колонке id или секция с пометкой **done** |
| Заблокировано | `… blocked` |
| Барьер CZ-000 | **done** — ветка `feat/cz-ux-fixes`, база `304abf2` |

## Старт orchestrator

```text
orchestrator, continuous, queue mode, 5 агентов.
Backlog: docs/PARALLEL_AGENT_TASKS.md. 1 задача = 1 builder. builder → verifier → fix.
Commit без моей команды не делать.
```
