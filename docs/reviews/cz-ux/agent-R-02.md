# Agent R-02 — adversarial review log

## PACK-01 — Удалить скан-печать

**Verdict:** APPROVE WITH WARNINGS  
**Files reviewed:** `frontend/src/screens/ff/FfPackagingPage.tsx` (commit `bcdafa7`)

### Critical

_нет_

### Warnings

1. Нет e2e-регрессии на отсутствие скан-поля — ни один тест не проверяет, что `marking-scan-print-field` / `marking-scan-print-input` отсутствуют.
2. Дублирующие коммиты `bcdafa7` и `eafab3f` — одинаковый diff (−93 строки).
3. TASKLOG без отдельной строки PACK-01 — только упоминание в TASK-063 (интеграция в FINAL-01/PACK-09).

### Checklist

| Раздел | OK | ISSUE | N/A |
|--------|----|-------|-----|
| A. Engineering standards | 5 | 1 | 2 |
| B. External contracts | 2 | 0 | 1 |
| C. Async / race | — | 0 | 5 |
| D. UI mechanics | 1 | 0 | 4 |
| E. Tests | 1 | 1 | 0 |
| F. Scope & ops | 2 | 0 | 1 |

ISSUE: `FfPackagingPage.tsx` >400 строк — наследие файла, не введено PACK-01.

### Contract gaps

| Контракт | Статус |
|----------|--------|
| Gate «нет элемента скан-печати» | ✅ |
| Удалить JSX + `submitScanPrint` + `scan*` | ✅ `bcdafa7` |
| Убрать `printMarkingCodeLabels` (только scan-print) | ✅ |
| Поле отсутствует в ручном и МП-задании | ✅ |
| E2e: зафиксировать отсутствие поля | ⚠️ Gap |

### Evidence

- Коммит `bcdafa7`: удалены `scanBarcode`/`scanBusy`/`scanFlash`, `submitScanPrint` (POST `/operations/marking-codes/scan-print`), JSX `marking-scan-print-field`.
- Grep по `FfPackagingPage.tsx` и `frontend/` — 0 совпадений scan-print.
- E2e `ff-marking-packaging.spec.ts` — per-line print, без scan-print.

## PRINT-01 — Не-ЧЗ: qty-only (без конструктора)

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `0c694b7`  
**Files:** `MarkingPrintDialog.tsx`, `ff-mp-packaging-print.spec.ts`

### Critical

_нет_

### Warnings

1. Регрессия префилла: после CROSS-01 `wbBarcodeQty=1` вместо `qtyNeedPack`.
2. Дубли MenuItem в ЧЗ-билдере (merge PRINT-03) — см. PRINT-03 BLOCK.
3. Edge `reprint && !requiresHonestSign` — qty скрыто, печать с qty=1.
4. E2e только MP-контекст (TC-NEW-MP-016).

### Gate

Не-ЧЗ → только `marking-print-wb-qty` ✅

## LEDGER-06 — Локализация типов событий

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `8c0c350`

### Critical

_нет_

### Warnings

1. Фильтр `EVENT_TYPES` — подмножество бэкенда (6 из 10).
2. Fallback на английский для неизвестных типов.
3. `FfHonestSignReprintsPage` — сырой `event_type`.
4. CSV export — EN enum.

### Gate

События по-русски в ленте ✅ | e2e «Импорт»/«Печать» ✅

## POOLCARD-02 — Экспорт всех кодов

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `1d71ce5` (integrate `d2ff556`)

### Critical

_нет_

### Warnings

1. Нет e2e на подпись «N из M».
2. Хвост КМ не в экспорте (UI предупреждает).
3. `isExportSubsetOfPool` edge case при фильтре статуса.
4. API без пагинации — риск больших пулов.
5. Verification только build.

### Gate

Серверный fetch + честные подписи ✅

## CROSS-01 — «Повтор»: перепечатка одного КМ

**Verdict:** APPROVE WITH WARNINGS  
**Commits:** `b20496f`, `280944b`

### Critical

_нет_

### Warnings

1. MP-отгрузка — «Повтор» скрыт в меню.
2. Race fetch `printed-codes` без abort.
3. API без `code_ids` — reprint всей строки.
4. Побочный регресс `wbBarcodeQty=1`.

### Gate

Radio один КМ + `code_ids` ✅ | e2e TC-NEW-CROSS-01 ✅
