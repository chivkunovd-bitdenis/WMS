# F05 Product Browser QA Rerun Live Strict

Дата: 2026-08-14.

Роль: STRICT LIVE Product Browser QA Agent.

Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Scope: только F05 seller inbound fact-card rerun после финального code review. Код не редактировался. Production/staging/Railway/secrets не трогались. Этот отчет не является release-ready статусом.

## Verdict

`PRODUCT_BROWSER_APPROVED`

Причина: live browser pass выполнен на реальном UI. Основная карточка проведенной seller-приемки с недостачей и товаром, добавленным ФФ, стала рабочей fact-card: селлер сразу видит общий итог, блок `Что не так`, проблемные строки, максимум 5 колонок, локальное раскрытие деталей и no-overflow на 1280 px. Старый 9-column report не вернулся.

Критичный rerun blocker закрыт: после reload `/seller/inbound/...` остается `WMS · Селлер`, topbar/left nav seller shell на месте, `Документы` ведет на `/seller/documents`, а не на `/documents` и не в FF/public login. Дополнительно проверил direct seller deep route после возврата в FF root: seller shell также сохранился.

Не называю F05 release-ready: это только Product Browser QA verdict по F05 rerun scope.

## Browser Proof

- `browser_used`: yes.
- Browser surface: Browser plugin `browser-client`, live IAB tab from existing FF dashboard tab.
- Frontend: `http://127.0.0.1:5186/`.
- Seller portal: `http://127.0.0.1:5186/seller/`.
- Backend API: `http://127.0.0.1:18056/`.
- Temporary DB: `backend/qa-f05-rerun-live-strict-1786656744.db`.
- Viewport checked in browser: `1280x720`.
- FF context before seller route: visible `Портал ФФ` at `/app/ff/dashboard` for `ff-admin-f05-rerun-1786657008405@example.com`.
- Seller context: visible `Портал селлера` for `seller-f05-final-1786657450177@example.com`.
- Note: browser-side storage probing returned no reliable token values, so dual-context proof is visual and route-based: the same live browser session showed FF dashboard, then seller portal, then FF root again, then direct seller deep route and reload.

## Fixture

Local-only fixture created against the local API, then verified through live browser clicks.

- FF admin used in visible browser: `ff-admin-f05-rerun-1786657008405@example.com`.
- Seller user: `seller-f05-final-1786657450177@example.com`.
- Seller id: `63b539c4-bb8b-422b-882d-50400faf3c1e`.
- Warehouse: `F05 Very Long Warehouse Name For Reload Shell And Ellipsis Check`.
- Discrepancy document: `60d0a723-f0fb-4e73-9810-8a1832497d3c`.
- Clean document: `db83c309-106f-458d-88fb-bd865f499df1`.
- Planned SKU: `planned-sku-f05-final-1786657450177`.
- FF-added SKU: `ff-added-f05-final-1786657450177`.
- Discrepancy data: planned product `3`, accepted planned product `2`, FF-added product planned `0` / accepted `1`, boxes `plan 2 / fact 0`.
- Clean data: planned `2`, accepted `2`, no discrepancy.

## Routes And Clicks

Observed routes:

- `http://127.0.0.1:5186/app/ff/dashboard`
- `http://127.0.0.1:5186/seller/`
- `http://127.0.0.1:5186/seller/documents`
- `http://127.0.0.1:5186/seller/inbound/60d0a723-f0fb-4e73-9810-8a1832497d3c`
- reload kept `http://127.0.0.1:5186/seller/inbound/60d0a723-f0fb-4e73-9810-8a1832497d3c`
- clicking `Документы` after reload landed on `http://127.0.0.1:5186/seller/documents`
- `http://127.0.0.1:5186/seller/inbound/db83c309-106f-458d-88fb-bd865f499df1`
- reload kept `http://127.0.0.1:5186/seller/inbound/db83c309-106f-458d-88fb-bd865f499df1`
- direct deep route after FF root: `http://127.0.0.1:5186/seller/inbound/60d0a723-f0fb-4e73-9810-8a1832497d3c`
- direct deep route reload still kept seller shell, then `Документы` landed on `/seller/documents`

Live clicks/inputs:

- seller login email/password filled.
- clicked `Войти`.
- clicked seller nav `Документы`.
- clicked discrepancy document row `60d0a723-f0fb-4e73-9810-8a1832497d3c`.
- clicked expand icon on FF-added row.
- clicked collapse on the same row.
- used browser reload on discrepancy deep route.
- clicked `Документы` after discrepancy reload.
- clicked clean document row `db83c309-106f-458d-88fb-bd865f499df1`.
- used browser reload on clean deep route.
- clicked `Документы` after clean reload.
- opened direct seller deep route after visiting FF root.
- reloaded direct seller deep route.
- clicked `Документы` after direct deep route reload.

## Screenshots

User requested exactly one repo artifact, so no separate screenshot files were added under `docs/`. Screenshots were captured during the live run as temporary local evidence:

- FF start dashboard: `/tmp/wms-f05-rerun-live-strict/31-ff-start-dashboard.png`
- Seller login: `/tmp/wms-f05-rerun-live-strict/32-seller-login.png`
- Seller documents after login: `/tmp/wms-f05-rerun-live-strict/34-documents-with-rows.png`
- Discrepancy fact-card: `/tmp/wms-f05-rerun-live-strict/35-discrepancy-card.png`
- Discrepancy details expanded: `/tmp/wms-f05-rerun-live-strict/36-discrepancy-expanded.png`
- Discrepancy after reload: `/tmp/wms-f05-rerun-live-strict/37-discrepancy-after-reload.png`
- Documents after reload nav: `/tmp/wms-f05-rerun-live-strict/38-documents-after-reload-nav.png`
- Clean fact-card: `/tmp/wms-f05-rerun-live-strict/39-clean-card.png`
- Clean after reload: `/tmp/wms-f05-rerun-live-strict/40-clean-after-reload.png`
- FF root after seller checks: `/tmp/wms-f05-rerun-live-strict/42-ff-root-after-seller-login.png`
- Dual-context direct seller route: `/tmp/wms-f05-rerun-live-strict/43-dual-context-direct-deep-route.png`
- Dual-context direct seller route after reload: `/tmp/wms-f05-rerun-live-strict/44-dual-context-after-direct-reload.png`
- Dual-context documents nav: `/tmp/wms-f05-rerun-live-strict/45-dual-context-documents-nav.png`

## Product Judgment

### Main Discrepancy Card

The first screen answers the seller question quickly: what was declared, what was accepted, and what is wrong. `Итог приемки` shows `Заявлено 3 · принято 3` and `Есть расхождения`. `Что не так` shows `Недостача 1`, `Излишек 1`, `Добавлено ФФ: 1 товар`, and the box issue `Короба: план 2 · факт 0`. This is useful warehouse information for this conducted document and does not require the seller to calculate the problem from table numbers.

The card is not the old report. Visible headers are exactly `Товар`, `Заявлено`, `Принято`, `Итог`, and the expand icon column. Old first-level report headers `Фото`, `Артикул`, `ШК`, `Артикул продавца`, `Артикул WB`, `Наименование`, `Расхождение` were not present.

The first row is the FF-added product and carries `Добавлено ФФ`, `0`, `1`, `Излишек 1`. The second row is the planned product with `3`, `2`, `Недостача 1`. This ordering is useful: the seller sees the rows that require attention before normal rows.

### Expand Details

Expand/collapse worked locally and did not navigate away. Expanded details show full article, barcode, seller/WB article fields, and full warehouse label. That is the right information weight: full identifiers are available for audit, but they do not occupy first-level columns.

The expand tooltip `Скрыть сверку` is useful because the icon-only action has a name. It briefly overlays the far right edge while hovering, but does not hide business values.

### Reload And Shell

Before and after reload of `/seller/inbound/60d0a723-f0fb-4e73-9810-8a1832497d3c`:

- `document.title`: `WMS · Селлер`;
- topbar: `Портал селлера`;
- left nav: `Документы`, `Товары`, `Честный знак`, `Настройки`;
- route: `/seller/inbound/60d0a723-f0fb-4e73-9810-8a1832497d3c`;
- `Документы` click after reload: `/seller/documents`;
- no `/documents` FF/public route;
- no login screen.

After visiting FF root in the same browser session, direct seller deep route and reload also kept seller shell and returned to `/seller/documents`. This covers the critical rerun blocker.

### Geometry At 1280

Measured in live browser on discrepancy card:

- viewport: `1280x720`;
- document scroll width: `1280`;
- body scroll width: `1280`;
- table container client width: `958`;
- table container scroll width: `958`;
- header count: `5`;
- visible old report headers: `[]`;
- visible raw technical terms in fact-card body: `[]`.

There was no horizontal overflow, no 9-column report comeback, and no visible text collision in the card.

### Clean State

Clean state passed functionally and visually enough for this rerun: `Без расхождений`, `Заявлено 2 · принято 2`, one normal row, `ОК`, no red problem row, no draft controls, no old report columns, no overflow, reload preserved seller shell and data.

Product polish note: the separate card title `Что не так` is still semantically awkward when nothing is wrong. The content `ФФ принял заявленное количество` is correct, but a quieter clean-state line would be more natural. I do not treat this as a rerun blocker because it does not overload the screen, does not hide the result, and the previous blocker was shell/routing.

### Visible Element Usefulness

- Seller logo and `Портал селлера`: useful shell ownership signal.
- Topbar email: useful account context.
- Topbar role `fulfillment_seller`: understandable to developers but not ideal product Russian; not introduced by F05 and not blocking this rerun.
- Bell icon: neutral shell control; not noisy.
- `Выйти`: expected session control.
- Left nav: compact and route-correct.
- Meta row `Поставка · В сортировке · warehouse`: useful; long warehouse ellipsis protects layout.
- `Итог приемки`: main business result, useful.
- `Что не так`: useful for discrepancy; slightly awkward for clean state.
- Product placeholder avatars: neutral fallback when product photo is absent; they do not consume a separate column.
- `Заявлено`, `Принято`, `Итог`: the right visible warehouse math.
- Expand icon: useful for full identifiers without first-level overload.

## Gate Result

- `browser_used`: yes.
- `main discrepancy card`: passed.
- `Что не так`: passed for discrepancy; clean-state polish note remains.
- `max 5 columns`: passed.
- `no old 9-column report`: passed.
- `expand/details`: passed.
- `1280 no overflow`: passed.
- `reload seller shell`: passed.
- `Документы` after reload -> `/seller/documents`: passed.
- `dual-context visible route check`: passed by FF root -> seller direct deep route -> reload -> seller docs.
- `clean state if possible`: passed with polish note.
- Final verdict: `PRODUCT_BROWSER_APPROVED`.
