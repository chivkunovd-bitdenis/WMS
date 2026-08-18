# Final Browser Regression Rerun: inbound / reception / returns / seller fact-card

Дата прогона: 2026-08-14
Репозиторий: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
Evidence folder: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-inbound-live-strict`

Verdict: `FINAL_BROWSER_GROUP_FAILED`

`browser_used`: yes
Browser surface: real Chromium via Playwright, `headless=false`, viewport `1280x720`. Browser plugin was attempted first, but in-app browser could not create a visible tab in the subagent thread, and Chrome extension browser was unavailable; fallback to Playwright Chromium was used because the task explicitly allowed Chromium/Chrome Playwright `headless=false`.

Ports:

- Backend: `127.0.0.1:18182`
- Frontend/Vite: `127.0.0.1:5182`
- SQLite: `qa-final.sqlite` in this evidence folder

## Scope Covered

Checked live in browser:

- Seller inbound / FF reception / dimensions / discrepancy / print
- Return inbound / return autoprint / WB barcode scan
- Seller `/seller/documents` completed inbound fact-card
- Features in requested group: F01-F06, F18, F19, plus connected reception UX

No code, commit, push, staging, production, Railway, or secrets were touched.

## Fixture

Created on clean local backend/sqlite:

- FF admin: `ff-admin-final-inbound-1786666957465@example.com`
- Seller account: `seller-final-inbound-1786666957465@example.com`
- Seller: `QA Seller final-inbound-1786666957465`
- Warehouse/location: `QA WH final-inbound-1786666957465`, location `A-01`
- Ordinary product: `sku-ordinary-final-inbound-1786666957465`, WB barcode `wb-ordinary-final-inbound-1786666957465`
- Return product: `sku-return-final-inbound-1786666957465`, WB barcode `wb-return-final-inbound-1786666957465`
- Ordinary inbound: `cfd99469-43f3-48b8-b5d9-c826c1ca768b`
- Return inbound: `b456ca6e-0aae-498e-a0de-5d30920ffcae`

Raw fixture and run data:

- `json/run-live.json`
- `json/run-live-continuation.json`
- `json/ordinary-waybill-print.html.json`
- `json/return-autoprint-capture-continuation.json`

## Routes

Live routes opened:

- `/`
- `/app/ff/reception`
- `/seller/`
- `/seller/documents`
- `/seller/inbound/cfd99469-43f3-48b8-b5d9-c826c1ca768b`

## Click Path

Ordinary inbound path:

- Opened FF registration, created FF admin.
- Opened FF sidebar `Приёмка`.
- Opened ordinary inbound from `/app/ff/reception`.
- Edited dimensions to `210×110×60 мм`; UI read back `1.39 л`.
- Scanned SKU `sku-ordinary-final-inbound-1786666957465`; fact became `1`.
- Manually corrected fact to `3`.
- Clicked `Завершить приёмку`, confirmed discrepancy dialog with `Недостача 2`.
- Status changed to `В сортировке`.
- Clicked `Печать накладной`; captured print HTML contains `Недостача 2`, SKU, seller name, and does not expose request UUID, warehouse UUID, `status`, `sorting`, FBS/WB order noise.

Return path:

- Reopened FF `/app/ff/reception` in live Chromium.
- Opened return inbound.
- Verified visible `Тип: Возврат`.
- Enabled `Печатать ШК при скане`.
- Scanned WB barcode `wb-return-final-inbound-1786666957465`.
- Captured autoprint payload: product name plus WB barcode.
- Fact read back as `1 из 1`.

Seller fact-card path:

- Opened `/seller/documents`.
- Opened completed ordinary inbound fact-card.
- Verified read-only state: no draft form, add-products button, submit button, save draft button, or line delete control.
- Verified human readback: `Заявлено 5`, `принято 3`, `Недостача 2`, `Есть расхождения`.
- Checked no raw UUID/status/error-code noise in visible seller body for the tested IDs/technical strings.

## Screenshots

Key screenshots:

- `screenshots/02-ff-reception-queue-final.png`
- `screenshots/03-ordinary-open-final.png`
- `screenshots/04-ordinary-dimensions-saved-final.png`
- `screenshots/05-ordinary-after-scan-final.png`
- `screenshots/06-ordinary-manual-discrepancy-final.png`
- `screenshots/07-ordinary-discrepancy-dialog-final.png`
- `screenshots/08-ordinary-completed-final.png`
- `screenshots/14-return-open-continuation.png`
- `screenshots/15-return-after-autoprint-continuation.png`
- `screenshots/16-seller-documents-continuation.png`
- `screenshots/17-seller-fact-card-continuation.png`

## Metrics

Measured at `1280x720`:

- Ordinary login, queue, ordinary open, ordinary completed: `documentScrollWidth=1280`, `bodyScrollWidth=1280`, `appRootScrollWidth=1280`.
- Return queue, return open, return after autoprint: `documentScrollWidth=1280`, `bodyScrollWidth=1280`, `appRootScrollWidth=1280`.
- Seller documents and seller fact-card: `documentScrollWidth=1280`, `bodyScrollWidth=1280`, `appRootScrollWidth=1280`.

No page-level horizontal overflow was detected in collected metrics. No black strip was visible on checked screenshots. Return controls and seller fact-card text/buttons were not clipped at the 1280px viewport.

## Blocker

After successful ordinary inbound completion with discrepancy, the discrepancy dialog stayed visibly open on top of the already completed document. Evidence: `screenshots/08-ordinary-completed-final.png`.

Why this fails the product gate:

- The document behind the modal already shows status `В сортировке` and accepted fact `3 из 5`.
- The modal still says `Есть расхождения, провести приёмку?`, which is now stale.
- The modal still shows the discrepancy table and a disabled `Завершить приёмку` button, leaving the worker in an unclear state after the operation has already succeeded.
- This violates the required product judgement: visible controls must justify warehouse work and not leave the operator with stale/unclear state.

Return and seller fact-card passed their checked paths, but the group cannot pass because the ordinary discrepancy-completion UX is failed in the live browser.
