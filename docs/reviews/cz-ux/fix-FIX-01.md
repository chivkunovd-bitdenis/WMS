# FIX-01 — Print dialog (PRINT-03 + related)

**Agent:** builder FIX-01  
**Branch:** `feat/cz-ux-fixes`  
**Date:** 2026-06-28

## Per-task status

| Task | Status | Notes |
|------|--------|-------|
| **PRINT-03** (BLOCK) | **FIXED** | Удалены merge-артефакты в custom-builder select: один `ЧЗ` + один `ШК ВБ`; убраны дубли и stale «Этикетка». Helper-тексты «этикеток» → «ШК ВБ» / «блоков». JSDoc в `markingPrintPresets.ts` обновлён. |
| PRINT-01 | **N/A** (verified) | Gate qty-only для не-ЧЗ не трогался; в коде `!requiresHonestSign` → только `marking-print-wb-qty`, без конструктора. Регрессии нет (см. `ff-mp-packaging-print.spec.ts`, вне зоны FIX-01). |
| PRINT-02 | **FIXED** (e2e) | Кнопка `marking-print-request-seller` отсутствует в коде; добавлен e2e assert `toHaveCount(0)` в TC-NEW-001. |
| PRINT-04 | **N/A** | Множитель × упаковка уже в коде (`packUnits`, `totalWbLabels`); изменений не требовалось. |
| PRINT-05 | **N/A** | Per-user template — backend/другие файлы, вне exclusive scope FIX-01. |

## Files changed

| File | Change |
|------|--------|
| `frontend/src/components/MarkingPrintDialog.tsx` | PRINT-03: MenuItem dedup; терминология ШК ВБ/блоков |
| `frontend/src/utils/markingPrintPresets.ts` | JSDoc `applyLabelsPerProductToLayout` |
| `frontend/tests-e2e/ff-marking-packaging.spec.ts` | e2e: нет «Этикетка» в select; нет request-seller; fix duplicate import |

## Verification

| Command | Exit code |
|---------|-----------|
| `cd frontend && npm run build` | **0** |
| `npx playwright test tests-e2e/ff-marking-packaging.spec.ts -g "print honest sign codes for line quantity"` | **0** |

## Follow-ups (out of scope)

- `ff-mp-packaging-print.spec.ts:226` ожидает «К печати: 6 этикеток» — после смены UI на «ШК ВБ» нужен апдейт expect (другой агент/верifier).
- `ff-marking-packaging.spec.ts` reprint-тест: «1 код» vs UI «1 КМ» — зона FIX-03 (FINAL-01).
- `MarkingPrintDialog.tsx` ~680 строк — pre-existing size debt.
