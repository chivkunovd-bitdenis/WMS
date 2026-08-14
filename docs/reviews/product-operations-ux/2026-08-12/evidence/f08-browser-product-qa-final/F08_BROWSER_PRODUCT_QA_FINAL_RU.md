# F08 Browser Product QA Final

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: independent Browser Product QA Agent.
Статус: `BROWSER_PRODUCT_QA_PASSED`.

## UX Verdict

F08 directions / FBS pool после geometry rework проходит живую браузерную продуктовую проверку на 1280px. Seller product catalog открывается, строка товара компактная, отдельного поля/колонки `Лимит` и bulk `Включить всем` / `Выключить всем` нет. До выделения FBS-пула статус понятный: `FBS-пул не выделен`, toggle выключен. Создание FBS-направления, создание резерва, изменение направления, перевод резерва в FBS и удаление через подтверждение проходят кликами в UI. Ошибка превышения остатка показана человеческим текстом, raw `directions_exceed_stock` не виден.

FF catalog distribution popover не раздвигает body/document и остается в viewport. Экран не выглядит перегруженным техническими чипами, raw-статусами или лишними bulk-действиями.

## Evidence

- Browser: 147.0.7727.15
- Web: `http://127.0.0.1:15108`
- API: `http://127.0.0.1:18108`
- Seed: `SKU-F08-1786624960107`, product `aed594bb-66cf-4131-ad1f-400671f587ee`
- Seller geometry: `{"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"tableScrollWidth":990,"tableContainerClientWidth":990,"tableContainerScrollWidth":990,"rowHeight":91.515625,"rowText":"F08 compact product with long human name that must not stretch the catalog rowSKU SKU-F08-1786624960107——10106FBS 4 штрезервы 0 штРаспределениеПубликуется в WBНет ТЗРедактировать","fbsCellText":"Публикуется в WB","limitControls":0}`
- FF popover geometry: `{"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"popoverWidth":320,"popoverRight":1208,"popoverText":"SKU-F08-1786624960107F08 compact product with long human name that must not stretch the catalog rowFBS4 штРезервы/наборы0 штСвободно для FBO6 шт"}`
- Screenshots:
  - `01-seller-catalog-initial-1280.png`
  - `02-seller-directions-panel-empty-fbs.png`
  - `03-seller-after-create-edit-directions.png`
  - `04-seller-human-error-excess-stock.png`
  - `05-seller-delete-confirmation.png`
  - `06-ff-catalog-distribution-popover.png`
  - `07-ff-catalog-distribution-popover-element.png`

## Commands

```bash
DATABASE_URL='sqlite+aiosqlite:////Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812/docs/reviews/product-operations-ux/2026-08-12/evidence/f08-browser-product-qa-final/f08-browser-qa.sqlite' WMS_AUTO_CREATE_SCHEMA=1 JWT_SECRET_KEY='qa-jwt-secret-key-minimum-32-characters-long' E2E_MOCK_WB_CARDS=1 E2E_MOCK_WB_SUPPLIES=1 E2E_MOCK_WB_WAREHOUSES=1 python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18108
VITE_API_PROXY='http://127.0.0.1:18108' E2E_SELLER_PATH_PREFIX='/seller' VITE_SELLER_PORTAL_URL='http://127.0.0.1:15108/seller/' npm run dev -- --host 127.0.0.1 --port 15108
F08_WEB_ORIGIN='http://127.0.0.1:15108' F08_API_ORIGIN='http://127.0.0.1:18108' node docs/reviews/product-operations-ux/2026-08-12/evidence/f08-browser-product-qa-final/f08-browser-product-qa-final.mjs
```

## Checks

- PASS: API health-check — 200
- PASS: FF registration and token — f08-browser-admin-1786624960107@example.com
- PASS: Inbound receiving started — 200
- PASS: Physical stock seeded via inbound operations — SKU-F08-1786624960107: 10
- PASS: No bulk enable button — bulk enable text absent
- PASS: No bulk disable button — bulk disable text absent
- PASS: No per-row Limit field — Лимит absent in product row
- PASS: No FBS pool status is human — FBS-пул не выделен
- PASS: No FBS pool toggle disabled — toggle disabled before FBS direction
- PASS: FBS direction enables safe publication toggle — toggle enabled after FBS allocation
- PASS: Excess stock error is human — Нельзя распределить больше, чем есть на ФФ. Уменьшите количество или освободите другое направление.
- PASS: Raw stock-direction error hidden — Нельзя распределить больше, чем есть на ФФ. Уменьшите количество или освободите другое направление.
- PASS: Delete cancel does not call DELETE — DELETE requests: 0
- PASS: Delete requires confirmation — DELETE requests: 1
- PASS: Seller product row compact at 1280px — rowHeight=91.515625
- PASS: No document horizontal overflow / black strip — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"tableScrollWidth":990,"tableContainerClientWidth":990,"tableContainerScrollWidth":990,"rowHeight":91.515625,"rowText":"F08 compact product with long human name that must not stretch the catalog rowSKU SKU-F08-1786624960107——10106FBS 4 штрезервы 0 штРаспределениеПубликуется в WBНет ТЗРедактировать","fbsCellText":"Публикуется в WB","limitControls":0}
- PASS: No body horizontal overflow — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"tableScrollWidth":990,"tableContainerClientWidth":990,"tableContainerScrollWidth":990,"rowHeight":91.515625,"rowText":"F08 compact product with long human name that must not stretch the catalog rowSKU SKU-F08-1786624960107——10106FBS 4 штрезервы 0 штРаспределениеПубликуется в WBНет ТЗРедактировать","fbsCellText":"Публикуется в WB","limitControls":0}
- PASS: Seller table does not overflow container — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"tableScrollWidth":990,"tableContainerClientWidth":990,"tableContainerScrollWidth":990,"rowHeight":91.515625,"rowText":"F08 compact product with long human name that must not stretch the catalog rowSKU SKU-F08-1786624960107——10106FBS 4 штрезервы 0 штРаспределениеПубликуется в WBНет ТЗРедактировать","fbsCellText":"Публикуется в WB","limitControls":0}
- PASS: Limit remains absent after CRUD — Публикуется в WB
- PASS: No hidden seller-fbs-limit controls — count=0
- PASS: No technical/raw texts on seller screen — raw technical strings absent
- PASS: FF popover does not widen document — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"popoverWidth":320,"popoverRight":1208,"popoverText":"SKU-F08-1786624960107F08 compact product with long human name that must not stretch the catalog rowFBS4 штРезервы/наборы0 штСвободно для FBO6 шт"}
- PASS: FF popover does not widen body — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"popoverWidth":320,"popoverRight":1208,"popoverText":"SKU-F08-1786624960107F08 compact product with long human name that must not stretch the catalog rowFBS4 штРезервы/наборы0 штСвободно для FBO6 шт"}
- PASS: FF popover stays in viewport — {"viewportWidth":1280,"bodyScrollWidth":1280,"documentScrollWidth":1280,"popoverWidth":320,"popoverRight":1208,"popoverText":"SKU-F08-1786624960107F08 compact product with long human name that must not stretch the catalog rowFBS4 штРезервы/наборы0 штСвободно для FBO6 шт"}
- PASS: FF popover content is business-readable — SKU-F08-1786624960107F08 compact product with long human name that must not stretch the catalog rowFBS4 штРезервы/наборы0 штСвободно для FBO6 шт
- PASS: No overloaded/technical text in FF catalog view — forbidden strings absent
