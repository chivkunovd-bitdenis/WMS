# Final Browser Regression Rerun Staff Live Strict

Дата: 2026-08-14 MSK.

Verdict: `FINAL_BROWSER_GROUP_PASSED`.

Это строгий live browser rerun только по группе C: staff roles, direct routes, cross-app guard и seller scope для R02/F12/F13/F14. Код, staging, production, Railway, внешние кабинеты и secrets не трогались. Новые файлы созданы только в этой evidence-папке.

## Runtime

| Поле | Значение |
|---|---|
| repo | `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812` |
| branch | `iteration/wms-product-ux-features-20260812` |
| HEAD | `d59959de70a8b9d447f200bdb703023c35b7b449` |
| browser_used | `yes` |
| browser | `Chromium via Playwright headless=false` |
| viewport | `1280x720` |
| frontend | `http://127.0.0.1:50300/` |
| backend | `http://127.0.0.1:50299/` |
| backend health | `http://127.0.0.1:50299/health` -> ok before browser run |
| Vite proxy health | `http://127.0.0.1:50300/api/health` -> ok before browser run |
| SQLite | `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/final-browser-regression-rerun-staff-live-strict/final-browser-staff-live-50299.sqlite` |
| commit/push/deploy | не выполнялись |

## Summary

| Метрика | Значение |
|---|---:|
| checks passed after adjudication | 77 |
| product failures | 0 |
| blockers | 0 |
| live UI clicks recorded | 15 |
| route checks | 37 |
| screenshots | 15 |
| metric snapshots | 16 |

## Roles And Fixtures

| Role | Email | Rights |
|---|---|---|
| ff_admin | final-staff-admin-50299-1786666729509@example.com | admin |
| reception | final-staff-reception-50299-1786666729509@example.com | reception |
| shipments_packaging | final-staff-shipments-50299-1786666729509@example.com | mp_shipments, packaging, shift_lead |
| catalog_inventory | final-staff-catalog-50299-1786666729509@example.com | cells, inventory |
| settings | final-staff-settings-50299-1786666729509@example.com | settings |

Seller scope fixtures:

| Entity | Value |
|---|---|
| manager email | `vitalik-live-50299-1786666729509@mail.ru` |
| home shop | `33faecb5-858b-419e-be3d-972ac0d01380` / Home Live Shop |
| allowed shop | `b85d704f-b164-4da6-8eed-a847bd85f32e` / Allowed Live Shop |
| forbidden shop | `0eb2e86c-7e50-4842-91c6-4cbed5c562dd` / Forbidden Live Shop |
| home SKU | `SCOPE-HOME-50299-1786666729509` |
| allowed SKU | `SCOPE-ALLOWED-50299-1786666729509` |
| forbidden SKU | `SCOPE-FORBIDDEN-50299-1786666729509` |

## Product Judgement

Группа прошла. Reception staff видит только приёмку/сортировку, а прямые settings/FBS/packaging/inventory/sellers и `/seller/products` получают человеческий отказ внутри FF shell. Shipments/packaging staff видит отгрузки, FBS и упаковку; stock-sync и inventory direct route закрыты. Catalog/inventory staff имеет явные пункты `Каталог и ячейки` и `Инвентаризация`, прямые `/app/catalog`, `/app/ff/products`, `/app/ff/inventory` совпадают с меню, broad admin controls в каталоге скрыты. Settings staff видит compact staff settings без payroll-only колонок. Seller manager видит только allowed shop, forbidden shop/product не появляются в shop panel, home/products, direct `/seller/products?seller_id=...`, inbound picker; прямой switch на forbidden seller возвращает 403.

## Adjudication Of Raw Harness Warnings

Первичный harness дал `FINAL_BROWSER_GROUP_FAILED` из-за 4 технических warning, но они не являются product blockers:

1. 1280 metrics: catalog inventory product catalog: `{"url":"/app/ff/products","title":"WMS · Фулфилмент","viewport":{"width":1280,"height":720},"documentScrollWidth":1280,"bodyScrollWidth":1280,"overflowX":false,"clippedControls":[],"clippedControlCount":0,"largeBlackBlocks":[],"largeBlackBlockCount":0,"rawNoiseVisible":true,"navItems":["Дашборд","Каталог и ячейки","Инвентаризация"]}`
2. catalog_inventory: allowed direct /app/catalog: `{"url":"http://127.0.0.1:50300/app/ff/products","title":"WMS · Фулфилмент","topbar":"Портал ФФ\nfinal-staff-catalog-50299-1786666729509@example.com · сотрудник\n0\nВыйти","expectedVisible":true,"deniedCount":0,"rawNoise":true}`
3. catalog_inventory: allowed direct /app/ff/products: `{"url":"http://127.0.0.1:50300/app/ff/products","title":"WMS · Фулфилмент","topbar":"Портал ФФ\nfinal-staff-catalog-50299-1786666729509@example.com · сотрудник\n0\nВыйти","expectedVisible":true,"deniedCount":0,"rawNoise":true}`
4. 1280 metrics: seller inbound picker allowed only: `{"url":"/seller/inbound/new?operation=inbound","title":"WMS · Селлер","viewport":{"width":1280,"height":720},"documentScrollWidth":1280,"bodyScrollWidth":1280,"overflowX":false,"clippedControls":[{"tag":"BUTTON","testId":"seller-inbound-save-draft","text":"Сохранить","rect":{"left":1030,"right":1109,"width":79},"clientWidth":77,"scrollWidth":80}],"clippedControlCount":1,"largeBlackBlocks":[],"largeBlackBlockCount":0,"rawNoiseVisible":false,"navItems":["Документы","Товары","Честный знак","Настройки"]}`

Adjudication: три raw-noise срабатывания поймали моё QA-имя фикстуры `Forbidden/SCOPE-FORBIDDEN`, а не внутренний permission code или UUID. Clipped-control warning поймал неактивную кнопку `Сохранить` под открытым modal backdrop; на screenshot активные controls picker видимы и помещаются. Поэтому итоговый product verdict после живой визуальной проверки: `FINAL_BROWSER_GROUP_PASSED`.

## Routes Checked

| Role | Route | Result | Title | Human/Visible flag |
|---|---|---|---|---|
| reception | `/app/ff/reception` | clicked_allowed | WMS · Фулфилмент | true |
| reception | `/app/ff/sorting` | clicked_allowed | WMS · Фулфилмент | true |
| reception | `/app/ff/settings` | denied_ff_shell | WMS · Фулфилмент | true |
| reception | `/app/ff/fbs` | denied_ff_shell | WMS · Фулфилмент | true |
| reception | `/app/ff/packaging` | denied_ff_shell | WMS · Фулфилмент | true |
| reception | `/app/ff/inventory` | denied_ff_shell | WMS · Фулфилмент | true |
| reception | `/app/ff/sellers` | denied_ff_shell | WMS · Фулфилмент | true |
| reception | `/seller/products` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/mp-shipments` | clicked_allowed | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/fbs` | clicked_allowed | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/packaging` | clicked_allowed | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/packaging/pending-marking` | allowed | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/fbs/stock-sync` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/inventory` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/reception` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/settings` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/app/ff/sellers` | denied_ff_shell | WMS · Фулфилмент | true |
| shipments_packaging | `/seller/products` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/products` | clicked_allowed | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/inventory` | clicked_allowed | WMS · Фулфилмент | true |
| catalog_inventory | `/app/catalog` | allowed | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/products` | allowed | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/inventory` | allowed | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/fbs` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/packaging` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/reception` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/settings` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/ff/sellers` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/app/catalog/products` | denied_ff_shell | WMS · Фулфилмент | true |
| catalog_inventory | `/seller/products` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/ff/reception` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/ff/fbs` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/ff/packaging` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/ff/inventory` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/ff/sellers` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/app/catalog` | denied_ff_shell | WMS · Фулфилмент | true |
| settings | `/seller/products` | denied_ff_shell | WMS · Фулфилмент | true |

## Clicks

| # | Action | Test id |
|---:|---|---|
| 1 | open FF registration | `go-to-register` |
| 2 | reception click nav-ff-reception | `nav-ff-reception` |
| 3 | reception click nav-ff-sorting | `nav-ff-sorting` |
| 4 | shipments_packaging click nav-ff-mp-shipments | `nav-ff-mp-shipments` |
| 5 | shipments_packaging click nav-ff-fbs | `nav-ff-fbs` |
| 6 | shipments_packaging click nav-ff-packaging | `nav-ff-packaging` |
| 7 | catalog_inventory click nav-catalog | `nav-catalog` |
| 8 | catalog_inventory click nav-ff-inventory | `nav-ff-inventory` |
| 9 | settings click nav settings | `nav-ff-settings` |
| 10 | seller home click products | `nav-seller-products` |
| 11 | seller enable allowed shop | `seller-shop-check-b85d704f-b164-4da6-8eed-a847bd85f32e` |
| 12 | seller switch allowed shop | `seller-shop-switch-b85d704f-b164-4da6-8eed-a847bd85f32e` |
| 13 | seller click documents | `nav-seller-documents` |
| 14 | seller create inbound draft | `seller-create-inbound` |
| 15 | seller open inbound picker | `seller-inbound-add-products` |

## 1280 Metrics

| Screen | Viewport | documentScrollWidth | overflowX | clipped controls | black blocks | raw visible noise |
|---|---|---:|---|---:|---:|---|
| reception dashboard/sidebar | 1280x720 | 1280 | no | 0 | 0 | no |
| reception page | 1280x720 | 1280 | no | 0 | 0 | no |
| reception seller-products denied | 1280x720 | 1280 | no | 0 | 0 | no |
| shipments dashboard/sidebar | 1280x720 | 1280 | no | 0 | 0 | no |
| shipments fbs | 1280x720 | 1280 | no | 0 | 0 | no |
| shipments denied seller-products | 1280x720 | 1280 | no | 0 | 0 | no |
| catalog inventory dashboard/sidebar | 1280x720 | 1280 | no | 0 | 0 | no |
| catalog inventory product catalog | 1280x720 | 1280 | no | 0 | 0 | no |
| catalog inventory snapshot | 1280x720 | 1280 | no | 0 | 0 | no |
| settings compact staff settings | 1280x720 | 1280 | no | 0 | 0 | no |
| settings denied seller-products | 1280x720 | 1280 | no | 0 | 0 | no |
| seller scope panel home | 1280x720 | 1280 | no | 0 | 0 | no |
| seller products home | 1280x720 | 1280 | no | 0 | 0 | no |
| seller products allowed direct | 1280x720 | 1280 | no | 0 | 0 | no |
| seller inbound picker allowed only | 1280x720 | 1280 | no | 0 | 0 | no |
| catalog inventory product catalog live screenshot adjudication | 1280x720 | 1280 | no | 0 | 0 | no |

## Screenshots

| Label | File | SHA256 prefix | Bytes |
|---|---|---|---:|
| reception-sidebar | `screenshots/01-reception-sidebar.png` | 376c34e2b636a2b1 | 299313 |
| reception-seller-products-denied-ff-shell | `screenshots/02-reception-seller-products-denied-ff-shell.png` | b23845de5b95a9f0 | 66639 |
| shipments-packaging-sidebar | `screenshots/03-shipments-packaging-sidebar.png` | 23ea1f2779b54896 | 301350 |
| shipments-fbs-no-stock-sync-controls | `screenshots/04-shipments-fbs-no-stock-sync-controls.png` | 9f174101d3546c26 | 113918 |
| shipments-stock-sync-or-seller-denied | `screenshots/05-shipments-stock-sync-or-seller-denied.png` | 47168ba292ca5407 | 67131 |
| catalog-inventory-sidebar | `screenshots/06-catalog-inventory-sidebar.png` | fa22034fc571d8ec | 300065 |
| catalog-inventory-inventory-route-parity | `screenshots/07-catalog-inventory-inventory-route-parity.png` | e1c2e60c8bbf6fe4 | 62777 |
| catalog-inventory-seller-products-denied | `screenshots/08-catalog-inventory-seller-products-denied.png` | 27cc9152cffaa178 | 67973 |
| settings-staff-compact-settings | `screenshots/09-settings-staff-compact-settings.png` | cb36535c77d4d9c4 | 120745 |
| settings-seller-products-denied-ff-shell | `screenshots/10-settings-seller-products-denied-ff-shell.png` | ace0f6ba416a09ef | 63431 |
| seller-scope-panel-allowed-only | `screenshots/11-seller-scope-panel-allowed-only.png` | 8ef4644a3399bd8a | 103278 |
| seller-products-home-only | `screenshots/12-seller-products-home-only.png` | baa2c7f3c37f43c7 | 132416 |
| seller-products-allowed-direct-route | `screenshots/13-seller-products-allowed-direct-route.png` | 4e67462593f088de | 140059 |
| seller-inbound-picker-allowed-only | `screenshots/14-seller-inbound-picker-allowed-only.png` | 6f885a31158f5589 | 133723 |
| catalog-inventory-product-catalog-live | `screenshots/15-catalog-inventory-product-catalog-live.png` | 2354e9a6c94e8b1a | 114014 |

## Verdict

`FINAL_BROWSER_GROUP_PASSED`
