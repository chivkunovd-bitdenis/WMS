# R02 Staff Navigation Product Browser QA Final Live Strict

Дата: 2026-08-14.

Роль: STRICT LIVE Product Browser QA Agent по R02 final rerun after surface
guard.

Рабочий Git-root:
`/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Код frontend/backend не редактировался. Production, staging, Railway, внешние
кабинеты и secrets не открывались и не трогались. Проверка выполнена только на
локальном live UI.

## Verdict

`PRODUCT_BROWSER_APPROVED`

Коротко: blocker из предыдущего R02 live rerun закрыт в браузере. FF admin и
FF staff с FF-сессией, но без seller-login, при прямом открытии
`/seller/products` остаются в FF shell: title `WMS · Фулфилмент`, виден
`app-frame`, topbar `Портал ФФ`, пользователь в topbar, `logout`, и
человеческий отказ `Нет доступа к этому разделу.`. Seller login при этом не
показывается, seller nav/table не появляются.

Контрольные seller-сценарии тоже прошли: `/seller/` остаётся seller entrypoint,
а seller-token direct `/seller/products` открывает SellerApp с таблицей товаров.

Это не release-ready statement. R02 browser gate прошёл; общий release/staging
этим артефактом не объявляется.

## Inputs Read

- `AGENTS.md`;
- `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/r02-staff-nav-product-browser-qa-rerun-live-strict/R02_STAFF_NAV_PRODUCT_BROWSER_QA_RERUN_LIVE_STRICT_RU.md`;
- `docs/reviews/product-operations-ux/2026-08-12/evidence/r02-surface-guard-code-review-strict/R02_SURFACE_GUARD_CODE_REVIEW_STRICT_RU.md`;
- R02 handoff section in
  `docs/reviews/product-operations-ux/2026-08-12/HANDOFF_TO_NEW_CHAT_STRICT_WMS_GATE_RU.md`.

## Browser Evidence

Browser used: `yes`.

Поверхность: Codex Browser / `browser-client` / `tab.playwright`.

Локальные URL и порты:

- frontend: `http://127.0.0.1:5231/`;
- backend: `http://127.0.0.1:18191/`;
- DB: `backend/e2e-r02-final-live-strict-1786661604.db`;
- viewport: `1280x720`.

Run counters:

| Metric | Count |
|---|---:|
| UI logins through visible login forms | 7 |
| UI clicks recorded | 14 |
| route checks total | 54 |
| clicked allowed route checks | 8 |
| direct allowed route checks | 2 |
| direct denied FF-shell route checks | 44 |
| screenshots captured by browser | 9 |
| failures | 0 |
| blockers | 0 |

Скриншоты снимались живым браузером как byte snapshots. Чтобы сохранить
требование "exactly one artifact", отдельные screenshot-файлы в repo не
создавались; ниже зафиксированы label, URL, title, sha256 prefix и размер.

| Label | URL | Title | SHA256 prefix | Bytes |
|---|---|---|---|---:|
| admin-after-ui-login | `/app/ff/dashboard` | `WMS · Фулфилмент` | `2b30098441c97c48` | 75752 |
| admin-settings-payroll | `/app/ff/settings` | `WMS · Фулфилмент` | `a10e8e13264b4aad` | 67226 |
| admin-seller-products-denied | `/seller/products` | `WMS · Фулфилмент` | `ff22f1fbe5ce6442` | 29335 |
| shipments-seller-products-denied | `/seller/products` | `WMS · Фулфилмент` | `edd9a8252caf833f` | 22427 |
| inventory-seller-products-denied | `/seller/products` | `WMS · Фулфилмент` | `0ebd9fa6a9d2f881` | 23029 |
| reception-seller-products-denied | `/seller/products` | `WMS · Фулфилмент` | `2dc21d02e539fb33` | 22346 |
| settings-seller-products-denied | `/seller/products` | `WMS · Фулфилмент` | `d43fb0af4e0de4ef` | 21202 |
| seller-home-ff-token-entrypoint | `/seller/` | `WMS · Селлер` | `c58a334f6c478080` | 28789 |
| seller-products-with-seller-token | `/seller/products` | `WMS · Селлер` | `dfa5e05da9c96889` | 55694 |

## Fixtures And Roles

Fixtures созданы через локальный API только для подготовки данных. Все роли
логинились через реальную UI-форму: ввод email/password и click `Войти`.

QA suffix: `1786662287443`.

| Role | Email | Rights |
|---|---|---|
| FF admin | `qa-r02-final-admin-1786662287443@example.com` | admin |
| shipments/packaging staff | `qa-r02-final-shipments-1786662287443@example.com` | `mp_shipments=true`, `packaging=true`, `shift_lead=true` |
| inventory/cells staff | `qa-r02-final-inventory-1786662287443@example.com` | `cells=true`, `inventory=true` |
| reception staff | `qa-r02-final-reception-1786662287443@example.com` | `reception=true` |
| settings staff | `qa-r02-final-settings-1786662287443@example.com` | `settings=true` |
| seller | `qa-r02-final-seller-1786662287443@example.com` | seller id `393266e9-efbb-4634-9984-c853478c8efa` |

## Surface Guard Rerun

Direct `/seller/products` under FF token only:

| Role | Title | Topbar | Login form | Logout | Seller table | Denied text |
|---|---|---|---:|---:|---:|---|
| FF admin | `WMS · Фулфилмент` | `Портал ФФ ... администратор` | 0 | 1 | 0 | `Нет доступа к этому разделу.` |
| shipments/packaging staff | `WMS · Фулфилмент` | `Портал ФФ ... сотрудник` | 0 | 1 | 0 | `Нет доступа к этому разделу.` |
| inventory/cells staff | `WMS · Фулфилмент` | `Портал ФФ ... сотрудник` | 0 | 1 | 0 | `Нет доступа к этому разделу.` |
| reception staff | `WMS · Фулфилмент` | `Портал ФФ ... сотрудник` | 0 | 1 | 0 | `Нет доступа к этому разделу.` |
| settings staff | `WMS · Фулфилмент` | `Портал ФФ ... сотрудник` | 0 | 1 | 0 | `Нет доступа к этому разделу.` |

Product conclusion: previous wrong-surface blocker is gone. The denied state is
now inside FF shell, not seller shell and not seller login.

## R02 Matrix Sanity

### FF Admin

UI login as FF admin passed.

`/app/ff/settings` opened in FF shell. Payroll/admin-only controls were visible:

- `ff-staff-billing-month`: `1`;
- `ff-settings-users-panel`: `1`;
- visible labels: `Месяц расчёта`, `Ставка за ед.`, `Упаковано`, `Начислено`.

1280 nav check: 12 visible nav items, no clipped nav items, no nav overlaps.

### Shipments / FBS / Packaging Staff

Visible sidebar after UI login:
`Дашборд`, `Отгрузки`, `FBS`, `Упаковка`.

Hidden sidebar:
`Приёмка`, `Сортировка`, `Каталог и ячейки`, `Инвентаризация`, `Селлеры`,
`Настройки`.

Clicked route checks passed:

- `Отгрузки` -> `/app/ff/mp-shipments`, `ff-mp-shipments-page`;
- `FBS` -> `/app/ff/fbs`, `fbs-orders-screen`;
- `Упаковка` -> `/app/ff/packaging`, `ff-packaging-page`.

Direct allowed checks passed:

- `/app/ff/packaging/pending-marking` -> `ff-pending-marking-page`;
- `/app/ff/honest-sign/reprints` -> visible `Перепечатка КМ`.

Direct denied checks stayed in FF shell with human denied text, including
`/app/ff/sellers`, `/app/catalog/products`, `/app/ff/settings`,
`/app/ff/inventory`, `/app/ff/reception`, `/app/ff/sorting`, `/app/catalog`.

1280 nav check: 4 visible nav items, no clipped nav items, no nav overlaps.

### Inventory / Cells Staff

Visible sidebar after UI login:
`Дашборд`, `Каталог и ячейки`, `Инвентаризация`.

Hidden sidebar:
`Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`, `Селлеры`,
`Настройки`.

Clicked route checks passed:

- `Каталог и ячейки` -> `/app/ff/products`, `ff-products-list`;
- `Инвентаризация` -> `/app/ff/inventory`, `ff-inventory-snapshot-screen`.

Staff-safe catalog checks:

- `ff-products-create-seller`: `0`;
- `ff-products-import-tz`: `0`;
- `ff-products-create`: `0`;
- `ff-products-seller-filter`: `0`;
- packaging edit controls: `0`;
- `ff-products-error`: `0`;
- raw `forbidden`/`403` text in catalog body: `false`.

Inventory run check:

- `ff-inventory-snapshot-run` visible and disabled: `true`.

Direct denied checks stayed in FF shell with human denied text, including
`/app/ff/sellers`, `/app/catalog/products`, `/app/ff/mp-shipments`,
`/app/ff/fbs`, `/app/ff/packaging`, `/app/ff/reception`, `/app/ff/sorting`,
`/app/ff/settings`, `/app/ff/honest-sign/reprints`.

1280 nav check: 3 visible nav items, no clipped nav items, no nav overlaps.

### Reception Staff

Visible sidebar after UI login:
`Дашборд`, `Приёмка`, `Сортировка`.

Hidden sidebar:
`Отгрузки`, `FBS`, `Упаковка`, `Каталог и ячейки`, `Инвентаризация`,
`Селлеры`, `Настройки`.

Clicked route checks passed:

- `Приёмка` -> `/app/ff/reception`, `ff-reception-page`;
- `Сортировка` -> `/app/ff/sorting`, `ff-sorting-page`.

Direct denied checks stayed in FF shell with human denied text, including
`/app/ff/sellers`, `/app/catalog/products`, `/app/ff/mp-shipments`,
`/app/ff/fbs`, `/app/ff/packaging`, `/app/catalog`, `/app/ff/products`,
`/app/ff/inventory`, `/app/ff/settings`, `/app/ff/honest-sign/reprints`.

1280 nav check: 3 visible nav items, no clipped nav items, no nav overlaps.

### Settings Staff

Visible sidebar after UI login:
`Дашборд`, `Настройки`.

Hidden sidebar:
`Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`,
`Каталог и ячейки`, `Инвентаризация`, `Селлеры`.

Clicked route check passed:

- `Настройки` -> `/app/ff/settings`, `ff-settings-screen`.

Narrow settings checks:

- `ff-settings-users-panel`: `1`;
- `ff-staff-billing-month`: `0`;
- visible payroll labels `Месяц расчёта`, `Ставка за ед.`, `Упаковано`,
  `Начислено`: all absent;
- raw `forbidden`: `false`;
- raw `403`: `false`.

Direct denied checks stayed in FF shell with human denied text, including
`/app/ff/sellers`, `/app/catalog/products`, `/app/ff/reception`,
`/app/ff/sorting`, `/app/ff/mp-shipments`, `/app/ff/fbs`,
`/app/ff/packaging`, `/app/catalog`, `/app/ff/products`,
`/app/ff/inventory`, `/app/ff/honest-sign/reprints`.

1280 nav check: 2 visible nav items, no clipped nav items, no nav overlaps.

## Seller Portal Controls

With FF token only, `/seller/` stayed the seller entrypoint:

- URL: `http://127.0.0.1:5231/seller/`;
- title: `WMS · Селлер`;
- `login-form`: visible;
- `app-frame`: `0`;
- visible copy included `Вход для селлера`.

After actual seller UI login:

- direct `/seller/products` opened in SellerApp;
- title: `WMS · Селлер`;
- topbar contained `Портал селлера`;
- `seller-products-table`: visible;
- `login-form`: `0`;
- `ff-access-denied`: absent;
- `nav-seller-products`: visible.

## Final Gate Result

Browser-tested: `yes`.

R02 final live product browser QA verdict:

`PRODUCT_BROWSER_APPROVED`

No release-ready, staging-ready, deploy-ready, or production-ready claim is made
by this artifact.
