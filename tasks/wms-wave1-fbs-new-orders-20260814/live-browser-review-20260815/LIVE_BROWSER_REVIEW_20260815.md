# FBS New Orders Live Browser Review 2026-08-15

Screen: `wave1-fbs-new-orders` / `FBS — Новые заказы`.

Browser: real visible external Google Chrome via CDP/DevTools, not headless, not Playwright acceptance.

URL: `http://127.0.0.1:5186/app/ff/fbs`.

Chrome: `Chrome/151.0.7922.138`.

Live data: local review backend `127.0.0.1:18120`, sqlite `/tmp/wms-fbs-new-orders-live-review.sqlite`, seeded FF admin `fbs-live-review-02981000@example.com`.

## Round 1

Result: passed for the new-orders worklist scenarios after switching the controller to trusted CDP mouse events.

Covered:
- success list with 3 real long rows: WB `880001`, `880002`, `880003`;
- seller/WB warehouse column and filter;
- WB creation date without old 120h deadline text;
- product identifiers without stale route columns;
- product photos loaded from review data URLs;
- search by product/category/SKU style data, highlight and scroll without filtering the list;
- selection persistence across warehouse filter and tab switch;
- selected drawer stability;
- Excel export for selected rows;
- create supply from two compatible orders and workspace read-back with 2 orders;
- reload/read-back: created orders removed from the new-orders list;
- empty seller state;
- no-match search error state keeps the visible list.

Evidence:
- JSON: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/json/live-review-product-round1.json`
- Screenshots: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/82-product-round1-new-orders-initial-long-data-photos.png` through `93-product-round1-search-no-match-error-state-keeps-list.png`
- Excel: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/downloads/fbs-new-orders-2026-08-15.xls`

## Finding

Bucket: Tail.

Issue: partial read-back was present in the backend workspace but not visible in the tracking workspace UI. The alert was rendered only inside the composition stage.

Evidence before fix:
- JSON: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/json/live-review-product-round2-partial.json`
- Screenshot: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/94-product-round2-partial-delivery-row.png`

Fix:
- moved the existing `fbs-partial-rejection` alert to the common workspace content level;
- added an e2e regression for tracking/read-back visibility.

## Round 2

Result: passed after fix.

Evidence:
- JSON: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/json/live-review-product-round2-partial-after-fix.json`
- Screenshot: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/97-product-round2-partial-after-fix-warning-workspace.png`

## ORDER 023 Round 2

Result: the 5 slowdown findings from ORDER 022/023 were fixed and rechecked in a visible external Chrome round.

Covered:
- visible worklist row now shows 3 working identifiers: `WB №`, barcode, SKU or seller article fallback;
- `nmId` and `chrtId` are no longer visible in the working row;
- row height on 1280px viewport is 107px for the three long-data rows;
- long product, seller, and warehouse names stay single-line with hover details;
- primary action is `Забрать заказы из WB`; refresh is demoted to small text action;
- search is live, has no separate `Найти` button, highlights without hiding rows, and no-match keeps the list visible;
- Excel export remains available but does not compete with a removed find step.

Evidence:
- JSON: `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/json/live-review-product-round2-order023.json`
- Screenshots:
  - `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/98-order023-round2-compact-initial.png`
  - `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/99-order023-round2-live-search.png`
  - `tasks/wms-wave1-fbs-new-orders-20260814/live-browser-review-20260815/screenshots/100-order023-round2-live-search-no-match.png`

Round 2 buckets: Stop 0, Slowdown 0, Tail 0.

## Tests

Pre-existing development gate before this live review:
- `cd backend && ruff check .`: passed.
- `cd backend && mypy .`: passed, 251 source files.
- `cd backend && pytest`: 705 passed, 5 skipped, 6 warnings in 2195.08s.
- `cd backend && pytest tests/test_fbs_worklist_query_count.py tests/test_fbs_supply_from_orders.py`: 18 passed, 1 skipped in 40.24s.
- `cd frontend && npm run build`: passed.
- `cd frontend && npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts`: 5 passed in 50.9s.
- `cd frontend && npm run test:e2e -- tests-e2e/ff-fbs-supply.spec.ts`: 3 passed in 21.2s.

After the live-browser fix:
- `cd frontend && npm run build`: passed.
- `E2E_API_PORT=18130 E2E_WEB_PORT=5187 E2E_DB_FILE=e2e-fbs-supply-18130.db npm run test:e2e -- tests-e2e/ff-fbs-supply.spec.ts`: 4 passed in 1.0m.
- `E2E_API_PORT=18131 E2E_WEB_PORT=5188 E2E_DB_FILE=e2e-fbs-orders-18131.db npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts`: 5 passed in 1.2m.

After ORDER 023 compact-worklist fix:
- `cd frontend && npm run build`: passed.
- `E2E_API_PORT=18132 E2E_WEB_PORT=5189 E2E_DB_FILE=e2e-fbs-orders-18132.db npm run test:e2e -- tests-e2e/ff-fbs-orders.spec.ts`: 5 passed in 36.4s.

Known outside-target full e2e state from the interrupted earlier full run:
- `npm run test:e2e`: 96 passed, 13 failed, 1 interrupted, 32 did not run.
- The failures were outside the FBS new-orders target.

## Buckets

Stop: 0.

Slowdown: 0.

Tail: 1, fixed and rechecked in Round 2.

## Scope Guard

FBS-01 files were not changed:
- `backend/app/services/fbs_stock_sync_service.py`
- `backend/app/services/fbs_stock_availability_service.py`
