# Agent R-09 — adversarial review log

## PACK-08 — Прогресс X/Y в колонке ЧЗ

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `313c410`  
**Files reviewed:** `FfPackagingPage.tsx`, `ff-marking-packaging.spec.ts`, `ff-marking-print-constructor.spec.ts`

### Critical

_нет_

### Warnings

1. Два критерия неполноты: колонка ЧЗ — `qty_need_pack`, гард завершения (PACK-07) — `qty_done`; при частичной упаковке возможна путаница.
2. Нехватка кодов в пуле не подсвечивается (`CZ-M3` out of scope).
3. Нет отдельного `TC-NEW-PACK-08`; проверки в TC-NEW-001, TC-NEW-PKG-07.
4. Нет записи PACK-08 в TASKLOG.
5. `FfPackagingPage.tsx` >400 строк (pre-existing).
6. E2e не проверяет снятие подсветки и не использует `ff-packaging-marking-progress-*` testids.

### Checklist

| Раздел | OK | ISSUE | N/A |
|--------|-----|-------|-----|
| A. Engineering | 5 | 1 | 2 |
| B. External | — | — | all |
| C. Async/race | 3 | 0 | — |
| D. UI mechanics | 2 | 0 | 4 |
| E. Tests | 2 | 1 | 1 |
| F. Scope | 2 | 0 | — |

### Contract gaps

| Gate | Статус |
|------|--------|
| «напечатано X / нужно Y» | ✅ |
| остаток в пуле | ✅ |
| подсветка неполных | ✅ |
| подсветка нехватки в пуле (CZ-M3) | ❌ out of scope |

## PRINT-03 — Переименовать label → «ШК ВБ»

**Verdict:** BLOCK  
**Commit:** `f267a75` (integrate `8b06d45`)  
**Files:** `MarkingPrintDialog.tsx`, `markingPrintPresets.ts`

### Critical

1. Merge-артефакт на HEAD: в custom-builder select одновременно «Этикетка», «ШК ВБ» и дубли «ЧЗ» (стр. 488–491). Gate не выполнен на integrated ветке.

### Warnings

1. Старая терминология «этикеток» в helper-текстах.
2. JSDoc `markingPrintPresets.ts:101` не обновлён.
3. Нет e2e на отсутствие «Этикетка» в select.
4. Isolated commit `f267a75` чистый.

### Fix

Удалить дубли MenuItem 488–489; e2e assert «Этикетка» absent в select.

## IMPORT-01 — Мерж групп по GTIN

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `b66b98e`

### Critical

_нет_

### Warnings

1. CROSS-04: `poolContext` при re-preview может затереть title/productIds.
2. Exact GTIN — 13/14 digit не мержатся.
3. Нет e2e второго файла.
4. Race preview без abort.
5. Нет TASKLOG; файл >400 строк.

### Gate

Мерж по gtin + сохранение title/productIds ✅ (без poolContext)

## POOLCARD-03 — Таб «Лента» → превью + ссылка

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `8bca507`

### Critical

_нет_

### Warnings

1. `loadLedger` без error-handling.
2. E2e не проверяет cap 5 событий.
3. Seller-портал не покрыт e2e.
4. Коллизия TC-NEW-011.
5. Файл >400 строк; race без abort.

### Gate

Превью + ссылка ✅ | дубль ленты убран ✅

## CROSS-03 — Единый Autocomplete селлера

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `b8b85e4`

### Critical

_нет_

### Warnings

1. Clearable Autocomplete → лента без `seller_id`.
2. E2e не проверяет поиск по названию.
3. Коллизия TC-NEW-011.
4. Seller-портал не покрыт e2e.

### Gate

Единый `MarkingSellerPicker` ✅ | e2e фильтрация ✅
