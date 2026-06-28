# Agent R-08 — adversarial review log

## PACK-07 — Гард завершения при неполной маркировке

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `3930952`  
**Files:** `FfPackagingPage.tsx`, `ff-marking-packaging.spec.ts`

### Critical

_нет_ (traceability gaps — см. warnings)

### Warnings

1. Коллизия TC-ID `TC-NEW-PKG-07` с другим сценарием в test-case doc.
2. Нет runtime proof e2e в TASKLOG.
3. Два критерия неполноты: `qty_done` (гард) vs `qty_need_pack` (PACK-08 подсветка).
4. E2e смешивает PACK-07 и PACK-08 asserts.
5. Нет happy-path «напечатали → complete enabled».
6. Дублирующий import в spec.

### Gate

UI зеркалит `assert_packaging_line_marking_done` ✅ | warning + disabled complete ✅

## LEDGER-05 — Единая модель фильтров

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `411c98f` (integrate `eff8fe4`)

### Critical

_нет_

### Warnings

1. TASKLOG без runtime proof e2e.
2. Нет e2e на debounce «Маска КМ».
3. Stale fetch race в `load()` без abort.
4. 400ms UX gap без индикатора.
5. Файл ~403 строки.

### Gate

«Применить» убрана ✅ | debounce текст / мгновенно select+даты ✅

## POOLS-06 — Один CTA на привязку

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `5cfff27`

### Critical

_нет_

### Warnings

1. Нет e2e на `pool-link-quick` / отсутствие `pool-unlinked`.
2. TASKLOG hash неверный.
3. Два входа: кнопка + меню.
4. Статус «не привязан» убран полностью.

### Gate

Дубль чип+кнопка убран ✅
