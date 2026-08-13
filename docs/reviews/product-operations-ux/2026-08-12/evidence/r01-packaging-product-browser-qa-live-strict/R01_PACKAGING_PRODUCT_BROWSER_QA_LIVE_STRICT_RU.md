# R01/F07 Product Browser QA Live Strict: packaging

Дата: 2026-08-14, Europe/Moscow.

Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Роль проверки: `STRICT LIVE Product Browser QA Agent`, product owner + WMS/warehouse/logistics/marketplace reviewer.

Verdict: `PRODUCT_REWORK_REQUIRED`.

Это не release-ready verdict. Код backend/frontend не редактировался. Staging,
production, Railway и secret panels не трогались. Создан только этот QA artifact.

## Browser / Runtime

browser_used: `yes`.

Browser surface: Codex In-app Browser through Browser API, real local UI tabs.

Viewport: `1280x720`, set through Browser viewport capability.

Local URLs / ports:

- Frontend: `http://127.0.0.1:55147`
- API: `http://127.0.0.1:18147`
- API health: `{"status":"ok"}`
- DB: temporary local SQLite `/private/tmp/wms-r01-packaging-live-strict-18147.db`

Role used in UI: FF admin / warehouse packaging operator:
`r01-live-admin-1786657289906@example.com`.

API was used only to seed local fixture data and create helper tasks in the local
runtime. Product verdict is based on live browser clicks, typing, scans, routes,
DOM read-back and screenshots.

## Read Sources

- `AGENTS.md`
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/r01-packaging-ba-ux-rework-strict/R01_PACKAGING_BA_UX_REWORK_STRICT_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/r01-packaging-product-review-live-strict/R01_PACKAGING_PRODUCT_REVIEW_LIVE_STRICT_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/r01-packaging-code-review-repeat-strict/R01_PACKAGING_CODE_REVIEW_REPEAT_STRICT_RU.md`
- Current UI in live browser on `/app/ff/packaging`, `/app/ff/packaging/pending-marking`, `/app/ff/mp-shipments`.

## Fixture

Local warehouse/cells:

- Warehouse: `R01 WH 1786657289906`
- Mixed seller cell: `A1-R01-9906`
- Cancel cell: `CANCEL-R01-9906`
- MP cell: `MP-R01-9906`

Products / sellers:

- Seller A: `R01 Seller A 1786657289906`, SKU `R01-A-1786657289906`, qty 4 in `A1-R01-9906`
- Seller B: `R01 Seller B 1786657289906`, SKU `R01-B-1786657289906`, qty 2 in `A1-R01-9906`
- Pool0 marking seller: `R01 Seller KM 1786657289906`, SKU `R01-KM-1786657289906`, requires ЧЗ, no codes in pool
- Cancel task product: `R01-CANCEL-1786657289906`
- MP/F17 product: `R01-MP-1786657289906`

## Routes / Actions

Live browser routes:

- `/` - typed FF admin email/password and clicked `Войти`.
- `/app/ff/packaging` - opened queue, create dialog, status tabs and search.
- `/app/ff/packaging/1cd4c514-687d-4a11-8a15-bb71d3795588` - one-seller task created through UI.
- `/app/ff/packaging/00c29934-56a6-4ba7-88c6-1fa449e95a4a` - complete flow fixture task.
- `/app/ff/packaging/pending-marking` - pool0 marking handoff.
- `/app/ff/mp-shipments` - MP/FBO shipment and `Упаковка/ЧЗ` tab.

Live clicks/scans:

- Clicked `Создать задание`.
- Selected warehouse `R01 WH 1786657289906` and cell `A1-R01-9906`.
- Selected two rows from different sellers.
- Unselected Seller B and clicked `Создать` for Seller A only.
- Scanned valid `R01-A-1786657289906`.
- Scanned unknown `R01-UNKNOWN-CODE`.
- Scanned `R01-A-1786657289906` to remaining `0`, then scanned once more for overage.
- Typed manual `+5` and clicked `+N`.
- Typed manual `+2` and clicked `+N`.
- Clicked `Отменить последнее`; JS `confirm` appeared for manual `+2`.
- Opened a fresh task, scanned `R01-B-1786657289906` twice, double-clicked `Завершить упаковку`.
- Clicked `Выполненные`, searched `№000003`.
- Clicked `Отменённые`, searched `№000004`, opened cancelled detail.
- Opened pending marking and clicked `Открыть задание`.
- Opened MP shipment row, clicked `Упаковка/ЧЗ`, clicked `Печать/финал`.

## Screenshots / Evidence

Screenshots were captured during the live Browser run under `/private/tmp`. They
are listed here as evidence references but are not additional repo artifacts:

- `/private/tmp/r01-01-packaging-route-1280.png`
- `/private/tmp/r01-02-create-dialog-unchecked-1280.png`
- `/private/tmp/r01-03-create-dialog-mixed-block-1280.png`
- `/private/tmp/r01-05-task-panel-created-1280.png`
- `/private/tmp/r01-06-valid-scan-plus-one-1280.png`
- `/private/tmp/r01-07-unknown-scan-no-mutation-1280.png`
- `/private/tmp/r01-08-overage-scan-no-mutation-1280.png`
- `/private/tmp/r01-13-exact-manual-plus-two-1280.png`
- `/private/tmp/r01-17-after-double-complete-1280.png`
- `/private/tmp/r01-19b-done-tab-explicit-search-completed-1280.png`
- `/private/tmp/r01-20-cancelled-tab-search-1280.png`
- `/private/tmp/r01-21-cancelled-detail-opened-1280.png`
- `/private/tmp/r01-22-pending-marking-pool0-1280.png`
- `/private/tmp/r01-23-pending-task-link-detail-1280.png`
- `/private/tmp/r01-25-mp-packaging-tab-scanner-panel-1280.png`
- `/private/tmp/r01-26-mp-final-print-tab-1280.png`

JSON evidence snapshot: `/private/tmp/r01-packaging-live-evidence.json`.

## Passed Checks

Queue on `/app/ff/packaging` now shows warehouse-operational columns:
`Номер`, `Статус`, `Селлер`, `Склад / ячейка`, `Товар`, `Прогресс`, `Источник`.
The open MP task showed seller, human `Сортировка`, product, `0/2`, source
`Отгрузка МП`.

Create dialog for `A1-R01-9906` started with both rows unchecked:
`checkedCount = 0`, Create disabled. Each row visibly carried seller and ТЗ:
Seller A row had `Селлер: R01 Seller A...`, Seller B row had
`Селлер: R01 Seller B...`.

Mixed-seller selection was blocked. After selecting both Seller A and Seller B,
Create stayed disabled and the exact text was visible:
`Нельзя создать одно задание для разных селлеров. Выберите товары одного селлера.`

One-seller create from Seller A succeeded through the UI. Created task `№000002`
opened as `/app/ff/packaging/1cd4c514-687d-4a11-8a15-bb71d3795588`.
The task panel showed seller, warehouse/cell, task progress, product identity,
ТЗ and scanner field. Initial scanner focus read-back was
`ff-packaging-scanner-input`.

Valid scan worked as a unit action. After scanning `R01-A-1786657289906`, progress
changed from `Готово 0 / Осталось 4` to `Готово 1 / Осталось 3`, line text changed
to `Готово 1 / Осталось 3 / Всего 4`, and feedback showed
`+1 упаковано: R01 Pack A 1786657289906`.

Unknown scan did not mutate progress. After `R01-UNKNOWN-CODE`, progress remained
`Готово 1 / Осталось 3`.

Overage scan did not mutate progress. After the task reached `Готово 4 / Осталось 0`,
one more scan kept `Готово 4 / Осталось 0`.

Manual overage is bounded. With only one unit remaining, manual `+5` did not mutate
progress and showed inline human text: `По этому товару уже упаковано всё количество`.

Manual `+2` can mutate when bounded. With two units remaining, manual `+2` moved the
task to `Готово 4 / Осталось 0`, feedback showed
`Добавлено вручную: 2 шт · R01 Pack A 1786657289906`, and history showed
`+2 вручную`.

Complete is blocked until remaining is zero. On task `№000003`, before scans
complete was disabled at `Готово 0 / Осталось 2`; after one scan it stayed disabled
at `Готово 1 / Осталось 1`; after the second scan it became enabled at
`Готово 2 / Осталось 0`.

Double-click complete was idempotent in browser. After double-clicking
`Завершить упаковку`, task `№000003` showed `Выполнено`, history had one
`Задание выполнено` event and two scan events.

Completed and cancelled tasks are searchable/reloadable:

- `Выполненные` + search `№000003` showed the completed row:
  `№000003 / Выполнено / R01 Seller B... / 2/2 / Ручное`.
- `Отменённые` + search `№000004` showed the cancelled row:
  `№000004 / Отменено / R01 Seller A... / 0/1 / Ручное`.
- Opening `№000004` showed read-only cancelled detail and history event
  `Задание отменено`.

Pending marking pool0 passed the required handoff. `/app/ff/packaging/pending-marking`
showed one row with `Нет КМ`, seller owner `R01 Seller KM 1786657289906`,
next step `Запросите КМ у селлера`, disabled row print and disabled bulk print.
Clicking `Открыть задание` opened exact task `№000005`.

Raw `__SORTING__` was not visible in queue, pending marking, task detail or MP
shipment packaging. The UI showed human `Сортировка`.

MP/F07 packaging connection passed. On `/app/ff/mp-shipments`, opening shipment
`№000001` and clicking `Упаковка/ЧЗ` showed the same scanner-first packaging task
surface with seller, `R01 WH... / Сортировка`, progress, scanner input, product
identity and ТЗ.

F17 print connection is present where applicable. In `Печать/финал`, button
`Печать листа отгрузки` was present and enabled, while final completion remained
blocked until packaging and box distribution.

## Product Blockers

### P1. Raw backend error codes are shown to the warehouse operator

Unknown scan displays `unknown_barcode` as the main red error. Overage scan displays
`line_already_packed` as the main red error.

This fails the strict product requirement that unknown/overage errors be human and
warehouse-actionable. The operator should see a message like "ШК не найден в задании"
or "По этому товару всё уже упаковано", not raw backend codes.

Evidence:

- valid/unknown/overage flow in Browser
- `/private/tmp/r01-07-unknown-scan-no-mutation-1280.png`
- `/private/tmp/r01-08-overage-scan-no-mutation-1280.png`
- DOM read-back: `error = "unknown_barcode"` and `error = "line_already_packed"`

### P1. Body-level horizontal overflow remains at 1280 px

Several required 1280px surfaces still report `documentElement.scrollWidth = 1290`
with `clientWidth = 1280`.

Observed failing surfaces:

- initial `/app/ff/packaging` queue: `scrollWidth 1290`, `clientWidth 1280`
- create dialog: `scrollWidth 1290`, `clientWidth 1280`
- done tab explicit search: `scrollWidth 1290`, `clientWidth 1280`
- cancelled/done history list surfaces also showed `scrollOk = false`

This fails the explicit requirement: no horizontal overflow at 1280px.

### P2. Create summary omits seller count

The approved R01 spec required summary:
`Выбрано N SKU / M шт / K seller`.

Live UI shows only:

- `Выбрано 0 строк / 0 шт.`
- `Выбрано 1 строк / 4 шт.`
- mixed-seller state replaces summary with the block message

The block itself is correct, but the normal summary lacks seller count. In a
warehouse cell with multiple sellers, seller count is part of the safety read-back.

### P2. Create dialog is visually overloaded at 1280px

The create dialog is functionally improved, but at 1280x720 the product/TЗ text
wraps into very tall rows. In the one-seller screenshot the user is visually parked
near the bottom of the dialog, with the selected Seller B row dominating the screen.
This is not a full process blocker by itself, but it still violates the "no UI
overload" bar for a fast packing desk.

Evidence:

- `/private/tmp/r01-02-create-dialog-unchecked-1280.png`
- `/private/tmp/r01-04-create-one-seller-before-submit-1280.png`

### P2. Manual +2 undo confirmation appeared, but reversal could not be fully accepted in this Browser pass

After manual `+2`, clicking `Отменить последнее` opened a browser-level JavaScript
`confirm`. The active confirm blocked DOM/screenshot access, which proves the
confirmation exists. However, this Browser backend repeatedly failed to accept or
dismiss it:

- `tab.getJsDialog()` returned `type = "confirm"`.
- `accept()` and `dismiss()` returned `No dialog is showing`.
- while blocked, any DOM/screenshot call returned: active confirm JavaScript dialog.

Therefore I cannot honestly mark the manual `+2` undo reversal as browser-approved
in this run. Because other product blockers already require rework, this does not
change the final verdict, but the next QA pass must repeat this exact undo step in
a controllable browser and prove the reversal read-back after accepting confirmation.

### P2. Scanner focus after success/error needs correction or repeat proof

Initial task open focused `ff-packaging-scanner-input`. After valid scan and after
unknown/overage, DOM read-back for active test id was empty, although the visual
surface still showed the scanner field. R01 requires focus to stay in the scanner
input after success and errors. This needs either a UI fix or a repeat proof with a
browser driver that can reliably read active focus after the scan click.

## Final Product Verdict

`PRODUCT_REWORK_REQUIRED`.

R01/F07 is substantially closer to the approved product shape: seller-safe create,
mixed-seller blocking, scanner-first task panel, completion gating, history, pool0
handoff and MP/F17 connection are all visible in live browser.

It still cannot pass strict Product Browser QA because operator-facing error text is
raw technical code and required 1280px surfaces still have body-level horizontal
overflow. The missing seller count in create summary and unresolved manual `+2` undo
acceptance proof should be fixed or explicitly re-tested before another browser QA
attempt.
