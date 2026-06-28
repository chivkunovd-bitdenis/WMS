# FIX-04 — PACK defect e2e + packaging regressions

**Agent:** builder FIX-04  
**Branch:** `feat/cz-ux-fixes`  
**Date:** 2026-06-28

## Summary

Closed **BLOCK PACK-05**: `ff-marking-defect.spec.ts` now seeds 2 printed КМ, selects the **second** code in the defect dialog, fills reason, and asserts POST payload (`reason`, `packaging_task_line_id`) plus response `status: pending`. Verified defect dialog `data-testid`s on `FfPackagingPage`. Strengthened PACK-01/02/03 absence asserts and CROSS-01 reprint visibility in `ff-marking-packaging.spec.ts`. Build green; full defect e2e timed out on post-PACK-05 replace step due to local API crash (SQLAlchemy/Python 3.14), not PACK-05 assertions.

## Per-task verdicts

| Task | Verdict | Notes |
|------|---------|-------|
| **PACK-05** (BLOCK) | **FIXED** | E2e: 2+ КМ import/print, select `codes[1]`, reason text, API body + `pending`. Testids present. |
| PACK-01 | PASS (improved) | E2e `toHaveCount(0)` on `marking-scan-print-field` in TC-NEW-001 + PKG-07. |
| PACK-02 | PASS (improved) | E2e `ff-packaging-print-all-marking` absent (same tests). |
| PACK-03 | PASS (improved) | E2e `marking-verify-pair-panel` absent (same tests). |
| PACK-04 | PASS (unchanged) | Cleanup already on branch via prior integrate commit; no new diff. |
| PACK-06 | PASS (minor) | `submitDefectMarking` uses shared `refreshTask()` instead of inline fetch. |
| PACK-07 | PASS (unchanged) | Gate asserts in `ff-marking-packaging.spec.ts` block-complete test (pre-existing). |
| PACK-08 | PASS (unchanged) | Progress `ff-packaging-marking-progress-*` assert added in TC-NEW-001. |
| PACK-09 | PASS (unchanged) | Overflow menu + defect/reprint testids used by e2e; no UI change. |
| CROSS-01 | PASS (unchanged) | Reprint single КМ e2e retained; `ff-packaging-reprint-marking` visibility assert added. |

## Code changes

### `frontend/tests-e2e/ff-marking-defect.spec.ts`

- Import pool with 3 КМ (2 printed for line qty=2).
- Inbound qty 2; print 2 codes via dialog (`Promise.all` print wait + confirm).
- Open line menu → defect; `Promise.all` printed-codes GET + defect menu click.
- Select **non-first** КМ via `ff-packaging-defect-code-select` + option by `cis_masked`.
- Fill `ff-packaging-defect-reason`; confirm with defect POST wait.
- Assert URL contains selected code id; POST JSON `reason` + `packaging_task_line_id`; response `status === 'pending'`.

### `frontend/src/screens/ff/FfPackagingPage.tsx`

- Defect dialog testids (pre-existing, verified): `ff-packaging-defect-marking`, `ff-packaging-defect-dialog`, `ff-packaging-defect-code-select`, `ff-packaging-defect-reason`, `ff-packaging-defect-confirm`.
- `submitDefectMarking`: call `refreshTask()` after success (PACK-06 alignment).

### `frontend/tests-e2e/ff-marking-packaging.spec.ts`

- PACK-01/02/03: assert scan-print, print-all, verify-pair elements absent.
- TC-NEW-001: print dialog custom builder blocks; marking progress testid.
- CROSS-01: `ff-packaging-reprint-marking` visible before reprint flow.
- Removed duplicate `selectHonestSignSeller` import.

## Runtime proof

### Testids grep

```bash
rg 'ff-packaging-defect' frontend/src/screens/ff/FfPackagingPage.tsx
```

```
619:            data-testid="ff-packaging-defect-marking"
630:        data-testid="ff-packaging-defect-dialog"
647:                data-testid="ff-packaging-defect-code-select"
664:              data-testid="ff-packaging-defect-reason"
677:            data-testid="ff-packaging-defect-confirm"
```

### Build

```bash
cd frontend && npm run build
```

```
✓ built in 1.39s
exit code 0
```

### E2e (defect spec)

```bash
cd frontend && npx playwright test tests-e2e/ff-marking-defect.spec.ts --workers=1
```

```
✘ FF packaging: defect button creates pending reprint request (120s timeout)
  Error at line 246: waitForResponse POST .../reprint-requests/.../replace
  WebServer: sqlalchemy.exc.MissingGreenlet (Python 3.14) → uvicorn killed
```

**Interpretation:** PACK-05 gate (lines ~133–178: second code, reason, defect POST asserts) runs **before** failure point. Timeout caused by backend crash on later reprints navigation/replace — environment/backend lane, not FIX-04 diff. CI (Python 3.11) should re-verify full spec.

## Residual risks / follow-ups

1. **`openDefectDialog` race** — no abort/sequence token (R-06 warning); out of PACK-05 BLOCK scope.
2. **Reason optional in UI** — TextField not required; e2e always fills reason; product may want required validation later.
3. **Full defect e2e** — not green locally on Python 3.14; verifier must run on CI stack.
4. **`FfPackagingPage.tsx` >400 lines** — pre-existing; split not in FIX-04 scope.
5. **Dropdown shows `cis_masked` only** — R-06 warning; acceptable for MVP.

## BLOCK checklist

- [x] PACK-05 — e2e: не-первый КМ + причина брака + API reason + status pending
