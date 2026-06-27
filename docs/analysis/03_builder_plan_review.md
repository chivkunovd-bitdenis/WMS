# Builder Plan Review

## Verdict

- Статус: **PASS**
- Краткий вывод: после решений владельца **DEC-001…DEC-011** (2026-06-27) business spec и technical plan согласованы. Все 18 задач **READY**, блокеров и unsafe-задач нет. План можно передавать builder-агенту **порядком Implementation Order** из `02_technical_builder_plan.md`. Разработку не начинать до явного запроса владельца.

## Input

- Business spec: `docs/analysis/01_normalized_process_spec.md` (DEC-001…DEC-011, Open Questions: none)
- Technical plan: `docs/analysis/02_technical_builder_plan.md` (обновлён под решения)
- Дата ревью: 2026-06-27

## Owner Decisions Applied

| ID | Суть | Отражение в плане |
|----|------|-------------------|
| DEC-001 | Только `marketplace_unload` | Scope, Stop Conditions |
| DEC-002 | Пустые короба удаляются при ship; X из Y = товары в коробах | TASK-014, TASK-015, BR-009 |
| DEC-003 | PackagingTask при create draft | TASK-006 READY |
| DEC-004 | Без полей водитель/авто/пропуск | TASK-014 переписан, Out of Scope |
| DEC-005 | Выкл. → агрегат; вкл. → ячейка или зона сортировки | TASK-002, BR-006 |
| DEC-006 | Резерв confirm → списание collect → ship статус | TASK-004, TASK-015 |
| DEC-007 | Delete короба только пустого | TASK-010, BR-011 |
| DEC-008 | Sync план → упаковка при CRUD линий | TASK-006 |
| DEC-009 | Дефолт адресное хранение = вкл. | TASK-001 |
| DEC-010 | Предупреждение на «Короба» + при ship; ship только при полном распределении | TASK-013, TASK-014, TASK-015 |
| DEC-011 | «Печать всех ШК» на финале | TASK-014 |

## Requirements Coverage

| REQ | Spec | Plan | Задачи | Статус |
|-----|------|------|--------|--------|
| REQ-001 | YES | YES | TASK-001–003 | OK |
| REQ-002 | YES (EXISTS) | PARTIAL | TASK-012, TASK-017 | OK — отдельная задача не нужна; желательно regression в TASK-017 |
| REQ-003 | YES | YES | TASK-005, TASK-011, TASK-013 | OK |
| REQ-004 | YES | YES | TASK-006, TASK-007, TASK-012 | OK — create draft + sync (DEC-003, DEC-008) |
| REQ-005 | YES | YES | TASK-007 | OK |
| REQ-006 | YES | YES | TASK-008 | OK |
| REQ-007 | YES | YES | TASK-009 | OK |
| REQ-008 | YES | YES | TASK-011 | OK |
| REQ-009 | YES | YES | TASK-002, TASK-004, TASK-015 | OK — DEC-005/006 закрыли unknown по inventory |
| REQ-010 | YES | YES | TASK-010 | OK — DEC-007: delete empty, remove line + откат |
| REQ-011 | YES | YES | TASK-013 | OK — + warning DEC-010 |
| REQ-012 | YES | YES | TASK-014, TASK-012, TASK-015 | OK — без полей перевозки (DEC-004) |
| REQ-013 | YES | YES | TASK-007, TASK-012 | OK |
| REQ-014 | YES | YES | TASK-018, TASK-002, TASK-011 | OK |

**Все REQ покрыты.** Частичность REQ-002 допустима (EXISTS в коде).

## Task Review Summary

| Task | План | Builder-ready | Примечание |
|------|------|---------------|------------|
| TASK-001 | READY | YES | Конкретизировать целевой API-файл при реализации |
| TASK-002 | READY | YES | DEC-005: агрегат / зона сортировки |
| TASK-003 | READY | YES | — |
| TASK-004 | READY | YES | После TASK-002; до TASK-010/011 |
| TASK-005 | READY | YES | После box flow |
| TASK-006 | READY | YES | Был BLOCKED Q-003 — снят |
| TASK-007 | READY | YES | Зависит от TASK-006 |
| TASK-008 | READY | YES | — |
| TASK-009 | READY | YES | — |
| TASK-010 | READY | YES | Был unsafe — DEC-007 закрыл |
| TASK-011 | READY | YES | + TASK-004 в dependencies |
| TASK-012 | READY | YES | Финал → TASK-014 (исправлено) |
| TASK-013 | READY | YES | + warning DEC-010 |
| TASK-014 | READY | YES | Был BLOCKED Q-004 — переписан |
| TASK-015 | READY | YES | После TASK-004 |
| TASK-016 | READY | YES | — |
| TASK-017 | READY | YES | — |
| TASK-018 | READY | YES | — |

### Blocked Tasks

**Нет.**

### Unsafe Tasks

**Нет.** Ранее небезопасные TASK-002, TASK-004, TASK-010 закрыты правилами DEC-005, DEC-006, DEC-007 в spec.

## Scope Review

### In Scope

- Контур `marketplace_unload`: адресное хранение, упаковка (draft + sync), короба, collect, счётчики, предупреждения, финал с печатью всех ШК, ТСД API, тесты.

### Out of Scope

- `outbound_shipment` (DEC-001)
- Поля водитель/авто/пропуск (DEC-004)
- Android-клиент, импорт сверх picker, сущность «магазин»

**Лишнего scope нет.**

## Consistency Check

| ID | Было | Статус |
|----|------|--------|
| CONS-001 | TASK-012 ссылался на TASK-013 вместо TASK-014 | **Исправлено** |
| CONS-002 | TASK-006 BLOCKED vs TASK-007 READY | **Закрыто** — TASK-006 READY |
| CONS-003 | TASK-004 после TASK-011 в порядке | **Исправлено** — TASK-004 до TASK-011; dependency в TASK-011 |
| CONS-004 | REQ-001…013 vs REQ-014 | **Исправлено** — REQ-001…014 |

## Residual Gaps (не блокируют разработку)

### GAP-R01. Конкретный API-модуль tenant settings

- Тип: **IMPLEMENTATION**
- Проблема: TASK-001 указывает `backend/app/api/` без имени файла.
- Блокирует: **NO** — выбрать паттерн при первом slice.

### GAP-R02. «Зона сортировки» в inventory_service

- Тип: **TECHNICAL**
- Проблема: DEC-005 зафиксирован в spec; при реализации TASK-002 нужно привязать к существующим `StorageLocation` / warehouse zone в коде, не изобретая сущность.
- Блокирует: **NO** — исследование в TASK-002.

### GAP-R03. Regression REQ-002 в e2e

- Тип: **TEST**
- Проблема: нет явной строки в TASK-017 на seller_id.
- Блокирует: **NO** — желательно добавить при TASK-017.

## Readiness

### Ready Tasks (все 18)

TASK-001 … TASK-018 — см. Implementation Order в `02_technical_builder_plan.md`.

### Recommended First Slice

1. TASK-001 → TASK-006 → TASK-002 → TASK-003
2. TASK-007 → TASK-008 → TASK-004
3. TASK-009 → TASK-010 → TASK-011 → TASK-005 → TASK-013 → TASK-012 → TASK-015 → TASK-014
4. TASK-016, TASK-017, TASK-018 — по мере готовности блоков

## Final Decision

- Можно передавать builder-агенту: **YES** (полный план)
- Обязательно перед кодом: следовать Implementation Order; не трогать `outbound_shipment`; не добавлять поля перевозки
- Желательно при реализации: GAP-R01–R03
- **Разработка:** по запросу владельца (на момент ревью — docs only)
