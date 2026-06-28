# FIX-03 — Terminology (КМ/ЧЗ) + e2e sync

**Agent:** builder FIX-03  
**Branch:** `feat/cz-ux-fixes`  
**Date:** 2026-06-28

## Summary

Closed **BLOCK FINAL-01**: user-visible «код/кодов» replaced with **КМ** in pool export captions, reprints history, import nav placeholder, print error; e2e `marking-print-will-print` aligned with UI. Addressed LEDGER-06 / POOLCARD-01 warnings in scope (localized event types in reprints drawer, RU status in CSV). Build green.

## Per-task verdicts

| Task | Verdict | Notes |
|------|---------|-------|
| **FINAL-01** (BLOCK) | **FIXED** | E2e «1 КМ»; pool/reprints/App/printMarkingCodeLabel strings updated. |
| SHARED-01 | PASS (unchanged) | `markingStatus.ts` dictionary already RU; no code change. |
| POOLCARD-01 | PASS (improved) | CSV status column uses `codeStatusLabel()` instead of EN enum. |
| LEDGER-06 | PASS (improved) | Reprints history drawer uses `ledgerEventLabel()` instead of raw `event_type`. |
| POOLS-03 | N/A | «Загрузить КМ» already in `HonestSignScreen.tsx` (FIX-05 lane). |

## Code changes

### `frontend/tests-e2e/ff-marking-packaging.spec.ts`

- Expect `marking-print-will-print`: `К перепечатке: 1 КМ` (was `1 код`).

### `frontend/src/screens/shared/HonestSignPoolPage.tsx`

- Export count captions: «N КМ» / «N КМ пула» / «N КМ выборки».
- CSV export: status column localized via `codeStatusLabel`.

### `frontend/src/screens/ff/FfHonestSignReprintsPage.tsx`

- Link + drawer title: «История КМ».
- Hint texts: consistent КМ wording (no «код маркировки» / «Старый код»).
- History events: `ledgerEventLabel(ev.event_type)`.

### `frontend/src/App.tsx`

- FF import placeholder nav title: «Загрузка КМ» (only honest-sign import route).

### `frontend/src/utils/printMarkingCodeLabel.ts`

- Empty batch error: «Нет КМ для печати.»

## Runtime proof

### Grep (exclusive files)

```bash
rg 'кодов|История кода|Нет кодов|Загрузка кодов' \
  frontend/src/screens/shared/HonestSignPoolPage.tsx \
  frontend/src/screens/ff/FfHonestSignReprintsPage.tsx \
  frontend/src/utils/printMarkingCodeLabel.ts \
  frontend/src/App.tsx
```

No matches in changed user-visible strings (App retains «код ячейки» for warehouse cells — out of scope).

### Build

```bash
cd frontend && npm run build
```

```
✓ built in 1.36s
exit code 0
```

## Residual risks / follow-ups

1. **No terminology lint gate** — grep manual only; other lanes (FIX-04/05) may still have «код» outside this slice.
2. **SHARED-01** — no unit test for `codeStatusLabel` / `ledgerEventLabel` fallback (FIX-05 or separate chore).
3. **POOLCARD-01** — `STATUS_OPTIONS` still subset of backend enum (screen filter, not labels module).
4. **LEDGER-06** — `HonestSignLedgerPage` filter `EVENT_TYPES` still 6/10 (FIX-05 lane).
5. **E2e** — terminology assert only; full `test:e2e` not run in this step (verifier).

## BLOCK checklist

- [x] FINAL-01 — терминология + e2e «1 КМ»
