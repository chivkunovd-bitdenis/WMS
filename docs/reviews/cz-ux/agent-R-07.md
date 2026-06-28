# Agent R-07 — adversarial review log

## PACK-06 — «Брак»: перезапрос задания + onUpdated

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `1e0d4fd`

### Critical

_нет_

### Warnings

1. Silent fail: успешный defect + failed GET → диалог закрывается без ошибки.
2. E2E не ждёт GET task и не assert'ит счётчики.
3. Backend не меняет counters на pending defect — acceptance «счётчики обновляются» не verifiable на этом шаге.
4. Race: `defectDialogBusy` не блокирует `busy`.
5. Inline GET вместо `refreshTask()`.
6. Нет TASKLOG PACK-06.

### Checklist

- C Async: 3 ISSUE | E Tests: 2 ISSUE

### Gate

T-B2 GET + `onUpdated` после defect ✅ в коде

## LEDGER-03 — Фильтр по диапазону дат

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `34b208e` (integrate `5947737`)

### Critical

_нет_

### Warnings

1. Naive datetime без TZ vs UTC `created_at`.
2. Граница `T23:59:59` может отсечь события.
3. «С > По» — пусто без подсказки.
4. Stale GET race при быстрой смене дат.
5. E2e UTC vs локальный календарь.
6. Pytest: нет partial/inverted range.

### Gate

T-F3 «с/по» + server params ✅ | pytest + e2e ✅

## IMPORT-03 — Убрать тихий кэп 8

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `b665ee6`

### Critical

_нет_

### Warnings

1. Нет e2e на truncation + «Показать ещё».
2. Скрытые `productIds` за кэпом без chips.
3. Modal overflow после expand all.
4. UX parity с pool-dialog.
5. Нет TASKLOG IMPORT-03.

### Gate

Подпись + «Показать ещё» + vitest ✅

## POOLCARD-01 — Локализация статусов кодов

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `117b153`

### Critical

_нет_

### Warnings

1. `STATUS_OPTIONS` неполный (6 из 10 backend enum).
2. CSV export — EN enum.
3. Нет unit fallback `codeStatusLabel`.
4. Узкий e2e (только «Доступен»).
5. Lane bleed с SHARED-01 (`markingStatus.ts`).

### Gate

T-E1 filter + chips RU ✅ | e2e partial ✅

## REPRINTS-02 — Причина отклонения

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `7e3d6d4` (integrate `b108423`)

### Critical

_нет_

### Warnings

1. Нет e2e на reject-dialog + reason в POST.
2. «Видимо заявителю» — UI отсутствует.
3. Reject перезаписывает `req.reason` (причина брака).
4. API не требует non-empty reason.
5. Ошибка reject под модалкой.

### Gate

T-G2 dialog + API reason ✅

## CROSS-04 — «Догрузить» с контекстом пула

**Verdict:** BLOCK  
**Commit:** `bf13014` (merge `14730c2`)

### Critical

1. `poolContext` при re-preview затирает user-edited `title` и re-merge `productIds`.

### Warnings

1. GTIN 13/14 — риск дублей групп.
2. Context только на dashboard cards.
3. E2e seller-only, без assert prefill.
4. Merge bundles IMPORT-05/POOLS-06.

### Gate

T-D4 happy-path ✅ | re-preview edits ❌ → **builder fix**
