# CZ UX — сводный adversarial-review

**Ветка:** `feat/cz-ux-fixes`  
**Прогресс:** 47 / 47 ✅

## Сводка вердиктов

| Verdict | Count |
|---------|-------|
| APPROVE | 0 |
| APPROVE WITH WARNINGS | 43 |
| BLOCK | 4 |

## BLOCK (fix before merge)

| ID | Agent | Суть |
|----|-------|------|
| PACK-05 | R-06 | E2e: выбор не-первого КМ + причина (T-B1) |
| PRINT-03 | R-09 | Merge-артефакт MenuItem в `MarkingPrintDialog` |
| CROSS-04 | R-07 | `poolContext` затирает правки при re-preview |
| FINAL-01 | R-03 | E2e «1 код» vs «1 КМ»; остатки «код/кодов» в UI |

## Паттерны warnings

- TASKLOG / TC-ID / commit hash — системно
- Негативные e2e на удалённые UI
- Stale fetch / race в `load()` без abort (ledger, pools)
- `MarkingImportDialog` merge debt (IMPORT + CROSS-04)
- Mega-merge коммиты затрудняют изолированное ревью

## Вывод

**4 блокера** перед merge в `main`. **43 задачи** с предупреждениями — в основном отсутствие e2e, TASKLOG drift, race без abort.

**Приоритет фиксов:**
1. **PRINT-03** — дубли MenuItem (быстрый UI-баг)
2. **FINAL-01** — терминология + e2e (иначе красный CI)
3. **CROSS-04** — потеря правок при re-preview (data loss)
4. **PACK-05** — gate T-B1 не доказан e2e

**Docs-only follow-up:** FINAL-03 — синхрон `MASTER_BACKLOG` со статусами lane.

Детали по задачам: `docs/reviews/cz-ux/agent-R-*.md`
