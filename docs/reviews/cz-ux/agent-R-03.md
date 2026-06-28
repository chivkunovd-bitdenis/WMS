# Agent R-03 — adversarial review log

## PACK-02 — Удалить «Печать всех ЧЗ»

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `b2bb88d` (lane `task/PACK-02`; на HEAD — `854c1c8` PACK-04)

### Critical

_нет_

### Warnings

1. `task/PACK-02` не ancestor `feat/cz-ux-fixes`; gate на HEAD закрыт PACK-04.
2. `depends_on PACK-01` не соблюдён на lane-ветке.
3. Verification: только build; нет негативного e2e.
4. TC-NEW-003 снят без обновления каталога.
5. TASK-037 коллизия с FINAL-03.

### Checklist

- E Tests: ISSUE | F Scope: ISSUE

### Gate

Нет print-all UI на `task/PACK-02` ✅; на HEAD через PACK-04 ✅

## PRINT-05 — Per-user print template

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `e79b8e2`

### Critical

_нет_

### Warnings

1. Нет атомарности print + auto-save (split commit).
2. Нет UNIQUE на `__user_last__`.
3. `create_print_template` всегда user-scoped.
4. PUT/DELETE без проверки владельца.
5. Нет e2e для двух операторов.
6. `print_template_service.py` >400 строк.

### Gate

Миграция + resolve + auto-save + pytest Вася/Петя ✅

## POOLS-04 — Убрать дубль дашборд+таблица

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `356cd0c` (integrate `3ce2367`)

### Critical

_нет_

### Warnings

1. Нет TASKLOG POOLS-04.
2. KPI «Пулы на исходе» → пустая таблица (пересечение POOLS-02).
3. E2e только empty pool.
4. Брак/непривязка не в `isProblematicPool`.

### Gate

Нет двойного показа пула ✅ | e2e dedup ✅

## FINAL-01 — Единый термин (КМ/ЧЗ) по лейблам

**Verdict:** BLOCK  
**Commits:** `c3d05c8` (labels), integrate `78abf21` (assembled slice → `feat/cz-ux-fixes`)

### Critical

1. E2E drift: `ff-marking-packaging.spec.ts` ожидает «1 код», UI — «1 КМ» (`marking-print-will-print`).
2. Gate не закрыт — user-visible «код/кодов» остались: `HonestSignPoolPage` (CSV export), `FfHonestSignReprintsPage` («История кода»), `App.tsx` («Загрузка кодов»), `printMarkingCodeLabel.ts`.

### Warnings

1. Mega-merge lane-веток + labels; verification только build.
2. Reprints hint-тексты всё ещё смешивают код/КМ.
3. Нет lint/grep gate на терминологию.
4. `HonestSignPoolPage` в TASKLOG, но CSV-строки пропущены.

### Checklist

ISSUE: 2 (E Tests, F Scope/gate)

### Gate

| Критерий | Статус |
|----------|--------|
| КМ для экземпляров, ЧЗ для требования/системы | ✅ в основных экранах |
| Нет смеси КИЗ/код/КМ | ❌ остатки «код» |
| E2e согласован с лейблами | ❌ |

### Следующий шаг

**builder** — добить лейблы, обновить e2e `К перепечатке: 1 КМ`; затем verifier.
