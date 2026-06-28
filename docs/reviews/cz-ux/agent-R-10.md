# Agent R-10 — adversarial review log

## PACK-09 — Действия в overflow-меню

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `dafaf8b` (+ e2e `280944b` CROSS-01)

### Critical

_нет_

### Warnings

1. Нет отдельной записи TASKLOG для PACK-09.
2. E2e `.first()` на menu-btn — хрупко при multi-line.
3. Gate «≤2–3 видимых кнопки» не покрыт автотестом.
4. MP-unload defect-only path без e2e.
5. `FfPackagingPage.tsx` >400 строк (pre-existing).

### Checklist

- A: ISSUE (file size) | E: ISSUE (gate-count) | F: ISSUE (TASKLOG)

### Gate

Повтор/Брак в overflow ✅ | eligibility сохранена ✅

## LEDGER-04 — Экспорт ленты по фильтрам

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `d549c18` (integrate `b5024d0`)

### Critical

_нет_

### Warnings

1. Нет Playwright e2e на «Экспорт».
2. `export_too_large` — нет RU-сообщения и pytest.
3. CSV `event_type` на EN, UI — RU.
4. Debounce → экспорт может отстать от ввода.
5. Хрупкий pytest `"imported" in line`.
6. Нет export parity для date/cis_mask.

### Gate

Серверный экспорт по фильтрам ✅ | CSV count = ledger.total ✅

## POOLS-01 — Селлер через Autocomplete

**Verdict:** APPROVE WITH WARNINGS  
**Commits:** `af63c35`, `ce55f5a` (+ `MarkingSellerPicker` CROSS-03)

### Critical

_нет_

### Warnings

1. Gate «30+» — нет e2e search.
2. TASKLOG дублирует TASK-037.
3. Duplicate import в `ff-marking-packaging.spec.ts`.
4. Clearable Autocomplete без подсказки.
5. `noOptionsText` не покрыт e2e.

### Gate

Кнопки → Autocomplete ✅ | testids ✅

## POOLS-05 — Единый формат прогноза

**Verdict:** APPROVE WITH WARNINGS  
**Commit:** `c32df5d` (integrate `63a4aa0`)

### Critical

_нет_

### Warnings

1. Нет e2e на ForecastLabel / parity таблица↔карточки.
2. `HonestSignPoolPage` — сырые `forecast_days` (UX drift).
3. `ForecastLabel` не shared; файл 737 строк.
4. testId прогноза только в таблице.

### Gate

Таблица + карточки HonestSignScreen — один формат ✅

## CROSS-02 — Контракт pending-marking total vs rows

**Verdict:** APPROVE WITH WARNINGS  
**Commits:** `c997485`, `d8ccd35` (merge `91ba65c`)

### Critical

_нет_

### Warnings

1. `total > 200` — chip/badge ≠ видимых строк.
2. Ошибка API → badge 0 без сообщения.
3. Generic error strings.
4. Нет unit-тестов helper.

### Gate

Бейдж = chip = row count (≤200) ✅ | e2e TC-NEW-011 ✅
