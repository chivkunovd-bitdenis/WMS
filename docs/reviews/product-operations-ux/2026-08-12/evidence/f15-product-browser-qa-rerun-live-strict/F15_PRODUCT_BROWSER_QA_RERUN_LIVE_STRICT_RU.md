# F15 Product Browser QA Rerun Live Strict

Вердикт: PRODUCT_BROWSER_APPROVED

Дата проверки: 2026-08-14, live browser rerun after P0 fix. Release ready не заявляется.

## Контекст

- browser_used: yes
- Browser: Codex In-app Browser, управляемая live-вкладка через Browser plugin. `visibility.set(true)` в этом subagent-потоке недоступен, но реальная вкладка была открыта, UI был прокликан, screenshots сняты с live tab.
- Frontend: `http://127.0.0.1:5216`
- Backend: `http://127.0.0.1:18156`
- DB: `/tmp/wms_f15_rerun_live_strict_20260814_01.sqlite`
- Evidence JSON: `/tmp/wms-f15-product-browser-qa-rerun-live-strict/f15-rerun-live-result.json`
- Git root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
- HEAD на момент проверки: `97ab6bfbe6e7b34d987ee55472749b06a87da92f`
- Роли:
  - FF admin: `f15-rerun-ff-1786660030892@example.com`
  - Seller: `f15-rerun-seller-1786660030892@example.com`
- Данные:
  - SKU: `F15-RERUN-1786660030892`
  - Product: `e02c9d36-c08c-4aac-9486-3c6c5fa64a9b`
  - Warehouse: `381c99d6-6527-4dd6-aab7-05518ab32b27`
  - Storage location barcode: `LOC-5638A6D1EEB0`
  - WB warehouse: `900001`
  - MP request: `49d4a5a0-b31d-436f-ab22-caefe2c15548`

Код, staging, production, Railway, secrets, deploy и merge не трогались.

## Live Browser Routes And Clicks

Открывались реальные UI routes:

- `http://127.0.0.1:5216/` - FF registration.
- `http://127.0.0.1:5216/seller/` - seller login/documents/inbound/MP dialog.
- `http://127.0.0.1:5216/app/ff/mp-shipments?open_mp=49d4a5a0-b31d-436f-ab22-caefe2c15548` - FF submitted/confirmed start.
- `http://127.0.0.1:5216/app/ff/mp-shipments` - reload/read-back recovery by clicking the document row.

Ключевые live clicks:

- FF: registration, submitted MP open, confirm plan, boxes tab, import dialog open/cancel, batch create 2 boxes, add-products dialogs for both boxes, scan location barcode, manual fill `2 + 2`, packaging tab, manual pack `4`, complete packaging, final tab, ship, shipped boxes tab.
- Seller: login, documents, draft delete, cancel, reload/read-back, delete again, confirm, reload/read-back, open submitted inbound, open submitted MP readonly dialog.

## Screenshots

- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/01-ff-registration-live-ui.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/02-seller-documents-before-delete.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/03-seller-delete-confirm-dialog.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/04-seller-delete-cancel-keeps-draft-after-reload.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/05-seller-delete-confirm-removes-draft-after-reload.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/06-seller-submitted-inbound-detail.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/07-seller-submitted-mp-readonly.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/08-ff-submitted-no-delete.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/09-ff-confirmed-no-delete.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/10-ff-confirmed-import-dialog.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/11-ff-confirmed-batch-created.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/12-ff-collecting-after-blocked-remove-readback.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/13-ff-packaging-complete-after-blocked-remove.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/14-ff-shipped-final.png`
- `/tmp/wms-f15-product-browser-qa-rerun-live-strict/15-ff-shipped-boxes-print-only-after-reload.png`

## Read-back Evidence

### Seller draft delete

Pass.

- Confirm dialog appeared: `seller-delete-draft-confirm-dialog`.
- Cancel preserved draft row: row count stayed `1`; API read-back status stayed `draft`.
- Reload after cancel still showed the draft row.
- Confirm deleted the draft: row count became `0`; API list no longer contained draft `d3a83f22-96b5-4dc0-b0e5-e0517f2f5675`.
- Success message: `seller-documents-delete-ok`.

### Seller non-draft documents

Pass.

- Submitted inbound row delete count: `0`.
- Submitted inbound detail line delete count: `0`.
- Direct submitted inbound document delete: `409 not_draft`.
- Direct submitted inbound line delete: `409 not_draft`.
- Read-back preserved status `submitted` and line `d0efd19f-0e21-47b8-b9af-1731d8ac56ea`.
- Submitted MP row delete count: `0`.
- Submitted MP dialog used readonly table count `1`; `seller-mp-line-delete` count `0`.
- Direct submitted MP document delete: `409 not_draft`.
- Direct submitted MP line delete: `409 not_draft`.
- Read-back preserved status `submitted` and line `45b0d811-e6fd-4b4e-b84a-42a4de797c3e`.

### FF submitted and confirmed

Pass.

- Submitted MP UI showed `Запланировано`; `ff-supplies-line-delete-*` count `0`.
- Direct submitted document delete: `409 not_draft`.
- Direct submitted line delete: `409 not_draft`.
- FF confirmed through UI; confirmed read-back status `confirmed`.
- Confirmed line delete count stayed `0`.
- Direct confirmed line delete: `409 not_draft`.

### Confirmed/collecting box workflow

Pass.

- Confirmed box operational controls were visible:
  - scan field `1`
  - scan button `1`
  - batch count `1`
  - batch create `1`
  - import boxes `1`
- Confirmed destructive controls were absent:
  - box menu copy `0`
  - box menu delete `0`
  - box line remove `0`
- Import dialog opened and closed.
- Batch create produced 2 boxes.
- Both boxes were filled through live UI add-products flow after scanning `LOC-5638A6D1EEB0`; distributed summary reached `4`, remaining `0`.
- Packaging still worked after the blocked direct remove: manual pack `4`, complete packaging, packed summary `4/4`.

### Collecting direct box-line remove

Pass.

- Status before probe: `collecting`.
- Visible collecting remove controls: `0`.
- Visible collecting box menu controls: `0`.
- Direct request:
  - `POST /operations/marketplace-unload-requests/49d4a5a0-b31d-436f-ab22-caefe2c15548/boxes/08e18d7b-b532-4233-b93d-005573c5cf1c/lines/33fd6711-0dfb-411a-9edf-f9ad3ed84c06/remove`
  - result: `409 not_draft`
- Line read-back preserved:
  - before: `33fd6711-0dfb-411a-9edf-f9ad3ed84c06`, qty `2`
  - after: `33fd6711-0dfb-411a-9edf-f9ad3ed84c06`, qty `2`
- Stock read-back preserved:
  - before quantity `8`, unpacked `8`, available `8`, reserved `0`
  - after quantity `8`, unpacked `8`, available `8`, reserved `0`
- Direct non-empty box delete: `409 box_not_empty`.
- Direct non-empty box copy: `422 plan_limit_exceeded`, no durable over-plan mutation.

### Shipped state

Pass.

- UI reached shipped: read-back status `shipped`.
- Final print sheet button was enabled before ship.
- Shipped box print stayed enabled.
- Shipped mutating controls hidden:
  - scan field `0`
  - scan button `0`
  - batch count `0`
  - batch create `0`
  - import boxes `0`
- Shipped destructive controls hidden:
  - box menu copy `0`
  - box menu delete `0`
  - box line remove `0`
  - box delete icons `0`
- Direct shipped line delete: `409 not_draft`.
- Direct shipped box copy: `409 not_editable`.
- Direct shipped box delete: `409 not_editable`.
- Direct shipped box-line remove: `409 not_draft`.
- Read-back after direct probes preserved status `shipped`, box count `2`, line ids:
  - `33fd6711-0dfb-411a-9edf-f9ad3ed84c06`
  - `609b57f6-b00c-4805-90a1-144e56217b16`
- UI noise scan: no `undefined`, `null`, `invalid_qty`, raw error codes, JSON braces, or `data-testid` visible in shipped dialog text.
- Browser console error count: `0`.

## Product Findings

No P0/P1 product findings in this rerun.

The previous P0 is closed by live evidence: collecting direct box-line remove is now blocked with `409 not_draft`, and durable line/stock read-back is preserved. Seller draft delete now has explicit confirmation; cancel preserves the draft and confirm deletes it.

## Verdict

PRODUCT_BROWSER_APPROVED

This is a Product Browser QA verdict only. It is not release ready, not staging approval, not production proof, and not permission to deploy.
