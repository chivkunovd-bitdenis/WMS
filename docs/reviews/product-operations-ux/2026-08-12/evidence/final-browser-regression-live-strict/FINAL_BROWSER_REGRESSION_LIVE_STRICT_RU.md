# FINAL_BROWSER_REGRESSION_LIVE_STRICT_RU

Дата прогона: 2026-08-14 MSK.

Verdict: `FINAL_BROWSER_REGRESSION_FAILED`.

Это был строгий live browser regression после per-feature gates. Я не засчитывал старую матрицу и не засчитывал Playwright-run из `ITERATION_FINAL_INTEGRATION_REVIEW_RU.md` как final product proof, потому что текущий контракт требует новый живой browser judgement.

## Runtime

| Поле | Значение |
|---|---|
| repo | `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812` |
| branch | `iteration/wms-product-ux-features-20260812` |
| HEAD at run | `d59959de70a8b9d447f200bdb703023c35b7b449` |
| browser_used | `yes` |
| browser | Chromium `headless=false`, live local UI |
| frontend | `http://127.0.0.1:5188/` |
| backend | `http://127.0.0.1:18280/` |
| viewport | `1280x720` |
| DB | isolated SQLite `/tmp/wms-final-browser-regression-live-strict-20260814.sqlite` |
| code/docs edited before judgement | no |
| production/staging/Railway/secrets/deploy | not touched |
| commit/push | not done |

Important technical note: browser print helpers open native print from iframes. For print checks I used the existing in-app capture flag `__WMS_CAPTURE_PRINT_HTML__` and disabled only `window.print` in the browser context, so the visible UI button was still clicked and the generated print HTML was read back without opening a native print dialog.

## Test Entities

| Entity | ID / value |
|---|---|
| FF admin | `final-admin-1786663837545@example.com` |
| Seller | `final-seller-1786663837545@example.com` |
| seller_id | `f6a6e071-8b41-4df7-8306-43626eae72e1` |
| warehouse_id | `ffc9f4b8-70b5-4078-a4c9-bdd798385ea2` |
| location_id | `7a0d39de-6d3b-4aa9-b6dd-66fee9db5546` |
| product_id | `66f39478-9d5a-4238-b9c4-a3c7ddf5bdd5` |
| product_sku | `SKU-FINAL-1786663837545` |
| ordinary inbound | `ceb52ef0-729b-445c-9368-a920d726310d` |
| return inbound | `47e0e0f2-74a0-492d-bf13-d29c8c06dd40` |
| packaging_task_id | `54b86711-2133-41f7-8f2e-90af7425ed57` |
| marketplace_unload_id | `05a18e54-2369-4c89-9c38-74028f3067a2` |
| delete draft | `a56fc405-9286-4162-aac3-604d79975720` |
| delete submitted | `a91023e9-d861-49e9-b1d2-483bf4fe39c5` |

## Overall Result

| Scenario group | Scope | Verdict |
|---|---|---|
| Seller inbound / FF reception / dimensions / print / returns / autoprint / fact-card | F05, F06, F18, F19 plus connected reception UX | `PASS` |
| Catalog / stocks / FBS / FBO / FF catalog cleanup | F08-F11, F16, F22, F23 | `FAIL` |
| Staff roles / direct routes | R02, F12, F14 | `PASS` |
| Packaging / marking / MP print | R01, F07, F17 | `PASS` |
| Delete only draft | F15 | `PASS` |

Final release decision remains failed because one product blocker in seller catalog/stocks is release-blocking.

## PASS Evidence

### Inbound / Reception / Seller Fact-Card

Route/click path:

1. FF login at `/`.
2. Opened `/app/ff/reception` through sidebar `Приёмка`.
3. Opened inbound `ceb52ef0-729b-445c-9368-a920d726310d`.
4. Edited dimensions from the receiving row to `200x100x50 мм`, read back `1.00 л`.
5. Scanned `SKU-FINAL-1786663837545`.
6. Manually changed accepted quantity to `2`.
7. Completed receiving through discrepancy dialog.
8. Clicked `Печать накладной`; captured generated print HTML with fact and discrepancy.
9. Opened return inbound `47e0e0f2-74a0-492d-bf13-d29c8c06dd40`.
10. Verified `Возврат` and return autoprint switch, enabled it, scanned WB barcode, captured print HTML.
11. Seller login at `/seller/`.
12. Opened seller documents, then fact-card for the completed inbound.

Observed result:

- Ordinary inbound stayed in one reception workflow; no `Упаковка` tab appeared inside reception.
- FF saw human status `В сортировке`, accepted `2 из 3`, discrepancy `Недостача 1`, and boxes `0 из 1`.
- Seller fact-card was read-only and showed `Есть расхождения` / `Недостача 1`.
- No raw UUID/status/error-code noise was visible on the seller fact-card.
- 1280px check for seller fact-card had no page-level horizontal overflow.

Temporary visual evidence:

- `/tmp/wms-final-browser-regression-live-strict/screens/01-inbound-ordinary-completed.png`
- `/tmp/wms-final-browser-regression-live-strict/screens/02-seller-fact-card-readback.png`

### Staff Roles / Direct Routes

Checked roles:

- reception staff `5607c4de-af95-4017-82b9-8828576ab372`;
- shipments/packaging staff `95ffba5b-3b91-4631-a30a-822f2871284d`;
- catalog/inventory staff `eb27e7ae-fa9e-4c4d-a7e6-46f550728d14`;
- settings staff `f47e6cc7-f95d-456a-8cbf-f2eabca60b29`.

Observed result:

- Reception staff opened `/app/ff/reception`; `/app/ff/settings`, `/app/ff/fbs`, `/app/ff/packaging`, `/app/ff/inventory`, `/app/ff/sellers`, and `/seller/products` were denied in FF shell with human access text.
- Shipments/packaging staff saw MP shipments, FBS, and packaging; stock-sync direct route was denied.
- Catalog/inventory staff saw `Каталог и ячейки` and `Инвентаризация`; direct `/app/ff/inventory` matched the menu.
- Settings staff saw compact staff settings without payroll-only columns.

Temporary visual evidence:

- `/tmp/wms-final-browser-regression-live-strict/screens/04-staff-settings-compact.png`

### Packaging / MP Print

Route/click path:

1. FF admin opened `/app/ff/packaging`.
2. Created packaging task from `WH-FINAL / Сортировка`.
3. Selected the product and quantity `2`.
4. Scanned one valid SKU.
5. Scanned invalid SKU `SKU-FINAL-1786663837545-UNKNOWN`.
6. Opened MP shipment final tab and clicked `Печать листа отгрузки`.

Observed result:

- Packaging task used human number, not service UUID.
- Scanner success read back `Готово 1 / Осталось 1 / Всего 2`.
- Invalid scan showed human error `ШК не найден в этом задании`, not raw `unknown_barcode`.
- MP/FBO final print generated shipment sheet with seller/date/type/quantity/fact content and no FBS order QR.

Temporary visual evidence:

- `/tmp/wms-final-browser-regression-live-strict/screens/05-packaging-task-scanner.png`
- `/tmp/wms-final-browser-regression-live-strict/screens/06-mp-final-print-sheet.png`

### Delete Only Draft

Route/click path:

1. Seller opened `/seller/documents`.
2. Draft inbound `a56fc405-9286-4162-aac3-604d79975720` had delete action.
3. Submitted inbound `a91023e9-d861-49e9-b1d2-483bf4fe39c5` had no delete action.
4. Cancelled delete confirmation once, then confirmed.
5. Read-back: draft disappeared; submitted document stayed visible.

Temporary visual evidence:

- `/tmp/wms-final-browser-regression-live-strict/screens/07-seller-delete-only-draft.png`

## FAIL Blocker

### P0: Seller Catalog / Stocks Screen Still Fails Product Regression

Affected scope: F08-F11, F16, F22, F23.

Route:

```text
http://127.0.0.1:5188/seller/products
```

Live observed header:

```text
Товар | WB / ШК | Остаток | FBS-пул | Публикация WB | ТЗ / ЧЗ | Действия
```

Why this blocks release:

- The strict acceptance expected human marketplace identifier wording `Артикул WB`; live seller catalog shows collapsed `WB / ШК`.
- At 1280px the page itself does not overflow, but the seller catalog table is too compressed: the `Действия` header is visibly clipped to `Действе`, product identifiers are ellipsized, and the action column is reduced to a narrow `ТЗ` link.
- The stock values are visually stacked as `10 / 12 / 12` without enough context in the main row. For a seller deciding what can go to FBS vs FBO, this is too report-like and ambiguous.
- This is not just a test wording mismatch. The live screenshot shows the seller catalog still failing the product-owner criterion: a warehouse/seller operator should not have to decode compressed technical columns to understand WB article, stock, FBS pool, publication state, and next action.

Additional diagnostic read-back:

- No page-level horizontal overflow at 1280: `document.scrollWidth=1280`, `body.scrollWidth=1280`.
- Table width equals container width: `990px`.
- First row height: about `91.5px`.
- Creating an FBS direction through the drawer did work: `FBS diagnostic`, `3 шт`, `Свободный FBO 9 шт`, no page overflow.
- This means the blocker is product/visual clarity of the seller catalog main row, not backend inability to create stock directions.

Temporary visual evidence:

- `/tmp/wms-final-browser-regression-live-strict/screens/03-FAIL-catalog-stocks-fbs-fbo-ff-catalog-cleanup.png`
- `/tmp/wms-final-browser-regression-live-strict/screens/08-catalog-table-diagnostic.png`
- `/tmp/wms-final-browser-regression-live-strict/screens/09-catalog-after-direction-diagnostic.png`

## Product Verdict

`FINAL_BROWSER_REGRESSION_FAILED`.

The iteration must not be called stage-ready or release-ready. The exact returned area is seller catalog/stocks UI, especially the `/seller/products` main table. After rework, the final live browser regression must be rerun; old per-feature passes and automated Playwright results are not enough for this final gate.
