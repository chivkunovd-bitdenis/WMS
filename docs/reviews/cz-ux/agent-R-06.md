# Agent R-06 — adversarial review log

## PACK-05 — «Брак»: выбор кода + причина

**Verdict:** BLOCK  
**Commit:** `1b94a53`

### Critical

1. E2E не доказывает выбор не-первого КМ (один код, дефолт `codes[0]`).
2. E2E не заполняет/не проверяет поле причины (T-B1 / ORD-10).

### Warnings

- Race в `openDefectDialog` без abort/sequence token.
- Причина опциональна в UI vs «указать причину» в acceptance.
- Дропдаун: только `cis_masked`.

### Checklist

- E Tests: 2 critical ISSUE | C Async: ISSUE (race)

### Next

Builder: расширить `ff-marking-defect.spec.ts` — 2 КМ, select 2-й, reason, assert API.

## LEDGER-02 — Серверный поиск по маске КМ

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `2927cd6`

### Critical

_нет_

### Warnings

1. Pytest не доказывает cross-page поиск (>limit).
2. Нет e2e на `cis-mask`.
3. `load()` без abort — race out-of-order.
4. `normalize_cis_mask_query` без unit-теста.

### Gate

Маска на сервер до пагинации ✅ | client filter убран ✅

## POOLS-03 — Tooltip на disabled «Загрузить коды»

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `416069c`

### Critical

_нет_

### Warnings

1. Empty-state `empty-upload` — dead click без tooltip.
2. 0 sellers — misleading tooltip.
3. Нет e2e на tooltip.
4. Копирайт vs T-D3.

### Gate

Toolbar disabled + Tooltip + span-wrapper ✅

## PENDING-01 — Массовая печать по списку

**Verdict:** APPROVE WITH WARNINGS  
**Commits:** `ea31ed5`, `c93286c`, `1dffbba`

### Critical

_нет_

### Warnings

1. `load()` → мигание «Загрузка…» между диалогами.
2. Отмена не очищает `printQueueRef`.
3. Повторный bulk без guard.
4. E2e ослаблен (нет assert product header).
5. Magic `setTimeout` в очереди.

### Gate

Чекбоксы + sequential per-line dialog ✅ | TC-NEW-008 ✅
