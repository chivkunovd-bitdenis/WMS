# Final Integration Review Strict — WMS product operations UX 2026-08-12

Дата проверки: 2026-08-14, Europe/Moscow.

Роль: Final Integration Review Agent, read-only.

Рабочий Git-root:

```text
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Ветка: `iteration/wms-product-ux-features-20260812`.

HEAD на момент проверки: `d59959de70a8b9d447f200bdb703023c35b7b449`.

## Verdict

`FINAL_INTEGRATION_FAILED`

Коротко: по документам есть strict/live Product Browser approval для всех 21 active release features (`F01-F19`, `F22`, `F23`), и я не засчитывал старые paper/e2e-only статусы как proof. Но итоговая интеграция не проходит из-за подтвержденного backend red flag в F12: monthly stock snapshots сейчас доступны seller-token с `200 OK`, хотя текущий test contract требует `403` для seller. Это ломает границу FF inventory/admin surface vs seller portal и не позволяет запускать final browser regression как следующий release gate.

Отдельно: это не final browser regression, не stage approval, не release-ready statement и не deploy permission.

## Scope

Active release scope: 21 фича.

- Included: `F01`, `F02`, `F03`, `F04`, `F05`, `F06`, `F07`, `F08`, `F09`, `F10`, `F11`, `F12`, `F13`, `F14`, `F15`, `F16`, `F17`, `F18`, `F19`, `F22`, `F23`.
- Excluded: `F20` out of scope by user, `F21` blocked/missing target repo for `sellerfocus.pro`.

## Sources Read

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/HANDOFF_TO_NEW_CHAT_STRICT_WMS_GATE_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/STRICT_PRODUCT_RECERT_AUDIT_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`
- Relevant strict/final evidence for `F05`, `F07/R01`, `F12/F14/R02`, `F15`
- Strict recert evidence for `F01-F19`, `F22`, `F23`
- Current scoped code/test files around failing F12 access contract

## Numeric Gate Table

| Metric | Count |
| --- | ---: |
| total_features | 21 |
| ba_ready | 21 |
| product_reviewed | 21 |
| product_approved_for_dev | 21 |
| product_rework_required | 0 current unresolved product verdicts in final evidence |
| dev_done | 21 documented, but final backend integration red flag remains |
| code_review_passed | 21 documented, but current targeted backend pytest has 1 failing test |
| browser_product_qa_passed | 21 documented strict/live approvals |
| browser_product_qa_failed | 0 current final approvals; old failed/rework artifacts are historical |
| browser_product_qa_blocked | 0 current final approvals |
| integrated | 0 |
| final_regression_passed | 0 |

## Per-Feature Evidence Check

| Feature(s) | Final evidence accepted for this review | Evidence status |
| --- | --- | --- |
| F01-F04 | `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md` | Strict Product / UX live browser pass; `browser_used` effectively yes via headed Chromium, real DOM clicks, URL/ports/screenshots recorded. File is currently untracked. |
| F05 | `evidence/f05-product-browser-qa-rerun-live-strict/F05_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` | Final live Product Browser QA approved seller fact-card and seller shell reload/nav. File is tracked. |
| F06, F18, F19 | `evidence/strict-product-recert-live-f05-f06-f18-f19/STRICT_PRODUCT_LIVE_REPORT_RU.md` plus later F05-specific rerun for F05 | F06/F18/F19 strict live approved; historical F05 rework in this file is superseded by later F05 rerun. Strict recert file is currently untracked. |
| F07/R01 and F17 | `evidence/r01-packaging-product-browser-qa-rerun-live-strict/R01_PACKAGING_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` plus `evidence/r01-backend-compat-code-review-strict/R01_BACKEND_COMPAT_CODE_REVIEW_STRICT_RU.md` | Final live packaging QA approved; old R01 code-review failed artifacts are superseded by backend compatibility code review pass. Final R01 QA file is currently untracked. |
| F08-F11, F16, F22, F23 | `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md` | Strict live catalog/stock pass with local Chromium, API, Vite and WB emulator. File is currently untracked. |
| F12/F14/R02 | `evidence/r02-staff-nav-product-browser-qa-final-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_FINAL_LIVE_STRICT_RU.md` plus `evidence/r02-surface-guard-code-review-strict/R02_SURFACE_GUARD_CODE_REVIEW_STRICT_RU.md` | Final live Product Browser QA approved route/sidebar/direct-route matrix and FF/seller surface guard. File is tracked. However backend monthly snapshot seller access test now fails; see blocker P0 below. |
| F13 | `evidence/strict-product-recert-live-f12-f15/STRICT_PRODUCT_RECERT_LIVE_F12_F15_RU.md` | Strict live F13 approved. Same file also contains historical F12/F14/F15 rework statuses superseded by later R02/F15 reruns. File is currently untracked. |
| F15 | `evidence/f15-product-browser-qa-rerun-live-strict/F15_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md` plus `evidence/f15-code-review-final-strict/F15_CODE_REVIEW_FINAL_STRICT_RU.md` | Final live QA approved delete-only-drafts across seller and FF MP unload/box-line statuses. File is tracked. |

Conclusion: I found strict/live product evidence for every active feature, but evidence durability is incomplete because several central evidence files and `STRICT_PRODUCT_RECERT_AUDIT_RU.md` are untracked in the current worktree.

## Blockers

### P0 — F12 monthly snapshot API leaks to seller-token

Current endpoint:

- `backend/app/api/inventory_balances.py`
- `GET /operations/inventory-balances/monthly-snapshots`

The endpoint calls the generic `assert_inventory_read_access(session, user)`. That helper currently allows `FULFILLMENT_SELLER` with product permission. For ordinary inventory summaries this may be intended, but F12 monthly snapshot is documented/tested as FF admin/inventory-staff surface. The targeted test explicitly requires:

- FF admin: `200`;
- FF staff with `inventory=true`: `200`;
- FF staff without inventory: `403`;
- seller-token: `403`.

Actual current result: seller-token gets `200`.

Commands run:

```bash
cd backend
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms_final_integration_backend_tests_1786664200.sqlite \
uv run --frozen pytest \
  tests/test_packaging_tasks.py \
  tests/test_marking_pending.py \
  tests/test_fbs_packaging_integration.py \
  tests/test_fbs_packaging_fulfillment.py \
  tests/test_product_packaging_instructions.py \
  tests/test_staff_packaging_billing.py \
  tests/test_marketplace_unload_and_discrepancy_acts.py \
  tests/test_stock_directions.py \
  tests/test_seller_shop_scope.py \
  tests/test_staff_users.py \
  tests/test_inbound_intake.py \
  -q -p no:cacheprovider
```

Result: `1 failed, 82 passed`.

Failing test:

```text
tests/test_stock_directions.py::test_monthly_stock_snapshot_get_requires_ff_inventory_access
assert blocked_seller.status_code == 403
E assert 200 == 403
```

Single-test confirmation on a fresh SQLite DB:

```bash
cd backend
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms_final_integration_f12_single_1786664300.sqlite \
uv run --frozen pytest \
  tests/test_stock_directions.py::test_monthly_stock_snapshot_get_requires_ff_inventory_access \
  -q -p no:cacheprovider
```

Result: same failure, `1 failed`.

Owner / next action: F12/R02 Atomic Dev must narrow monthly snapshot GET access so seller-token cannot read this FF inventory snapshot endpoint, or explicitly change the product/API contract and tests through the proper Product/UX gate. Then Code Review must rerun the F12/R02 backend access scope, and Product Browser QA should rerun if any visible route/error surface changes.

### P1 — Release truth is not durable in Git yet

The branch is ahead of origin and the worktree is broadly dirty. Some final evidence files are tracked, but several central strict recert artifacts used by this review are untracked:

- `docs/reviews/product-operations-ux/2026-08-12/STRICT_PRODUCT_RECERT_AUDIT_RU.md`
- `evidence/strict-product-recert-live-f01-f04/QA_RESULT_RU.md`
- `evidence/strict-product-recert-catalog-stock-live/STRICT_LIVE_RECERT_REPORT_RU.md`
- `evidence/strict-product-recert-live-f05-f06-f18-f19/STRICT_PRODUCT_LIVE_REPORT_RU.md`
- `evidence/strict-product-recert-live-f12-f15/STRICT_PRODUCT_RECERT_LIVE_F12_F15_RU.md`
- `evidence/r01-packaging-product-browser-qa-rerun-live-strict/R01_PACKAGING_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md`

This does not invalidate the local review, but it means the evidence set is not recoverable from HEAD alone. Under the repo contract, no release/staging/ready claim may be made until scoped evidence and code are committed and the resulting SHA is known. I did not commit or push because the user explicitly forbade it.

Owner / next action: after the F12 blocker is fixed and gates rerun, Integration Owner must stage only exact release/evidence files, avoid `git add .`, commit scoped changes, record SHA, and push only if explicitly allowed.

### P1 — Status documents still contain old unsafe "passed" claims

There are older documents that still claim final integration/browser regression passed for the earlier, pre-strict interpretation:

- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FINAL_INTEGRATION_REVIEW_RU.md` says status passed and records a final browser regression.
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_PRODUCT_GATE_RU.md` has a "Финальный gate после общего browser regression" section with `passed`.

The later handoff and strict recert documents say the opposite: old passed statuses cannot be trusted, a new strict Final Integration Review is required, and final browser regression must run only after this review passes. The chronological meaning is understandable, but the release source of truth is still easy to misread.

Owner / next action: after the code blocker is resolved, a docs-only gate cleanup should mark those older reports as superseded by the strict handoff/strict recert/final integration artifacts, without pretending the old final regression is current.

## Non-Blocking Checks Passed In This Review

### Backend Ruff

Command:

```bash
cd backend
RUFF_CACHE_DIR=/tmp/wms-final-integration-review-ruff-cache uv run --frozen ruff check .
```

Result: `All checks passed!`.

### Diff Check

Command:

```bash
git diff --check
```

Result: passed, no whitespace/conflict-marker output.

### TypeScript Dry Build

Command:

```bash
cd frontend
npm exec tsc -- -b --dry --pretty false
```

Result: dry mode reported that a non-dry build would build `tsconfig.app.json` and `tsconfig.node.json`. This is not a real build pass.

I did not run `npm run build` in this read-only review because the script writes to `frontend/dist` and TypeScript build info under `frontend/node_modules/.tmp`. Previous scoped evidence files report successful builds, but this final review did not produce a fresh non-mutating frontend build verdict.

## Final Browser Regression Requirement

Final browser regression was not run in this review, by task definition and because this review failed.

After the F12 blocker is fixed and a repeat Final Integration Review passes, a separate final live Product Browser Regression must cover at minimum:

- FF inbound: F01-F06/F18/F19 including scan, discrepancy, dimensions, manual product, fact waybill, return/autoprint.
- Seller inbound fact-card: F05 shell ownership, reload/read-back, compact discrepancy/clean card.
- Packaging/MP/FBO/FBS: F07/R01, F15, F17 including packaging queue, create, mixed seller block, scanner/manual/undo, pending marking, MP print/final, delete-only-drafts.
- Catalog/stocks/WB sync: F08-F11/F16/F22/F23 including directions, FBS pool, free FBO, safe sync, seller catalog cleanup, FF catalog.
- Staff/access: F12/F13/F14/R02 including FF staff menu/direct-route parity, seller access scope, monthly snapshot access and cross-app surface guard.

Only after that separate regression passes can release/staging readiness even be discussed.

## Final State

- local: dirty worktree, branch ahead of origin, many modified/untracked code/docs/evidence files.
- committed: current HEAD `d59959de70a8b9d447f200bdb703023c35b7b449`, but this review artifact and several strict evidence files are not committed.
- pushed: not pushed by this agent.
- deployed: not deployed; staging/Railway/production not touched.
- browser-tested: per-feature strict/live evidence exists, but this agent did not run final browser regression.
- remaining risks: F12 backend access leak, uncommitted evidence state, old docs with superseded passed claims, low disk headroom observed during review (`df -h .` showed about `1.1GiB` available).

Final verdict remains:

`FINAL_INTEGRATION_FAILED`
