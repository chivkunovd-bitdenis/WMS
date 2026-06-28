# Очередь autopilot: дорожки, блокировки, зависимости

> **Для кого:** владелец продукта и автор backlog.  
> **Для агента:** orchestrator читает этот файл **только в queue mode** при раздаче задач — не подмешивается в каждый чат автоматически.  
> **Переносимость:** те же **имена атрибутов** используй в других проектах.

---

## Зачем

Два builder'а, правящие **один файл** параллельно → конфликт на merge или потерянные правки.

**Единица блокировки = файл или экран** (группа файлов одного UI).

---

## Атрибуты (канонические имена — не переименовывать)

| Атрибут | Обязателен | Смысл |
|---------|------------|--------|
| **`lane`** | рекомендуется | Дорожка: задачи с **одним `lane`** идут **строго по одной** (последовательно). |
| **`files`** | да (для кода) | Список путей, которые задача **блокирует**. Нельзя параллелить две задачи с **пересечением** `files`. |
| **`depends_on`** | если есть порядок | ID задач-предшественников (через запятую). Задача **не стартует**, пока все предшественники не **` done`**. |

Дополнительно (как сейчас в WMS):

| Маркер | Смысл |
|--------|--------|
| **` done`** в конце строки | Закрыто (verifier PASS). |
| **` blocked`** | 3 fix без зелёного CI — skip. |

---

## Правила планирования (orchestrator)

1. **Skip:** строки с ` done` или ` blocked`.
2. **depends_on:** задача runnable только если все ID из `depends_on` уже ` done` в QUEUE.
3. **files:** не запускать две runnable задачи одновременно, если множества `files` **пересекаются** (хотя бы один общий путь).
4. **lane:** в одном `lane` одновременно **не больше одной** активной задачи (даже если `files` формально разные — lane = общая дорожка экрана/модуля).
5. **parallel_workers:** из промпта / `SESSION_HANDOFF` — максимум столько builder **одновременно**, сколько задач прошли правила 2–4.
6. **Строго 1 задача = 1 builder** (как в orchestrator).

---

## Формат строки в `.cursor/QUEUE.md`

Одна задача = одна строка. Атрибуты через ` | ` (пробел-вертикальная черта-пробел):

```text
ID — человекочитаемое описание | lane: имя-дорожки | files: path/a, path/b | depends_on: ID2, ID3
```

Примеры:

```text
MP-035 — TSD scan contract | lane: mp-api | files: backend/app/api/marketplace_unload_requests.py, backend/app/services/marketplace_unload_collect_service.py | depends_on:
MP-036 — UI scan hints | lane: mp-shipments-ui | files: frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx | depends_on: MP-035
MP-037 — e2e full-flow | lane: mp-e2e | files: frontend/tests-e2e/ff-mp-full-flow.spec.ts | depends_on: MP-035, MP-036
MP-038 — seller unload dialog | lane: seller-mp | files: frontend/src/components/SellerMarketplaceUnloadDialog.tsx | depends_on:
```

- **`depends_on:`** пустой или `depends_on: —` — нет предшественников.
- **`files:`** для docs-only задач можно `files: docs/...` или один markdown.
- **Имена lane:** kebab-case, по модулю/экрану: `mp-shipments-ui`, `mp-api`, `cz-ledger`, `seller-settings`.

---

## Как нарезать backlog (для человека)

1. **Сначала дорожки** — один экран / один service = одна lane.
2. **Внутри lane** — порядок сверху вниз; при необходимости `depends_on` на предыдущий ID.
3. **Между lane** — можно параллелить, если **нет** общих `files` и нет `depends_on` на незакрытое.
4. **Крупная задача** — несколько строк, разные `files`, связь через `depends_on`.
5. **E2E** — отдельная lane или `depends_on` на UI/API, которые тестируешь.

---

## Resume после обрыва

State на диске: ` done` / ` blocked` в QUEUE. Orchestrator снова применяет правила 1–6 к **открытым** строкам. `depends_on` пересчитывается по актуальному QUEUE.

---

## Связанные файлы (WMS)

| Файл | Роль |
|------|------|
| `.cursor/QUEUE.md` | Список задач с атрибутами |
| `.cursor/SESSION_HANDOFF.md` | `parallel_workers`, последняя закрытая |
| `~/.cursor/agents/orchestrator.md` | Режим очереди + ссылка сюда |
| `.cursor/rules/wms-queue.mdc` | Краткие правила queue mode |

---

## Шпаргалка для старта orchestrator

```text
orchestrator, continuous, queue mode, 5 агентов, resume. Продолжай .cursor/QUEUE.md.
Планирование: docs/CURSOR_QUEUE_LANES_RU.md — lane, files, depends_on.
1 задача = 1 builder. builder → verifier → fix.
```
