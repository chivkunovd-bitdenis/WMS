# Final Browser Regression Rerun: inbound stale-modal fix

Дата прогона: 2026-08-14
Репозиторий: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
Evidence folder: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-inbound-after-fix-live-strict`

Verdict: `FINAL_BROWSER_GROUP_PASSED`

`browser_used`: yes
Browser surface: real Chromium via Playwright, `headless=false`, viewport `1280x720`.

Ports:

- Backend: `127.0.0.1:18221`
- Frontend/Vite: `127.0.0.1:5221`
- SQLite: `qa-18221.sqlite` in this evidence folder

No code, commit, push, staging, production, Railway, or secrets were touched. Only screenshots, JSON, sqlite evidence, and this Markdown artifact were created.

## Final Evidence

Primary raw evidence:

- `json/run-live-final.json`
- `json/fixture-rerun.json`
- `json/ordinary-waybill-print-rerun.html.json`
- `json/return-autoprint-capture-continuation-after-fix.json`

Fixture:

- FF admin: `ff-admin-after-fix-rerun-1786668071455@example.com`
- Seller account: `seller-after-fix-rerun-1786668071455@example.com`
- Seller: `QA Seller after-fix-rerun-1786668071455`
- Warehouse/location: `QA WH after-fix-rerun-1786668071455`, location `A-01`
- Ordinary product: `sku-ordinary-after-fix-rerun-1786668071455`, WB barcode `wb-ordinary-after-fix-rerun-1786668071455`
- Return product: `sku-return-after-fix-rerun-1786668071455`, WB barcode `wb-return-after-fix-rerun-1786668071455`
- Ordinary inbound: `64f1a8db-55f0-4659-8ba4-e97846c1b385`
- Return inbound: `f50120ea-91ee-4984-b719-a52812172d2a`

## Live Route And Click Path

Routes opened in the real browser:

- `/`
- `/app/ff/dashboard`
- `/app/ff/reception`
- `/seller/`
- `/seller/documents`
- `/seller/inbound/64f1a8db-55f0-4659-8ba4-e97846c1b385`

Ordinary inbound path:

- Opened registration UI and created FF admin.
- Created seller account, warehouse/location, ordinary product, ordinary submitted inbound expected `5`, and return submitted inbound on a clean sqlite backend.
- Fresh-loaded FF shell, clicked sidebar `Приёмка`, opened ordinary inbound from `/app/ff/reception`.
- Verified ordinary inbound type `Поставка` and verified return autoprint switch was not visible.
- Edited dimensions to `210×110×60 мм`; UI read back `1.39 л`.
- Scanned SKU `sku-ordinary-after-fix-rerun-1786668071455`; fact became `1`.
- Manually corrected fact to `3`; UI read back `Недостача 2`.
- Clicked `Завершить приёмку`, saw discrepancy dialog with `Недостача 2`, then confirmed.

Critical stale-modal check immediately after confirm:

- `modalCountImmediately`: `0`
- `staleQuestionCount`: `0`
- `staleButtonTextPresent`: `false`
- Status: `В сортировке`
- Fact readback: `Принято: 3 из 5`
- Line readback: `Недостача 2`

This closes the previous product blocker: after successful completion, the discrepancy dialog disappears and no stale confirmation controls remain over the already completed document.

Print check:

- Clicked `Печать накладной` and captured print HTML.
- HTML contains SKU, seller, `Заявлено 5`, `Факт 3`, `Недостача 2`.
- HTML does not contain request UUID, warehouse UUID, raw `status` / `sorting`, or FBS/WB order noise.

Return inbound path:

- Fresh FF login on the same clean backend/sqlite.
- Clicked sidebar `Приёмка`, opened return inbound.
- Verified visible type `Возврат`.
- Verified autoprint switch is visible only on return path.
- Enabled `Печатать ШК при скане`.
- Scanned WB barcode `wb-return-after-fix-rerun-1786668071455`.
- Captured autoprint payload containing product name and WB barcode.
- Fact read back as `Принято: 1 из 1`.

Seller fact-card path:

- Opened `/seller/documents`, then the completed ordinary inbound fact-card.
- Verified read-only state: no draft form, add-products button, submit-to-warehouse button, save-draft button, or line delete control.
- Verified compact human readback: `Заявлено 5 · принято 3`, `Есть расхождения`, `Недостача 2`, `Короба: план 1 · факт 0`.
- Verified no request UUID, warehouse UUID, raw technical status, or FBS/WB order noise inside the fact-card content.

## Screenshots

Key screenshots:

- `screenshots/22-ff-reception-queue-rerun.png`
- `screenshots/23-ordinary-open-rerun.png`
- `screenshots/24-ordinary-dimensions-saved-rerun.png`
- `screenshots/25-ordinary-after-scan-rerun.png`
- `screenshots/26-ordinary-manual-discrepancy-rerun.png`
- `screenshots/27-ordinary-discrepancy-dialog-rerun.png`
- `screenshots/28-ordinary-completed-after-confirm-rerun.png`
- `screenshots/33-return-queue-continuation.png`
- `screenshots/34-return-open-continuation.png`
- `screenshots/35-return-after-autoprint-continuation.png`
- `screenshots/36-seller-documents-continuation.png`
- `screenshots/37-seller-fact-card-continuation.png`

I visually inspected the key screenshots. The after-confirm screenshot shows the document in `В сортировке` with no discrepancy dialog/stale controls. Return and seller fact-card screenshots show no black strip or clipped critical controls.

## Metrics

All measured states used viewport `1280x720`. For every captured state, `documentScrollWidth=1280`, `bodyScrollWidth=1280`, and `pageOverflow=false`.

Measured states:

- Login and FF registered shell
- FF reception queue
- Ordinary inbound open, dimensions saved, after scan, manual discrepancy, discrepancy dialog, after confirm
- Return queue, return open, return after autoprint
- Seller documents, seller fact-card

No page-level horizontal overflow was detected. No black strip was visible in checked screenshots.

## Blockers

Final blockers: none.

Harness notes, not final product blockers:

- First attempt used ports `18220/5220`; the FF page had loaded before fixture creation and showed a stale empty queue. API readback had both inbound rows, so this was rerun with a fresh FF shell load.
- During the second attempt, after ordinary print capture, closing the FF dialog timed out. The core stale-modal check and print HTML had already passed; return and seller checks were continued in a fresh browser on the same clean `18221/5221` backend/sqlite and passed.

## Product Judgement

The previous stale-modal blocker is closed in live browser evidence. After confirming discrepancy, the worker lands on a completed `В сортировке` document with clear fact/discrepancy readback and no stale modal text or controls.

Every checked visible control/field in the scoped flows served warehouse or seller work: receiving, dimensions, fact correction, discrepancy confirmation, waybill print, return autoprint, and seller read-only fact-card.
