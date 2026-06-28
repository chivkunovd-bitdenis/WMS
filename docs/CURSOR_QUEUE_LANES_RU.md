# Очередь autopilot: дорожки, блокировки, зависимости

> **Для кого:** владелец продукта и автор backlog.  
> **Для агента:** orchestrator читает этот файл **только в queue mode** при раздаче задач — не подмешивается в каждый чат автоматически.  
> **Переносимость:** те же **имена атрибутов** используй в других проектах.

---

## Зачем

Два builder'а, правящие **один файл** параллельно → конфликт на merge или потерянные правки.

**Единица блокировки = файл или экран** (группа файлов одного UI).

---

## Статус задачи (единый контракт)

**Таблицу backlog НЕ редактируем** после старта. Статус — только файлы:

| Файл | Смысл |
|------|--------|
| **`.cursor/state/<id>.done`** | Закрыто: merge в integration branch + verifier PASS. Создаёт **orchestrator**. |
| **`.cursor/state/<id>.integrated`** | Merge `task/<id>` → integration branch выполнен. |
| **`.cursor/state/<id>.blocked`** | 3 fix без зелёного CI — skip. |

**depends_on:** задача runnable, когда у **всех** предшественников есть `.cursor/state/<id>.done`.

**integration_branch:** merged → `main` (PR #49, 2026-06-28). Для следующего эпика — новая ветка от `main`.

**Изоляция:** worktree `.cursor/wt/<id>`, ветка `task/<id>`, база = **HEAD integration branch**.

**Integrate (orchestrator, после verifier):** `./scripts/queue-integrate.sh <id>` — **один merge за раз** (global lock), конфликт → builder на integration branch.

---

## Атрибуты (канонические имена — не переименовывать)

| Атрибут | Обязателен | Смысл |
|---------|------------|--------|
| **`lane`** | рекомендуется | Дорожка: задачи с **одним `lane`** идут **строго по одной** (последовательно). |
| **`files`** | да (для кода) | Список путей, которые задача **блокирует**. Нельзя параллелить две задачи с **пересечением** `files`. |
| **`depends_on`** | если есть порядок | ID задач-предшественников (через запятую). Runnable только если у всех есть **`.done`** в state. |

---

## Правила планирования (orchestrator)

1. **Skip:** id, у которых есть `.cursor/state/<id>.done` или `.blocked`.
2. **depends_on:** runnable только если у всех предшественников есть `.cursor/state/<id>.done`.
3. **files:** не запускать две runnable задачи одновременно, если множества `files` **пересекаются**.
4. **lane:** в одном `lane` одновременно **не больше одной** активной задачи.
5. **parallel_workers:** из промпта / `SESSION_HANDOFF` — максимум столько builder **одновременно**, сколько задач прошли правила 2–4.
6. **Строго 1 задача = 1 builder.**

---

## Формат backlog (WMS)

**Файл:** **`docs/PARALLEL_AGENT_TASKS.md`** — markdown-таблицы по lane (**read-only** для статуса).

| Колонка | Смысл |
|---------|--------|
| **`id`** | PACK-01, PRINT-01, … (**не** менять на `PACK-01 done`) |
| **`depends_on`** | CZ-000, PACK-01, … (все должны быть `.done` в state) |
| **`do`** | что делать builder |
| **`gate`** | критерий verifier |

**Lane** = секция `## LANE-PACK`, `## LANE-PRINT`, …; `files` — в шапке lane или колонке CROSS.

---

## Как нарезать backlog (для человека)

1. **Сначала дорожки** — один экран / один service = одна lane.
2. **Внутри lane** — порядок сверху вниз; при необходимости `depends_on` на предыдущий ID.
3. **Между lane** — можно параллелить, если **нет** общих `files` и нет `depends_on` на незакрытое.
4. **Крупная задача** — несколько строк, разные `files`, связь через `depends_on`.
5. **E2E** — отдельная lane или `depends_on` на UI/API, которые тестируешь.

---

## Resume после обрыва

На диске: `.cursor/state/*.done` / `*.blocked`, worktree `.cursor/wt/<id>`, коммиты в ветках `task/<id>`.  
Тот же стартовый промпт в **новом чате** — orchestrator подхватит с state.

---

## Связанные файлы (WMS)

| Файл | Роль |
|------|------|
| **`docs/PARALLEL_AGENT_TASKS.md`** | Backlog (таблицы задач, read-only) |
| `.cursor/state/` | `.done` / `.blocked` |
| `.cursor/SESSION_HANDOFF.md` | `parallel_workers`, активные слоты |
| `~/.cursor/agents/orchestrator.md` | Режим очереди |
| `.cursor/rules/wms-queue.mdc` | Старт + краткие правила |
| `~/.cursor/autopilot/hooks.py` | Hook arm/continue (глобально) |

---

## Шпаргалка для старта orchestrator

```text
orchestrator, continuous, queue mode, 5 агентов. backlog: docs/PARALLEL_AGENT_TASKS.md
Worker pool: 1 id = 1 builder, refill on free slot.
Изоляция: worktree .cursor/wt/<id>. Готово = touch .cursor/state/<id>.done после verifier.
builder → verifier → fix.
```
