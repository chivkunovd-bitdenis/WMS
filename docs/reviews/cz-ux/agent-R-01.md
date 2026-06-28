# Agent R-01 — adversarial review log

## SHARED-01 — Словарь статусов/событий

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `a05ff56`  
**Files:** `markingStatus.ts`, `MarkingProductCodesDialog.tsx`

### Critical

_нет_

### Warnings

1. Нет отдельной строки TASKLOG для SHARED-01.
2. Нет unit-теста на fallback `codeStatusLabel`/`ledgerEventLabel`.
3. `MarkingProductCodesDialog` deprecated — gate в коде OK, e2e косвенно через POOLCARD-01.
4. Экспорт raw `CODE_STATUS_LABELS`/`LEDGER_EVENT_LABELS` — лишний публичный API.

### Checklist

- A: OK | E: ISSUE (нет unit) | F: ISSUE (TASKLOG)

### Contract gaps

Gate «словарь готов» ✅ | «диалог использует codeStatusLabel» ✅ | TASKLOG ⚠️

## PRINT-04 — Множитель × упаковка (каталог + упаковка)

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `435f9c2`  
**Files:** `productBarcodePrint.ts`, `ProductBarcodePrintDialog.tsx`, `MarkingPrintDialog.tsx`

### Critical

_нет_

### Warnings

1. Нет e2e на gate 3×5→15 (только unit).
2. `productDisplayMetaFromCatalog` не прокидывает `packaging_instructions`.
3. Дефолт `wbBarcodeQty=1` на упаковке вместо `qtyNeedPack`.
4. Мёртвый параметр `packUnits?` в `printProductBarcodeLabel`.
5. Regex парсинга ТЗ — риск ложных срабатываний.

### Gate

Каталог + упаковка × pack ✅ | unit 3×5→15 ✅

## IMPORT-04 — Удаление файла из импорта

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `dd0ef33`

### Critical

_нет_

### Warnings

1. Нет e2e на удаление чипа.
2. Stale groups при ошибке re-preview.
3. File input не сбрасывается после delete.
4. Нет integration unit на исчезновение GTIN.

### Gate

`onDelete` на чипах ✅ | `runPreview` / `clearPreview` ✅

## REPRINTS-01 — Объяснить «Подтвердить/Заменить»

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `4411f4b`

### Critical

_нет_

### Warnings

1. Нет TASKLOG REPRINTS-01.
2. Нет e2e на help-блок.
3. «Заменить» без confirm.
4. Дубль коммитов `4411f4b`/`8949fe7`.

### Gate

Alert + Tooltip с последствиями ✅

## FINAL-02 — Аудит дублей поверхностей ЧЗ

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `f048585` (merge LEDGER-06 + POOLCARD-03 + правки FINAL-02)  
**Files reviewed:** `docs/CZ_DUPLICATE_SURFACES_AUDIT_RU.md`, `HonestSignImportPage.tsx`, `HonestSignPoolPage.tsx`, `MarkingProductCodesDialog.tsx`, `App.tsx`, `ff-honest-sign-pool.spec.ts`

### Critical

_нет_

### Warnings

1. **Merge-коммит не изолирован** — `f048585` объединяет LEDGER-06, POOLCARD-03 и FINAL-02; diff 7 файлов, ревью «только FINAL-02» затруднено.
2. **`MarkingProductCodesDialog` — мёртвый код** — `@deprecated`, нигде не импортируется; файл оставлен по аудиту — техдолг.
3. **Локализация событий не везде** — `FfHonestSignReprintsPage` drawer «История кода» показывает сырой `event_type`; в пуле уже `ledgerEventLabel`.
4. **`HonestSignPoolPage.tsx` 660 строк** — >400, merge увеличил файл.
5. **Нет e2e «сирота недоступна»** — только static grep + deprecated.
6. **§4 аудита** — дубли дашборд/таблица, KPI, CTA остаются в backlog (POOLS-02…06).

### Gate

План дублей ✅ | редирект `/import` ✅ | локализация превью ✅ | e2e TC-NEW-012 ✅
