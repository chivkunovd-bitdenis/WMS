# R02 Staff Navigation Product Browser QA Rerun Live Strict

Дата: 2026-08-14.

Роль: STRICT LIVE Product Browser QA Agent по R02 rerun after cross-app guard fix.

Рабочий Git-root:
`/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.

Код backend/frontend не редактировался. Production, staging, Railway, внешние
кабинеты и secrets не открывались и не трогались. Проверка выполнена только на
локальном live UI.

## Verdict

`PRODUCT_REWORK_REQUIRED`.

Коротко: старый blocker частично закрыт, но не полностью. Для FF admin/staff
прямой переход на `/seller/products` больше не показывает seller login:
виден человеческий текст `Нет доступа к этому разделу.` и `login-form=0`.
Но финальный экран остаётся вне FF-shell: `title=WMS · Селлер`,
`app-frame=false`, `app-topbar=""`, `logout=false`. Это всё ещё выглядит как
seller app / wrong app, только с denied-заглушкой. Требование rerun было строже:
FF staff direct `/seller/products` must show `Нет доступа к этому разделу`,
not seller login/wrong app.

Остальная ключевая R02-матрица в live browser прошла: staff sidebar/direct FF
routes, `/app/catalog/products`, `/app/ff/sellers`, payroll admin-only,
inventory ограничения, `/seller/` entrypoint и seller-token `/seller/products`.

## Browser Evidence

Browser used: `yes`.

Поверхность: Codex Browser / `browser-client` / `tab.playwright`.

Локальные URL и порты:

- frontend: `http://127.0.0.1:5208/`;
- backend: `http://127.0.0.1:18172/`;
- DB: `/tmp/wms-r02-rerun-live-strict-1786666400.db`;
- viewport: `1280x720`;
- scratch JSON was used only during the run and was not kept as a deliverable.

Скриншоты снимались живым браузером как byte snapshots. Чтобы сохранить
требование "exactly one artifact", отдельные screenshot-файлы в repo не
создавались; ниже зафиксированы label, URL, title, sha256 prefix и размер:

| Label | URL | Title | SHA256 prefix | Bytes |
|---|---|---|---|---:|
| admin-settings-payroll | `/app/ff/settings` | `WMS · Фулфилмент` | `5353e706d10e3583` | 70335 |
| admin-seller-products-denied | `/seller/products` | `WMS · Селлер` | `9214e8211c0f9bd3` | 8723 |
| shipments-sidebar | `/app/ff/dashboard` | `WMS · Фулфилмент` | `d03f9284754cd7f6` | 68200 |
| shipments-seller-products-denied | `/seller/products` | `WMS · Селлер` | `9214e8211c0f9bd3` | 8723 |
| inventory-sidebar | `/app/ff/dashboard` | `WMS · Фулфилмент` | `0b0ae96b893ad977` | 68818 |
| inventory-seller-products-denied | `/seller/products` | `WMS · Селлер` | `9214e8211c0f9bd3` | 8723 |
| reception-sidebar | `/app/ff/dashboard` | `WMS · Фулфилмент` | `05d83d19c6ab2533` | 68094 |
| reception-seller-products-denied | `/seller/products` | `WMS · Селлер` | `9214e8211c0f9bd3` | 8723 |
| settings-sidebar | `/app/ff/dashboard` | `WMS · Фулфилмент` | `beff2169e00cc38b` | 67109 |
| settings-seller-products-denied | `/seller/products` | `WMS · Селлер` | `9214e8211c0f9bd3` | 8723 |
| seller-home-login-entrypoint | `/seller/` | `WMS · Селлер` | `c58a334f6c478080` | 28789 |
| seller-products-with-seller-token | `/seller/products` | `WMS · Селлер` | `a8c36ad5027b11da` | 55604 |

## Fixtures

Fixtures созданы через локальный API, затем роли логинились через реальную UI
форму `login-form`: ввод email/password и click `Войти`.

Пароль для всех QA-аккаунтов: `password123`.

- FF admin: `qa-r02-rerun-admin-1786666400@example.com`;
- shipments/packaging staff:
  `qa-r02-rerun-shipments-1786666400@example.com`,
  rights `mp_shipments=true`, `packaging=true`, `shift_lead=true`;
- inventory/cells staff:
  `qa-r02-rerun-inventory-1786666400@example.com`,
  rights `cells=true`, `inventory=true`;
- reception staff:
  `qa-r02-rerun-reception-1786666400@example.com`,
  rights `reception=true`;
- settings staff:
  `qa-r02-rerun-settings-1786666400@example.com`,
  rights `settings=true`;
- split spot-check roles:
  `mp-only`, `packaging-only`, `shift-lead-only`;
- seller:
  `qa-r02-rerun-seller-1786666400@example.com`,
  seller id `b42d1682-02aa-4398-8365-8d2dabedcc5e`.

## Cross-App Guard Rerun

FF contexts checked: admin, shipments/packaging, inventory/cells, reception,
settings.

For each FF context, direct `/seller/products` result:

- URL: `http://127.0.0.1:5208/seller/products`;
- visible text: `Нет доступа / Нет доступа к этому разделу.`;
- `login-form`: `0`;
- `app-frame`: `false`;
- `app-topbar`: empty;
- `logout`: `false`;
- title: `WMS · Селлер`.

Product conclusion: not seller login anymore, but still wrong shell/app. This
is the blocking rework.

## FF Admin

UI login as FF admin passed.

Clicked `Настройки` opened `/app/ff/settings`.

Payroll/admin-only controls visible:

- `ff-staff-billing-month`: `1`;
- `Месяц расчёта`: visible;
- `Ставка за ед.`: visible;
- `Упаковано`: visible;
- `Начислено`: visible;
- `ff-settings-users-panel`: visible.

At 1280px, admin nav had 12 items and no overlaps or clipped nav item text.
The page had document `scrollWidth=1373` because settings content is wider than
the viewport, but the nav drawer itself was not overloaded.

## Shipments / FBS / Packaging Staff

Sidebar after UI login:

- visible: `Дашборд`, `Отгрузки`, `FBS`, `Упаковка`;
- hidden: `Приёмка`, `Сортировка`, `Каталог и ячейки`,
  `Инвентаризация`, `Селлеры`, `Настройки`.

Clicked nav routes passed:

- `Отгрузки` -> `/app/ff/mp-shipments`, `ff-mp-shipments-page`;
- `FBS` -> `/app/ff/fbs`, `fbs-orders-screen`;
- `Упаковка` -> `/app/ff/packaging`, `ff-packaging-page`.

Direct allowed routes passed:

- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/ff/packaging/pending-marking`;
- `/app/ff/honest-sign/reprints` with visible `Перепечатка КМ`.

Direct denied FF routes passed in FF shell with human denied text:

- `/app/ff/fbs/stock-sync`;
- `/app/ff/reception`;
- `/app/ff/sorting`;
- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`;
- `/app/ff/settings`;
- `/app/ff/sellers`;
- `/app/catalog/products`.

1280 layout: viewport `1280x720`, nav items `4`, no nav overflow, no overlaps.

## Inventory / Cells Staff

Sidebar after UI login:

- visible: `Дашборд`, `Каталог и ячейки`, `Инвентаризация`;
- hidden: `Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`,
  `Селлеры`, `Настройки`.

Clicked nav routes passed:

- `Каталог и ячейки` -> `/app/ff/products`, `ff-products-list`;
- `Инвентаризация` -> `/app/ff/inventory`,
  `ff-inventory-snapshot-screen`.

Direct allowed routes passed:

- `/app/catalog`;
- `/app/ff/products`;
- `/app/ff/inventory`.

Staff-safe catalog checks:

- create seller action: `0`;
- import TZ action: `0`;
- create product action: `0`;
- seller filter: `0`;
- packaging edit controls: `0`;
- products error: `0`.

Inventory run check:

- `ff-inventory-snapshot-run`: visible;
- enabled: `false`.

Direct denied FF routes passed in FF shell with human denied text:

- `/app/ff/mp-shipments`;
- `/app/ff/fbs`;
- `/app/ff/packaging`;
- `/app/ff/reception`;
- `/app/ff/sorting`;
- `/app/ff/settings`;
- `/app/ff/sellers`;
- `/app/catalog/products`;
- `/app/ff/honest-sign/reprints`.

1280 layout: viewport `1280x720`, nav items `3`, no nav overflow, no overlaps.

## Reception Staff

Sidebar after UI login:

- visible: `Дашборд`, `Приёмка`, `Сортировка`;
- hidden: `Отгрузки`, `FBS`, `Упаковка`, `Каталог и ячейки`,
  `Инвентаризация`, `Селлеры`, `Настройки`.

Clicked nav routes passed:

- `Приёмка` -> `/app/ff/reception`, `ff-reception-page`;
- `Сортировка` -> `/app/ff/sorting`, `ff-sorting-page`.

Direct allowed routes passed:

- `/app/ff/reception`;
- `/app/ff/sorting`.

Direct denied FF routes passed in FF shell with human denied text:

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

1280 layout: viewport `1280x720`, nav items `3`, no nav overflow, no overlaps.

## Settings Staff

Sidebar after UI login:

- visible: `Дашборд`, `Настройки`;
- hidden: `Отгрузки`, `FBS`, `Упаковка`, `Приёмка`, `Сортировка`,
  `Каталог и ячейки`, `Инвентаризация`, `Селлеры`.

Clicked/direct allowed route passed:

- `Настройки` -> `/app/ff/settings`, `ff-settings-screen`;
- `/app/ff/settings` direct -> `ff-settings-screen`.

Settings-staff narrow check:

- `ff-settings-users-panel`: visible;
- `ff-staff-billing-month`: `0`;
- `Месяц расчёта`: `0`;
- `Ставка за ед.`: `0`;
- `Упаковано`: `0`;
- `Начислено`: `0`;
- raw `forbidden`: `0`;
- raw `403`: `0`.

Direct denied FF routes passed in FF shell with human denied text:

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

1280 layout: viewport `1280x720`, nav items `2`, no nav overflow, no overlaps.

## Permission Split Spot Checks

`mp-only` staff:

- `/app/ff/mp-shipments` opened `ff-mp-shipments-page`;
- `/app/ff/fbs`, `/app/ff/packaging`,
  `/app/ff/honest-sign/reprints` denied in FF shell.

`packaging-only` staff:

- `/app/ff/fbs` opened `fbs-orders-screen`;
- `/app/ff/mp-shipments` and `/app/ff/honest-sign/reprints` denied in FF shell.

`shift-lead-only` staff:

- `/app/ff/honest-sign/reprints` opened with visible `Перепечатка КМ`;
- `/app/ff/mp-shipments`, `/app/ff/fbs`, `/app/ff/packaging`
  denied in FF shell.

Spot-check failures: none.

## Seller Portal Control Checks

Before seller login, while FF staff session existed and no seller login had
been performed in this run, `/seller/` remained the seller entrypoint:

- URL: `http://127.0.0.1:5208/seller/`;
- title: `WMS · Селлер`;
- `login-form`: visible;
- visible copy: `WMS · Портал селлера`, `Вход для селлера`.

After actual seller UI login:

- `/seller/products` opened in SellerApp;
- `seller-products-table`: visible;
- topbar: `Портал селлера`;
- `login-form`: `0`;
- `ff-access-denied`: `0`;
- seller nav: `Документы`, `Товары`, `Честный знак`, `Настройки`;
- 1280 layout: no nav overflow, no overlaps.

## Blocking Rework

Fix the final visual surface for FF-token/no-seller-token direct
`/seller/products` and equivalent seller deep routes. It must land in the FF
app shell, with visible FF portal context/topbar/logout, not as a standalone
seller-title page. The current state is better than the previous seller-login
failure, but it still violates the "not wrong app" half of the rerun contract.

Do not use this artifact as a release-ready statement.
