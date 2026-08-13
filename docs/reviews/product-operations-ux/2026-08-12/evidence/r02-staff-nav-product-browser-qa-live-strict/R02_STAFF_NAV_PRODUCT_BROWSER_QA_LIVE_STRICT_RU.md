# R02 Staff Navigation Product Browser QA Live Strict

Дата: 2026-08-14.

Роль: STRICT LIVE Product Browser QA Agent по R02/F12/F14 staff navigation/direct-route parity.

Рабочий Git-root:
`/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Код backend/frontend, staging, production, Railway и secrets не трогались.
Проверка выполнена только на локальном live UI.

## Verdict

`PRODUCT_REWORK_REQUIRED`.

Причина не в основном FF staff sidebar: он прошел live browser проверку. Причина
в отдельном требовании про unrelated seller routes. После входа FF staff через
UI прямой переход на `/seller/products` показывает seller login screen
`WMS · Портал селлера / Вход для селлера`, а не человеческий отказ
`Нет доступа к этому разделу`. Это ровно тот класс поведения, который был
запрещен в задаче: не login/wrong app, а denied.

Все FF-shell direct routes из R02, включая `/app/catalog/products` и
`/app/ff/sellers`, закрываются корректно через `ff-access-denied` с текстом
`Нет доступа к этому разделу.`. Поэтому rework узкий: normalise seller-portal
direct-route handling for FF staff, не раздувая меню и не ломая прошедший FF
parity.

## Browser Evidence

Browser used: `yes`.

Поверхность: Codex In-app Browser / `tab.playwright`.

Локальные URL и порты:

- frontend: `http://127.0.0.1:5198/`;
- backend: `http://127.0.0.1:18152/`;
- DB: `backend/qa-r02-live-strict-1786660000.db`;
- viewport: `1280x900`.

Финальный live evidence:

- raw JSON: `/tmp/r02-staff-nav-live-browser-evidence-v3.json`;
- screenshots dir: `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3`;
- fixture suffix: `1786657193291`.

Роли переключались через реальный UI: `Выйти` -> login form -> ввод email и
пароля -> click `Войти` -> видимый `app-frame`. Первый automation-прогон был
отброшен как невалидный для verdict, потому что не дошел до staff экранов; этот
artifact основан на финальном прогоне `v3`.

## Fixtures

FF admin:

- `qa-r02-live-admin-1786657193291@example.com`.

Main staff roles:

- shipments/packaging:
  `mp_shipments=true`, `packaging=true`, `shift_lead=true`;
- inventory/cells:
  `cells=true`, `inventory=true`;
- reception:
  `reception=true`;
- settings:
  `settings=true`.

Permission split spot-check roles:

- mp-only:
  `mp_shipments=true`;
- packaging-only:
  `packaging=true`;
- shift-lead-only:
  `shift_lead=true`.

## FF Admin

UI login as FF admin passed.

Click `Настройки` opened `/app/ff/settings` and visible admin settings surface.
Admin settings showed packaging payroll/billing controls:

- `Месяц расчёта`: visible;
- `Ставка за ед., ₽`: visible;
- `Упаковано, шт`: visible;
- `Начислено, ₽`: visible;
- staff users panel: visible.

Screenshot:
`/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/ff-admin-settings-payroll-billing.png`.

## Shipments / Packaging Staff

Sidebar after UI login:

- visible: `Дашборд`, `Отгрузки`, `FBS`, `Упаковка`;
- not visible: `Приёмка`, `Сортировка`, `Каталог и ячейки`,
  `Инвентаризация`, `Селлеры`, admin `Каталог`, `Честный знак`, `Настройки`.

Clicked sidebar routes:

- `Отгрузки` -> `/app/ff/mp-shipments`, screen `ff-mp-shipments-page`;
- `FBS` -> `/app/ff/fbs`, screen `fbs-orders-screen`;
- `Упаковка` -> `/app/ff/packaging`, screen `ff-packaging-page`.

Direct allowed routes opened:

- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/ff/packaging/pending-marking`;
- `/app/ff/honest-sign/reprints`.

Admin-only FBS actions stayed hidden for staff:

- `fbs-orders-sync-wb`: `0`;
- `fbs-nav-stock-sync`: `0`.

Direct denied app routes passed with `Нет доступа к этому разделу.`:

- `/app/ff/fbs/stock-sync`;
- `/app/ff/reception`;
- `/app/ff/sorting`;
- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`;
- `/app/ff/settings`;
- `/app/ff/sellers`;
- `/app/catalog/products`.

Failure:

- `/seller/products` opened seller login instead of access denied.

Screenshots:

- sidebar:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/shipments-packaging-sidebar.png`;
- denied app route:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/shipments-packaging-denied-app-ff-fbs-stock-sync.png`.

## Inventory / Cells Staff

Sidebar after UI login:

- visible: `Дашборд`, `Каталог и ячейки`, `Инвентаризация`;
- not visible: `Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`,
  `Селлеры`, admin `Каталог`, `Честный знак`, `Настройки`.

Clicked sidebar routes:

- `Каталог и ячейки` -> `/app/ff/products`, screen `ff-products-list`;
- `Инвентаризация` -> `/app/ff/inventory`, screen
  `ff-inventory-snapshot-screen`.

Direct allowed routes opened:

- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`.

Staff-safe catalog checks:

- create seller action: `0`;
- import TZ action: `0`;
- create product action: `0`;
- seller filter: `0`;
- packaging edit controls: `0`.

Inventory run check:

- `ff-inventory-snapshot-run`: visible;
- enabled: `false`.

Direct denied app routes passed with `Нет доступа к этому разделу.`:

- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/ff/reception`;
- `/app/ff/sorting`;
- `/app/ff/settings`;
- `/app/ff/sellers`;
- `/app/catalog/products`;
- `/app/ff/honest-sign/reprints`.

Failure:

- `/seller/products` opened seller login instead of access denied.

Screenshots:

- sidebar:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/inventory-cells-sidebar.png`;
- denied app route:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/inventory-cells-denied-app-ff-mp-shipments.png`.

## Reception Staff

Sidebar after UI login:

- visible: `Дашборд`, `Приёмка`, `Сортировка`;
- not visible: `Отгрузки`, `FBS`, `Упаковка`, `Каталог и ячейки`,
  `Инвентаризация`, `Селлеры`, admin `Каталог`, `Честный знак`, `Настройки`.

Clicked sidebar routes:

- `Приёмка` -> `/app/ff/reception`, screen `ff-reception-page`;
- `Сортировка` -> `/app/ff/sorting`, screen `ff-sorting-page`.

Direct allowed routes opened:

- `/app/ff/reception`;
- `/app/ff/sorting`.

Direct denied app routes passed with `Нет доступа к этому разделу.`:

- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`;
- `/app/ff/settings`;
- `/app/ff/sellers`;
- `/app/catalog/products`;
- `/app/ff/honest-sign/reprints`.

Failure:

- `/seller/products` opened seller login instead of access denied.

Screenshots:

- sidebar:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/reception-sidebar.png`;
- denied app route:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/reception-denied-app-ff-mp-shipments.png`.

## Settings Staff

Sidebar after UI login:

- visible: `Дашборд`, `Настройки`;
- not visible: `Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`,
  `Каталог и ячейки`, `Инвентаризация`, `Селлеры`, admin `Каталог`,
  `Честный знак`.

Clicked sidebar route:

- `Настройки` -> `/app/ff/settings`, screen `ff-settings-screen`.

Settings-staff payroll/billing checks:

- `ff-staff-billing-month`: `0`;
- `Месяц расчёта`: `0`;
- `Ставка за ед.`: `0`;
- `Упаковано`: `0`;
- `Начислено`: `0`;
- raw permission labels / raw forbidden / `403`: not visible.

Direct allowed route opened:

- `/app/ff/settings`.

Direct denied app routes passed with `Нет доступа к этому разделу.`:

- `/app/ff/reception`;
- `/app/ff/sorting`;
- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`;
- `/app/ff/sellers`;
- `/app/catalog/products`;
- `/app/ff/honest-sign/reprints`.

Failure:

- `/seller/products` opened seller login instead of access denied.

Screenshots:

- sidebar:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/settings-sidebar.png`;
- denied app route:
  `/tmp/r02-staff-nav-live-screenshots-1786657193291-v3/settings-denied-app-ff-reception.png`.

## Permission Split Spot Checks

`mp-only` staff:

- sidebar: `Дашборд`, `Отгрузки`;
- `/app/ff/mp-shipments` opened;
- `/app/ff/fbs`, `/app/ff/packaging`,
  `/app/ff/honest-sign/reprints` denied.

`packaging-only` staff:

- sidebar: `Дашборд`, `FBS`, `Упаковка`;
- `/app/ff/fbs` and `/app/ff/packaging` opened;
- `/app/ff/mp-shipments` and `/app/ff/honest-sign/reprints` denied.

`shift-lead-only` staff:

- sidebar: `Дашборд`;
- `/app/ff/honest-sign/reprints` opened;
- `/app/ff/mp-shipments`, `/app/ff/fbs`, `/app/ff/packaging` denied.

Spot-check failures: none.

## 1280 Layout Check

Viewport was forced to `1280x900`.

Main staff menus had no horizontal overflow and no nav-item overlap:

- shipments/packaging: 4 nav items, overflow `false`, overlaps `[]`;
- inventory/cells: 3 nav items, overflow `false`, overlaps `[]`;
- reception: 3 nav items, overflow `false`, overlaps `[]`;
- settings: 2 nav items, overflow `false`, overlaps `[]`;
- FF admin: 12 nav items, overflow `false`, overlaps `[]`.

Product conclusion: staff navigation is short and not overloaded at 1280.

## Blocking Rework

Fix `/seller/products` and equivalent seller-portal direct routes for a logged-in
FF staff/admin browser context so they do not show seller login or wrong-portal
copy. The product behavior requested for R02 is a human denied state:
`Нет доступа к этому разделу`.

Do not use this artifact as a release-ready statement. After the rework, rerun
STRICT LIVE Product Browser QA for the seller-route denial plus a smoke pass of
the already passing FF staff sidebar/direct-route matrix.
