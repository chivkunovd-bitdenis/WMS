# FIX-02 — Import dialog (MarkingImportDialog)

**Agent:** builder FIX-02  
**Branch:** `feat/cz-ux-fixes`  
**Date:** 2026-06-28

## Summary

Closed **BLOCK CROSS-04**: re-preview no longer re-applies `poolContext` over user-edited `title` / `productIds` on existing groups. Added `AbortController` for preview race. Unit tests extended; build green.

## Per-task verdicts

| Task | Verdict | Notes |
|------|---------|-------|
| **CROSS-04** (BLOCK) | **FIXED** | `mergePreviewGroups` skips `applyPoolContextToGroup` for existing groups; lookup via `gtinMatches` (13/14-digit). Pool context applies only on first preview / new GTIN. |
| IMPORT-01 | PASS (unchanged) | GTIN merge + preserve edits; CROSS-04 was the gap — now closed. |
| IMPORT-02 | PASS (unchanged) | Per-group `productSearch` already isolated. |
| IMPORT-03 | PASS (improved) | Cap 8 already surfaced («Показать ещё» + caption). Added «· выбрано N» when list truncated and products selected. |
| IMPORT-04 | PASS (unchanged) | File chip delete → `runPreview`; merge preserves group state. |
| IMPORT-05 | PASS (unchanged) | Empty title → error border, scroll, `-title-missing` testid. |
| CROSS-03 | N/A | Seller `MarkingSellerPicker` lives in `HonestSignScreen.tsx` (FIX-03/05 lane). |

## Code changes

### `MarkingImportDialog.tsx`

1. **`mergePreviewGroups`** — existing groups: copy `title`, `productIds`, `productSearch` only; do **not** call `applyPoolContextToGroup`. New groups: still prefill from `poolContext`.
2. **`findExistingGroupByGtin`** — match prev groups with `gtinMatches` (13↔14 digit).
3. **`runPreview`** — `AbortController` cancels stale preview; abort on dialog `reset`.
4. **IMPORT-03** — truncated product list shows selected count.

### `markingImportMerge.test.ts`

- `does not re-apply pool context on re-preview for existing groups`
- `preserves user edits when re-preview uses 14-digit gtin variant`

### `ff-honest-sign-import.spec.ts`

- No change (happy-path import + duplicate re-import already cover TC-NEW-008).

## Runtime proof

### Unit tests

```bash
cd frontend && npm run test:unit -- markingImportMerge
```

```
 ✓ src/screens/shared/markingImportMerge.test.ts (17 tests) 6ms
 Test Files  1 passed (1)
      Tests  17 passed (17)
```

### Build

```bash
cd frontend && npm run build
```

```
✓ built in 2.07s
exit code 0
```

## Residual risks / follow-ups

1. **E2e pool-context re-preview** — no Playwright for «Догрузить КМ» + edit title + add second file; covered by unit tests only.
2. **E2e IMPORT-05** — submit without title not in e2e (unit helpers cover validation).
3. **Hidden selected products** — count shown when truncated; chips for off-screen selections still out of scope.
4. **File >400 lines** — `MarkingImportDialog.tsx` pre-existing size debt.

## BLOCK checklist

- [x] CROSS-04 — poolContext не затирает title/productIds при re-preview
