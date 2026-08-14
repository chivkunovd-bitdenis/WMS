# CATALOG_FINAL_REGRESSION_BROWSER_PRODUCT_QA_STRICT_RU

Дата: 2026-08-14 MSK.

Роль: Catalog Final Regression Live Product Browser QA Agent.

Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

HEAD: `d59959de70a8b9d447f200bdb703023c35b7b449`.

Verdict: `BROWSER_PRODUCT_QA_PASSED`.

Код, commit, push, staging, production, Railway и secrets не трогались. Проверка была только live browser QA по catalog blocker F08-F11/F16/F22/F23.

## Live Browser

| Поле | Значение |
| --- | --- |
| browser_used | `yes` |
| browser | Chromium via Playwright `headless=false` |
| viewport | `1280x720` |
| frontend | `http://127.0.0.1:15458/` |
| backend | `http://127.0.0.1:18458/` |
| route | `http://127.0.0.1:15458/seller/products` |
| DB | `/tmp/wms-catalog-final-browser-qa-20260814-18458.sqlite` |
| live evidence JSON | `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/live-browser-evidence.json` |
| stable visual JSON | `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/stable-visual-evidence.json` |

Фикстура создана как e2e path: регистрация FF, seller account, warehouse/location, product, WB mock cards sync, WB link `nm_id=424242`, packaging instruction, inbound intake, box scans, verify/post. Проверочный товар:

- seller: `qa-catalog-seller-final-1786665779346@example.com`
- SKU: `SKU-FINAL-final-1786665779346`
- product_id: `724b4820-5a34-468b-98fe-bd2709dca43c`
- inbound_id: `4d9ee8a6-10c2-4394-9292-1e472ad56356`
- FBS direction: `1800ff1d-9a70-4875-887e-baaae86e6d98`

## Screenshots

- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/01-seller-products-initial-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/02-selected-bulk-confirm-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/03-fbs-pool-drawer-empty-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/04-fbs-direction-created-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/05-packaging-dialog-from-tz-chz-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/06-fbs-drawer-stable-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/07-packaging-dialog-stable-1280.png`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/catalog-final-regression-browser-product-qa-strict/08-selected-bulk-confirm-stable-1280.png`

## Mandatory Path Result

1. `/seller/products` был открыт в живом Chromium на `1280x720`: PASS.
2. Screenshot paths и DOM metrics сохранены: PASS.
3. Header `Артикул WB` виден, `WB / ШК` отсутствует: PASS.
4. Stock cell читается как бизнес-данные: `В ячейках 12`, `На ФФ 12`, `Свободный FBO 12`; голого `12 / 12 / 7` или `12 / 12 / 12` нет: PASS.
5. Selection flow: выбрана одна строка, `Изменить публикацию` -> `Включить`, confirmation говорит `для 1 товаров`, содержит `Будут изменены только выбранные товары`, selected list содержит SKU. PATCH body: `product_ids=["724b4820-5a34-468b-98fe-bd2709dca43c"]`, `product_ids:null` нет: PASS.
6. FBS pool control: кнопка `Пул` с tooltip/aria `Настроить FBS-пул` открыла drawer, создано FBS-направление `5 шт`. Main row показывает `FBS 5 шт`, `резервы 0 шт`, `Свободный FBO 7`; drawer показывает `FBS 5 шт`, `Резервы 0 шт`, `Свободный FBO 7 шт`: PASS.
7. Packaging action находится в колонке `ТЗ / ЧЗ`: отдельной колонки `Действия` нет, кнопка `ТЗ` открывает `ТЗ на упаковку`: PASS.
8. Page/table layout: `documentScrollWidth=1280`, `bodyScrollWidth=1280`, `tableScrollWidth=990`, `containerClientWidth=990`; page-level horizontal overflow и black strip не воспроизведены. Row height `68.6328125px` <= `72px`; table headers/actions не клиппятся: PASS.
9. Short statuses: до FBS pool статус `Нет FBS`, после создания FBS pool статус `Проверяем WB`; raw codes/chip noise/technical labels и `Лимит` не видны. `WB: N шт` в этой локальной фикстуре не появился, потому что live WB confirmation не моделировалась: PASS.
10. F22 incident path: при missing FBS pool строка остаётся `Нет FBS`, toggle disabled, `WB: 0 шт` не показывается и не публикуется; bulk update остаётся selected-only: PASS.

## DOM Metrics Snapshot

| Metric | Value |
| --- | --- |
| viewport | `1280x720` |
| headers | `["", "Товар", "Артикул WB", "Остаток", "FBS-пул", "Публикация WB", "ТЗ / ЧЗ"]` |
| rowHeight | `68.6328125` |
| documentScrollWidth | `1280` |
| bodyScrollWidth | `1280` |
| tableScrollWidth | `990` |
| tableClientWidth | `990` |
| containerScrollWidth | `990` |
| containerClientWidth | `990` |
| pool button bounds | `x=896.6875 y=474.6875 width=44 height=24` |
| packaging button bounds | `x=1144.1796875 y=473.390625 width=36 height=24` |

## Product Read

Экран теперь проходит целевой catalog rework: оператор видит не техническое `WB / ШК`, а `Артикул WB`; остатки подписаны по складскому смыслу; FBS/FBO split читается в строке и подробно подтверждается в drawer; publication action не мутирует все товары; missing FBS pool не превращается в успешную публикацию `0`.

Визуальная ремарка не как blocker: stable drawer screenshot показывает, что верхняя shell-шапка визуально перекрывает самый верх drawer, хотя `Распределение остатка` есть в DOM, а обязательные FBS/FBO значения и действия видны и кликабельны. Для этого catalog blocker я не снимаю PASS, но это стоит держать как отдельный shell/drawer polish item, если будет отдельная задача по overlay layering.

Final verdict: `BROWSER_PRODUCT_QA_PASSED`.
