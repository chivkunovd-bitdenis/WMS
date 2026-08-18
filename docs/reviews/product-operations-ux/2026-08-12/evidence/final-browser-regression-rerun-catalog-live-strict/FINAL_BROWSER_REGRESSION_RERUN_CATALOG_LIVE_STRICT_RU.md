# FINAL_BROWSER_REGRESSION_RERUN_CATALOG_LIVE_STRICT_RU

Дата: 2026-08-14T00:19:43.323Z.

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Verdict: `FINAL_BROWSER_GROUP_PASSED`.

Код, commit, push, staging, production, Railway и внешние кабинеты секретов не трогались. Созданы только локальные evidence-файлы в этой папке.

## Live Browser

| Поле | Значение |
| --- | --- |
| browser_used | `yes` |
| browser | `Chromium via Playwright headless=false` |
| viewport | `1280x720` |
| frontend | `http://127.0.0.1:15591` |
| backend | `http://127.0.0.1:18591` |
| emulator | `http://127.0.0.1:18592` |
| sqlite | `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/wms.sqlite` |
| result_json | `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/live-result.json` |

## Seed

```json
{
  "suffix": 1786666771333,
  "adminEmail": "catalog-rerun-admin-1786666771333@example.com",
  "sellerEmail": "catalog-rerun-seller-1786666771333@example.com",
  "sellerId": "e50e4fa9-c537-4a61-9474-8958e9b76803",
  "warehouseId": "907cc40e-3d04-449d-841d-4534f5223b54",
  "productId": "2b9220ed-1e04-4618-aca8-e680b09eb350",
  "sku": "E2E-MOCK",
  "wb_nm_id": 424242,
  "wb_chrt_id": 9914242,
  "wb_barcode": "E2E-MOCK-BARCODE",
  "wbSelfToken": {
    "res": {},
    "json": {
      "ok": true,
      "cards_received": 1,
      "cards_saved": 1,
      "products_created": 1,
      "products_updated": 0,
      "products_skipped": 0
    },
    "text": "{\"ok\":true,\"cards_received\":1,\"cards_saved\":1,\"products_created\":1,\"products_updated\":0,\"products_skipped\":0}"
  },
  "forcedWb": [
    "2b9220ed1e044618aca8e680b09eb350",
    "E2E-MOCK",
    424242,
    9914242,
    "E2E-MOCK-BARCODE"
  ],
  "inbound": {
    "inboundId": "c7fc1daa-ef98-4fa3-8755-2f9f30fa1a37",
    "locationId": "d24c92e0-1a51-42b5-968f-83ed38ddeb65",
    "boxId": "8511a685-fbf3-40ae-b50b-f917f1535d37"
  },
  "initialEmulatorStock": 20
}
```

## Routes

- `http://127.0.0.1:15591/seller/`
- `http://127.0.0.1:15591/seller/products`
- `http://127.0.0.1:18591/operations/fbs-sellers/e50e4fa9-c537-4a61-9474-8958e9b76803/stocks/sync`
- `http://127.0.0.1:18591/operations/fbs-sellers/e50e4fa9-c537-4a61-9474-8958e9b76803/stocks/sync`
- `http://127.0.0.1:15591/`
- `http://127.0.0.1:15591/app/ff/products`

## Clicks

- seller login form: fill email/password
- seller login form: Войти
- select seller product row — `{"label":"select seller product row","productId":"2b9220ed-1e04-4618-aca8-e680b09eb350"}`
- Изменить публикацию
- Включить
- bulk confirm submit
- Пул / Настроить FBS-пул — `{"label":"Пул / Настроить FBS-пул","title":"Настроить FBS-пул"}`
- create FBS direction qty 5
- open ТЗ action from ТЗ / ЧЗ
- close ТЗ dialog
- logout seller
- ff admin login form: fill email/password
- ff admin login form: Войти
- open FF catalog
- open FF distribution popover

## Screenshots

- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/01-seller-products-initial-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/02-selected-only-bulk-confirm-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/03-fbs-pool-drawer-empty-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/04-fbs-direction-created-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/05-wb-readback-confirmed-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/06-packaging-dialog-from-tz-chz-1280x720.png`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-catalog-live-strict/run-20260814-031925/07-ff-catalog-cleanup-1280x720.png`

## Mandatory Checks

- PASS: seller /seller/products opened at 1280x720 — `{"viewportWidth":1280,"viewportHeight":720,"documentScrollWidth":1280,"bodyScrollWidth":1280,"documentClientWidth":1280,"bodyClientWidth":1280,"tableScrollWidth":990,"tableClientWidth":990,"containerScrollWidth":990,"containerClientWidth":990,"rowHeight":68.6328125,"headers":["","Товар","Артикул WB","Остаток","FBS-пул","Публикация WB","ТЗ / ЧЗ"],"poolButton":{"x":896.6875,"y":474.6875,"width":44,"height":24,"right":940.6875,"bottom":498.6875,"text":"Пул"},"packagingButton":{"x":1144.1796875,"y":473.390625,"width":36,"height":24,"right":1180.1796875,"bottom":497.390625,"text":"ТЗ"},"poolButtonVisible":true,"packagingButtonVisible":true,"pageText":"\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 0 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 12FBS 0 штрезервы 0 штПулНет FBSТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\n"}`
- PASS: headers are exact compact catalog headers with Артикул WB and no WB / ШК or Действия — `["","Товар","Артикул WB","Остаток","FBS-пул","Публикация WB","ТЗ / ЧЗ"]`
- PASS: stock cell has labels В ячейках / На ФФ / Свободный FBO and no naked stock fraction — `{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 12","distribution":"FBS 0 шт\n\nрезервы 0 шт\nПул","status":"Нет FBS","fbsCell":"Нет FBS","packaging":"ТЗ есть"}`
- PASS: missing FBS starts as Нет FBS with disabled toggle and no WB zero success — `{"initialTexts":{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 12","distribution":"FBS 0 шт\n\nрезервы 0 шт\nПул","status":"Нет FBS","fbsCell":"Нет FBS","packaging":"ТЗ есть"},"initialToggleDisabled":true}`
- PASS: initial layout has rowHeight <=72 and no horizontal overflow — `{"viewportWidth":1280,"viewportHeight":720,"documentScrollWidth":1280,"bodyScrollWidth":1280,"documentClientWidth":1280,"bodyClientWidth":1280,"tableScrollWidth":990,"tableClientWidth":990,"containerScrollWidth":990,"containerClientWidth":990,"rowHeight":68.6328125,"headers":["","Товар","Артикул WB","Остаток","FBS-пул","Публикация WB","ТЗ / ЧЗ"],"poolButton":{"x":896.6875,"y":474.6875,"width":44,"height":24,"right":940.6875,"bottom":498.6875,"text":"Пул"},"packagingButton":{"x":1144.1796875,"y":473.390625,"width":36,"height":24,"right":1180.1796875,"bottom":497.390625,"text":"ТЗ"},"poolButtonVisible":true,"packagingButtonVisible":true,"pageText":"\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 0 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 12FBS 0 штрезервы 0 штПулНет FBSТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\n"}`
- PASS: pool and ТЗ action bounds are visible, no clipped action column — `{"pool":{"x":896.6875,"y":474.6875,"width":44,"height":24,"right":940.6875,"bottom":498.6875,"text":"Пул"},"packaging":{"x":1144.1796875,"y":473.390625,"width":36,"height":24,"right":1180.1796875,"bottom":497.390625,"text":"ТЗ"}}`
- PASS: initial seller catalog has no raw code/chip/noise regression — `{"sample":"\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 0 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 12FBS 0 штрезервы 0 штПулНет FBSТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\n"}`
- PASS: bulk confirm is selected-only for 1 product — `{"confirmText":"Включить публикацию FBS для 1 товаров?\n\nБудут изменены только выбранные товары.\n\nE2E-MOCK · E2E-MOCK-BRAND\n\nОтмена\nПодтвердить"}`
- PASS: bulk request body sends product_ids array with selected id, never null/all — `{"bulkBody":{"product_ids":["2b9220ed-1e04-4618-aca8-e680b09eb350"],"fbs_stock_sync_enabled":true},"response":{"updated_count":1}}`
- PASS: missing FBS sync path keeps Нет FBS, disabled toggle, no WB: 0 шт and emulator remains 20 — `{"missingPoolTexts":{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 12","distribution":"FBS 0 шт\n\nрезервы 0 шт\nПул","status":"Нет FBS","fbsCell":"Нет FBS","packaging":"ТЗ есть"},"missingPoolState":{"amount":20,"item":{"chrt_id":9914242,"product_id":"2b9220ed-1e04-4618-aca8-e680b09eb350","target":null,"confirmed":null,"status":"error","error":"unsafe_stock_unknown","timestamp":"2026-08-14T00:19:37"},"status":{"wb_warehouse_id":501991,"binding_last_sync_at":"2026-08-14T00:19:37.090390","binding_last_sync_status":"error","binding_last_error_code":"unsafe_stock_unknown","items":[{"chrt_id":9914242,"product_id":"2b9220ed-1e04-4618-aca8-e680b09eb350","target":null,"confirmed":null,"status":"error","error":"unsafe_stock_unknown","timestamp":"2026-08-14T00:19:37"}]}}}`
- PASS: pool button exposes Настроить FBS-пул and drawer starts with no FBS guidance — `{"poolTitle":"Настроить FBS-пул","drawerText":"Распределение остатка\n\nE2E-MOCK · E2E-MOCK-BRAND\n\nFBS\n0 шт\nРезервы\n0 шт\nСвободный FBO\n12 шт\nFBS-пул не выделен. Сначала добавьте направление с галкой FBS.\n\nНаправлений пока нет.\n\nНовое направление\nНазвание\nНазвание\nКоличество\nКоличество\nКомментарий\nКомментарий\nFBS-пул для публикации в WB\nДобавить\nЗакрыть"}`
- PASS: FBS/FBO split is clear in main row and drawer after FBS direction — `{"afterFbsTexts":{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 7","distribution":"FBS 5 шт\n\nрезервы 0 шт\nПул","status":"Проверяем WB","fbsCell":"Проверяем WB","packaging":"ТЗ есть"},"drawerTextAfterFbs":"Распределение остатка\n\nE2E-MOCK · E2E-MOCK-BRAND\n\nFBS\n5 шт\nРезервы\n0 шт\nСвободный FBO\n7 шт\n\nFBS WB rerun\n\nFBS-пул · 5 шт\nРедактировать\nУдалить\nНовое направление\nНазвание\nНазвание\nКоличество\nКоличество\nКомментарий\nКомментарий\nFBS-пул для публикации в WB\nДобавить\nЗакрыть","fbsDirection":{"id":"48262ea6-0280-4aca-8655-1e8518df09a3","product_id":"2b9220ed-1e04-4618-aca8-e680b09eb350","name":"FBS WB rerun","comment":null,"quantity":5,"is_fbs":true,"created_at":"2026-08-14T00:19:38","updated_at":"2026-08-14T00:19:38"}}`
- PASS: after FBS direction status is Проверяем WB before emulator readback or a real nonzero readback — `{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 7","distribution":"FBS 5 шт\n\nрезервы 0 шт\nПул","status":"Проверяем WB","fbsCell":"Проверяем WB","packaging":"ТЗ есть"}`
- PASS: WB emulator confirms nonzero readback and seller UI shows WB: 5 шт — `{"confirmedState":{"amount":5,"item":{"chrt_id":9914242,"product_id":"2b9220ed-1e04-4618-aca8-e680b09eb350","target":5,"confirmed":5,"status":"confirmed","error":null,"timestamp":"2026-08-14T00:19:39"},"status":{"wb_warehouse_id":501991,"binding_last_sync_at":"2026-08-14T00:19:39.140162","binding_last_sync_status":"confirmed","binding_last_error_code":null,"items":[{"chrt_id":9914242,"product_id":"2b9220ed-1e04-4618-aca8-e680b09eb350","target":5,"confirmed":5,"status":"confirmed","error":null,"timestamp":"2026-08-14T00:19:39"}]}},"readbackTexts":{"inStorage":"В ячейках 12","onHand":"На ФФ 12","freeFbo":"Свободный FBO 7","distribution":"FBS 5 шт\n\nрезервы 0 шт\nПул","status":"WB: 5 шт","fbsCell":"WB: 5 шт","packaging":"ТЗ есть"}}`
- PASS: packaging opens from ТЗ / ЧЗ and action column remains unclipped — `{"packagingDialogText":"ТЗ на упаковку\n\nE2E-MOCK · E2E-MOCK-BRAND\n\nНужен Честный знак при упаковке\nИнструкция для фулфилмента\nИнструкция для фулфилмента\nОтмена\nПечать\nСохранить","packagingTextValue":"QA rerun: пакет, стикер WB, проверить ЧЗ перед отгрузкой","packagingMetrics":{"viewportWidth":1280,"viewportHeight":720,"documentScrollWidth":1280,"bodyScrollWidth":1280,"documentClientWidth":1280,"bodyClientWidth":1280,"tableScrollWidth":990,"tableClientWidth":990,"containerScrollWidth":990,"containerClientWidth":990,"rowHeight":68.6328125,"headers":["","Товар","Артикул WB","Остаток","FBS-пул","Публикация WB","ТЗ / ЧЗ"],"poolButton":{"x":896.6875,"y":474.6875,"width":44,"height":24,"right":940.6875,"bottom":498.6875,"text":"Пул"},"packagingButton":{"x":1144.1796875,"y":473.390625,"width":36,"height":24,"right":1180.1796875,"bottom":497.390625,"text":"ТЗ"},"poolButtonVisible":true,"packagingButtonVisible":true,"pageText":"\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 1 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 7FBS 5 штрезервы 0 штПулWB: 5 штТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\nТЗ на упаковкуE2E-MOCK · E2E-MOCK-BRANDНужен Честный знак при упаковкеИнструкция для фулфилментаQA rerun: пакет, стикер WB, проверить ЧЗ перед отгрузкойИнструкция для фулфилментаОтменаПечатьСохранить"}}`
- PASS: final metrics: rowHeight <=72, document/body scrollWidth <= viewport, table/container widths sane — `{"viewportWidth":1280,"viewportHeight":720,"documentScrollWidth":1280,"bodyScrollWidth":1280,"documentClientWidth":1280,"bodyClientWidth":1280,"tableScrollWidth":990,"tableClientWidth":990,"containerScrollWidth":990,"containerClientWidth":990,"rowHeight":68.6328125,"headers":["","Товар","Артикул WB","Остаток","FBS-пул","Публикация WB","ТЗ / ЧЗ"],"poolButton":{"x":896.6875,"y":474.6875,"width":44,"height":24,"right":940.6875,"bottom":498.6875,"text":"Пул"},"packagingButton":{"x":1144.1796875,"y":473.390625,"width":36,"height":24,"right":1180.1796875,"bottom":497.390625,"text":"ТЗ"},"poolButtonVisible":true,"packagingButtonVisible":true,"pageText":"\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 1 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 7FBS 5 штрезервы 0 штПулWB: 5 штТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\nТЗ на упаковкуОтменаПечатьСохранить"}`
- PASS: final product judgement: no overload, raw codes, old headers, separate actions, or WB zero success — `{"sample":"Портал селлера\ncatalog-rerun-seller-1786666771333@example.com · fulfillment_seller\n0\nВыйти\nДокументы\nТовары\nЧестный знак\nНастройки\nТовары\n\nКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).\n\nСинхронизировать по API\nПубликация FBS в WB\nПубликуется: 1 из 1\n\tТовар\tАртикул WB\tОстаток\tFBS-пул\tПубликация WB\tТЗ / ЧЗ\n\n\t\n\nE2E-MOCK-BRAND\n\nSKU E2E-MOCK · E2E-MOCK · L\n\t\n\n424242\n\nШК E2E-MOCK-BARCODE\n\t\nВ ячейках 12\nНа ФФ 12\nСвободный FBO 7\n\t\n\nFBS 5 шт\n\nрезервы 0 шт\nПул\n\t\nWB: 5 шт\n\t\nТЗ есть\nЧЗ нужен\nТЗ\n\nНа странице\n\n10\n\n1–1 of 1\n\nТЗ на упаковку\nОтмена\nПечать\nСохранить"}`
- PASS: FF catalog cleanup visible: business columns and no internal stage noise — `{"ffHead":"Фото\tSKU / ШК\tАртикул WB\tНазвание\n\tСеллер\tТЗ / ЧЗ\tДоступно\n\tРаспределение\t\n","sample":"Фото\tSKU / ШК\tАртикул WB\tНазвание\n\tСеллер\tТЗ / ЧЗ\tДоступно\n\tРаспределение\t\n\n\t\n\nE2E-MOCK\n\nE2E-MOCK-BARCODE\nРазмер: L\nСостав: хлопок 95%, эластан 5%\n\t\n\n424242\n\n\t\nE2E-MOCK-BRAND\nАртикул продавца: E2E-MOCK\nРазмер: L\n\t\n\nCatalog Rerun Seller 1786666771333\n\n\t\n\nЗаполнено\n\nЧЗ нужен\nТЗ\n\t\n\n7 шт\n\n\t\n\nFBS 5 · Резервы 0\n\nFBO 7\n\t"}`
- PASS: FF distribution popover shows FBS/FBO split without internal noise — `{"popoverText":"E2E-MOCK\n\nE2E-MOCK-BRAND\n\nFBS\n\n5 шт\n\nРезервы/наборы\n\n0 шт\n\nСвободно для FBO\n\n7 шт"}`

## Metrics

```json
{
  "initialSellerCatalog": {
    "viewportWidth": 1280,
    "viewportHeight": 720,
    "documentScrollWidth": 1280,
    "bodyScrollWidth": 1280,
    "documentClientWidth": 1280,
    "bodyClientWidth": 1280,
    "tableScrollWidth": 990,
    "tableClientWidth": 990,
    "containerScrollWidth": 990,
    "containerClientWidth": 990,
    "rowHeight": 68.6328125,
    "headers": [
      "",
      "Товар",
      "Артикул WB",
      "Остаток",
      "FBS-пул",
      "Публикация WB",
      "ТЗ / ЧЗ"
    ],
    "poolButton": {
      "x": 896.6875,
      "y": 474.6875,
      "width": 44,
      "height": 24,
      "right": 940.6875,
      "bottom": 498.6875,
      "text": "Пул"
    },
    "packagingButton": {
      "x": 1144.1796875,
      "y": 473.390625,
      "width": 36,
      "height": 24,
      "right": 1180.1796875,
      "bottom": 497.390625,
      "text": "ТЗ"
    },
    "poolButtonVisible": true,
    "packagingButtonVisible": true,
    "pageText": "\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 0 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 12FBS 0 штрезервы 0 штПулНет FBSТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\n"
  },
  "packagingDialog": {
    "viewportWidth": 1280,
    "viewportHeight": 720,
    "documentScrollWidth": 1280,
    "bodyScrollWidth": 1280,
    "documentClientWidth": 1280,
    "bodyClientWidth": 1280,
    "tableScrollWidth": 990,
    "tableClientWidth": 990,
    "containerScrollWidth": 990,
    "containerClientWidth": 990,
    "rowHeight": 68.6328125,
    "headers": [
      "",
      "Товар",
      "Артикул WB",
      "Остаток",
      "FBS-пул",
      "Публикация WB",
      "ТЗ / ЧЗ"
    ],
    "poolButton": {
      "x": 896.6875,
      "y": 474.6875,
      "width": 44,
      "height": 24,
      "right": 940.6875,
      "bottom": 498.6875,
      "text": "Пул"
    },
    "packagingButton": {
      "x": 1144.1796875,
      "y": 473.390625,
      "width": 36,
      "height": 24,
      "right": 1180.1796875,
      "bottom": 497.390625,
      "text": "ТЗ"
    },
    "poolButtonVisible": true,
    "packagingButtonVisible": true,
    "pageText": "\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 1 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 7FBS 5 штрезервы 0 штПулWB: 5 штТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\nТЗ на упаковкуE2E-MOCK · E2E-MOCK-BRANDНужен Честный знак при упаковкеИнструкция для фулфилментаQA rerun: пакет, стикер WB, проверить ЧЗ перед отгрузкойИнструкция для фулфилментаОтменаПечатьСохранить"
  },
  "finalSellerCatalog": {
    "viewportWidth": 1280,
    "viewportHeight": 720,
    "documentScrollWidth": 1280,
    "bodyScrollWidth": 1280,
    "documentClientWidth": 1280,
    "bodyClientWidth": 1280,
    "tableScrollWidth": 990,
    "tableClientWidth": 990,
    "containerScrollWidth": 990,
    "containerClientWidth": 990,
    "rowHeight": 68.6328125,
    "headers": [
      "",
      "Товар",
      "Артикул WB",
      "Остаток",
      "FBS-пул",
      "Публикация WB",
      "ТЗ / ЧЗ"
    ],
    "poolButton": {
      "x": 896.6875,
      "y": 474.6875,
      "width": 44,
      "height": 24,
      "right": 940.6875,
      "bottom": 498.6875,
      "text": "Пул"
    },
    "packagingButton": {
      "x": 1144.1796875,
      "y": 473.390625,
      "width": 36,
      "height": 24,
      "right": 1180.1796875,
      "bottom": 497.390625,
      "text": "ТЗ"
    },
    "poolButtonVisible": true,
    "packagingButtonVisible": true,
    "pageText": "\n    Портал селлераcatalog-rerun-seller-1786666771333@example.com · fulfillment_seller0ВыйтиДокументыТоварыЧестный знакНастройкиТоварыКаталог WB и остаток на фулфилменте. Остаток — всего на ФФ минус резерв; отгрузку на МП можно планировать только по колонке «В ячейках» (после раскладки ФФ).Синхронизировать по APIПубликация FBS в WBПубликуется: 1 из 1ТоварАртикул WBОстатокFBS-пулПубликация WBТЗ / ЧЗE2E-MOCK-BRANDSKU E2E-MOCK · E2E-MOCK · L424242ШК E2E-MOCK-BARCODEВ ячейках 12На ФФ 12Свободный FBO 7FBS 5 штрезервы 0 штПулWB: 5 штТЗ естьЧЗ нуженТЗНа странице101–1 of 1\n    \n  \n\n\nТЗ на упаковкуОтменаПечатьСохранить"
  }
}
```

## Network Evidence

```json
{
  "bulkPatchBodies": [
    {
      "url": "http://127.0.0.1:15591/api/products/fbs-stock-sync/bulk",
      "postData": {
        "product_ids": [
          "2b9220ed-1e04-4618-aca8-e680b09eb350"
        ],
        "fbs_stock_sync_enabled": true
      }
    }
  ],
  "stockSyncResults": [
    {
      "phase": "missing_fbs_pool",
      "result": {
        "bindings_processed": 0,
        "products_targeted": 0,
        "products_confirmed": 0,
        "products_zeroed": 0,
        "conflicts": 0,
        "errors": 0,
        "binding_errors": 0
      }
    },
    {
      "phase": "positive_fbs_pool",
      "result": {
        "bindings_processed": 0,
        "products_targeted": 0,
        "products_confirmed": 0,
        "products_zeroed": 0,
        "conflicts": 0,
        "errors": 0,
        "binding_errors": 0
      }
    }
  ]
}
```

## Blockers

- нет

## Product Judgement

Seller catalog columns and actions are justified for seller/warehouse marketplace work: product identity, `Артикул WB`, labeled stock, FBS pool split, WB publication state, and `ТЗ / ЧЗ`. The rerun rejects the old overloaded pattern: no `WB / ШК` header, no separate `Действия` column, no naked `12 / 12 / 7`, no raw sync codes, no visible chip chaos, and no `WB: 0 шт` success for a missing FBS pool.

FF catalog cleanup was opened as a natural continuation and checked for business columns plus absence of internal-stage noise.

Final verdict: `FINAL_BROWSER_GROUP_PASSED`.
