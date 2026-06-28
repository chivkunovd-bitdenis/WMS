# CZ UX — очередь фиксов (5 parallel builders)

**Ветка:** `feat/cz-ux-fixes`  
**Источник:** `CONSOLIDATED.md` + `agent-R-*.md`  
**Статус:** IN PROGRESS

## Правила безопасности

- Каждый агент **только свои файлы** (см. колонку Files).
- Шаг ≤ **5 файлов**, затем `ruff`/`pytest` или `npm run build` по зоне.
- **BLOCK** — обязательно закрыть в своей полосе.
- Warnings — код/e2e/race/TASKLOG; docs-only только у FIX-05.
- Отчёт: `docs/reviews/cz-ux/fix-FIX-0N.md` (verdict per task).

## Распределение

| Agent | BLOCK | Tasks | Files (exclusive) |
|-------|-------|-------|---------------------|
| FIX-01 | PRINT-03 | PRINT-01,02,04,05 | `MarkingPrintDialog.tsx`, `markingPrintPresets.ts`, `ff-marking-packaging.spec.ts` (print sections only) |
| FIX-02 | CROSS-04 | IMPORT-01..05, CROSS-03 | `MarkingImportDialog.tsx`, `markingImportMerge.test.ts`, `ff-honest-sign-import.spec.ts` |
| FIX-03 | FINAL-01 | SHARED-01, POOLCARD-01, LEDGER-06, POOLS-03 | `honestSignLabels*`, `HonestSignPoolPage.tsx`, `FfHonestSignReprintsPage.tsx`, `App.tsx`, `printMarkingCodeLabel.ts`, `ff-marking-packaging.spec.ts` (terminology asserts only) |
| FIX-04 | PACK-05 | PACK-01..09, CROSS-01 | `FfPackagingPage.tsx`, `ff-marking-defect.spec.ts`, `ff-marking-packaging.spec.ts` (pack/defect sections only) |
| FIX-05 | — | LEDGER-01..05, POOLS-01..06, REPRINTS-01..03, POOLCARD-02,03, BACKEND-01, CROSS-02, PENDING-01, FINAL-02,03 | ledger/pools/reprints screens, backend deprecations, docs |

## Конфликт `ff-marking-packaging.spec.ts`

- FIX-01: блоки print/dialog (не трогать defect).
- FIX-03: только строки с «код»→«КМ» в expect.
- FIX-04: defect/reprint sections.
- При merge — rebase по порядку FIX-03 → FIX-01 → FIX-04.

## BLOCK checklist

- [ ] PRINT-03 — дубли MenuItem в MarkingPrintDialog
- [ ] FINAL-01 — терминология + e2e «1 КМ»
- [ ] CROSS-04 — poolContext не затирает title/productIds при re-preview
- [ ] PACK-05 — e2e: не-первый КМ + причина брака
