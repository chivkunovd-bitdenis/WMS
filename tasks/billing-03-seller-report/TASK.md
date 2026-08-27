# Волна 3: отчёт по селлерам

## 0. Как работать и открыть наряд

Работа выполняется только в постоянном worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826` на ветке
`codex/billing-module-20260826`. Волна зависит от принятого tip 2А
`89fec60d9b571bb38fd4d43fadc86f247f5a4239` и принятого/pushed tip 2Б
`797bf2e3007b92e2ce08aec58e27506a53cfcf90`. Перед первой правкой нужен
independent review этого пакета, затем открывается ровно один наряд:

```bash
python3 scripts/naryad.py new "Волна 3 модуля «Расчёты»: отчёт по селлерам на существующем /app/ff/billing" --lane обычная --files backend/app/api/billing.py,backend/app/services/billing_seller_report_service.py,backend/app/services/storage_measurement_service.py,backend/tests/test_billing_seller_report_api.py,backend/tests/test_billing_seller_report_service.py,backend/tests/test_billing_invoice_service.py,frontend/src/screens/ff/FfBillingScreen.tsx,frontend/src/screens/ff/FfBillingScreen.test.ts,frontend/tests-e2e/billing-seller-report.spec.ts,frontend/tests-e2e/billing-ledger.spec.ts,frontend/tests-e2e/billing-invoices.spec.ts,docs/evidence/billing-03-seller-report/SELLER-REPORT-PROOF.md,docs/evidence/20260827-volna-3-otchet-po-selleram/BILLING-SELLERS-1600.jpg,docs/evidence/20260827-volna-3-otchet-po-selleram/BILLING-SELLERS-FINANCE-OFF-1600.jpg,docs/evidence/20260827-volna-3-otchet-po-selleram/VERDICT.md
```

Это осознанно **без** `--screens`: `/app/ff/billing` отсутствует в
`frontend/screens.registry.json`, ему нельзя присваивать чужой S-ID. Все 15
путей выше — полная граница main-волны. Новая миграция, модель, маршрут,
`App.tsx` и legacy invoice/ledger service запрещены. Разрешены только два
соседних Playwright-файла из literal list и только для узкой регрессии §8;
другие соседние E2E не трогаются. Если наряд не открывается, статус —
`BLOCKED`; хук, его настройки и baseline обходить нельзя.

До main-наряда обязателен отдельный owner-approved shared prerequisite: в
текущем ui-kit нет generic Moscow date-only/range control и labelled controlled
switch. Это отдельная работа и commit, не расширение Wave 3:

```bash
python3 scripts/naryad.py new "Волна 3 «Расчёты»: общая UI-kit prerequisite для доступного date-range Москвы и switch представления" --lane обычная --files frontend/src/ui-kit/FormFields.tsx,frontend/src/ui-kit/FormFields.test.tsx,frontend/src/ui-kit/index.ts,frontend/src/ui-kit/UiKitShowcase.tsx
```

В уже существующую family `FormFields` допустимо добавить только
screen-agnostic `MoscowDateInput`, controlled `MoscowDateRangeInput` и labelled
controlled `PreferenceSwitch`: programmatic label/help/error,
disabled/loading, keyboard и date-order/max-range semantics обязательны. Нельзя
добавлять billing/seller/finance/tariff/invoice wording, props, styles, route,
screen-specific primitive или refactor legacy screen. После unit/type/ui_guard/
showcase proof, independent acceptance, отдельного commit/push prerequisite
закрывается `python3 scripts/naryad.py close`; только потом открывается
буквальная main-команда выше. Main imports the accepted exports but does not
edit those four ui-kit paths.

Порядок main-волны: тест-кейсы из `CASES.md` до product code; реализация; целевые тесты;
полный обязательный регресс; независимое review; живой браузер; evidence;
отдельный commit и push. Никаких production/deploy, секретов, глобальных
аудитов, ARCH, нового реестра экранов или начала Wave 4/5.

## 1. Цель и бизнес-результат

Администратор ФФ видит на уже существующем `/app/ff/billing`, какие услуги
оказаны каждому селлеру за точный московский период. Он может безопасно
переключить представление «Финансы», получить серверные итоги и открыть
постраничную детализацию с переходом к первоисточнику. Для хранения это одна
честная агрегированная строка за выбранный интервал, а не сумма месячных
документов.

Волна не выставляет счёт и не рассчитывает выплаты сотрудникам. Это
переходная, но полноценная поставка только зоны «Селлеры».

## 2. Дословные требования владельца из `TASK.FINAL.md`

> «Волна 3 — отчёт по селлерам: сводка, детализация, произвольный период,
> агрегированное хранение и оба режима “Финансы”.»

> «Сервер не возвращает ставки, суммы и другие денежные поля» при выключенных
> финансах.

> «Итоги и счётчики считаются сервером, а не складываются на фронте из
> загруженной страницы.»

> «Для каждого селлера и каждого выбранного периода в детализации находится
> ровно одна строка “Хранение”.»

> «Месячные `BillingLedgerEntry` услуги `storage_liter_day` не входят в новый
> отчёт селлеров».

Также обязательны: период до 366 дней и московский полуинтервал; быстрые
периоды; cursor-pagination; стабильная ссылка на документ; tenant/RBAC;
обратная совместимость legacy API; отдельные charge, reversal и net server
totals; token/fingerprint точного хранения и его устаревание.

## 3. Что уже существует и обязательно переиспользуется

- `FfBillingScreen` уже обслуживает маршрут `/app/ff/billing`; меняется только
  его содержимое. Маршрут, `App.tsx`, shell и соседние экраны не меняются.
- `OperationFact`/`OperationFactLine` Wave 2А — новая половина read-model;
  `BillingLedgerEntry` — legacy половина до cutover. Один факт не попадает в
  обе. Не ослаблять `uq_billing_ledger_source_event`.
- `BillingLedgerLine` и V2 tariff snapshot дают суммы/товар там, где они уже
  есть; legacy amount/rate и старые source snapshots не переписываются.
- `InventoryMovement`, `ProductDimensionEvent`, `Product`, `Warehouse` и
  `storage_measurement_service` — единственные входы интервального хранения.
  `StorageStatement` и месячные storage ledger остаются отдельным экраном и
  историей, без изменения и без чтения для новой строки.
- `DataTable`, `FilterBar`, `ScreenHeader`, `StatusChip`, `ErrorNotice`,
  `TableSkeletonBody`, `PrimaryAction` и другие уже имеющиеся ui-kit элементы
  используются как есть. Raw MUI table/filter/button/tab и новый primitive
  запрещены.

## 4. Нормативные и запрещённые входы

Приоритет: этот пакет, `tasks/billing-module-20260825/TASK.FINAL.md`, фактический
код 2А/2Б, затем `AGENTS.md`, `CLAUDE.md`, `docs/product/NARYAD_RU.md` и
`docs/product/UX_CANON_RU.md`. `docs/process/KANON_ZADACHI_RU.md` в checkout
отсутствует: требования из него не выдумываются.

Запрещено: отдельный FBS-report/вкладка; вторая детализация хранения;
товарные/дневные/складские строки хранения; денежные поля или денежные итоги в
finance-off API; подсчёт totals из страницы фронтом; выбор операций, checkbox,
«Выставить счёт», preview/print, V2 invoice tables и invoice writes (Wave 4);
вкладки «Выставленные счета» и «Сотрудники», staff earnings и employee API
(Wave 4/5); изменение legacy `/api/billing/ledger`, `/api/billing/invoices`,
их контрактов, print/cancel или автоматической задачи счетов.

Wave 3 implements the required read-only prior-invoice mark/count, but not
invoice selection or writes. It is deliberately available only for a
`legacy_billing` detail row that carries `billing_ledger_entry_id`. Current
legacy `BillingInvoice.lines[].documents[]` snapshots preserve exact ledger ID
in `documents[].id`; same-tenant/seller invoices are counted by distinct
`BillingInvoice.id` over that entry's complete charge/reversal chain. A
cancelled invoice still counts as prior issuance. Matching a number, date,
amount, seller or source text is forbidden. If any relevant old snapshot is
missing/malformed, outcome is `unknown`, never a fabricated zero. `OperationFact`
and synthetic storage are unknown. `BillingInvoiceV2Source`, selection,
preview/print and invoice writes remain Wave 4.

## 5. Точные модели, API, состояния и сценарии

### Read-model и период

Новый typed read-model живёт в `billing_seller_report_service.py`, но данных не
пишет. Он объединяет:

1. `OperationFact` после durable cutover;
2. legacy `BillingLedgerEntry` до cutover, исключая
   `service_code='storage_liter_day'`;
3. одну synthetic `storage` row, вычисленную отдельно, не как ledger entry.

Запрос принимает `date_from` и `date_to` как ISO date. Валидны
`date_to >= date_from`, `date_to - date_from <= 365` (то есть включительно не
более 366 календарных дней) и `date_to <= текущий московский календарный день`.
Последнее — безопасное явное правило: нельзя начислять будущее хранение.
Сервер возвращает 422 до SQL-записи; UI показывает ту же inline validation, но
сервер остаётся источником истины. Сервис переводит период в
`[date_from 00:00 Europe/Moscow, (date_to + 1) 00:00 Europe/Moscow)`; browser
timezone никогда не участвует. Invalid/overlong range — 422 до SQL-записи.

Ровно эти новые endpoints, все под `require_fulfillment_admin` и tenant scope:

- `GET /api/billing/seller-report/summary` — filters `date_from`, `date_to`,
  optional `seller_id`, `search`, `include_finance` (default `false`), server
  rows и global `totals`;
- `GET /api/billing/seller-report/sellers/{seller_id}/details` — те же period/
  finance filters, `limit` 1..100 (default 50) и opaque cursor;
  `seller_id` обязан принадлежать tenant, иначе 404 без раскрытия;
  ответ содержит first-page единственную `storage_row`, `entries`, `next_cursor`
  и server totals для всего detail filter.

Cursor содержит только signed/encoded stable key `(occurred_at,id,kind)` и
filters; сортировка `(occurred_at DESC, kind, id DESC)` не пропускает и не
повторяет строку при загрузке следующей страницы. Totals и summary всегда
делает SQL/service на полном scope, не UI. Pydantic response models и OpenAPI
tests обязательны.

`include_finance=false` сохраняет тот же состав sellers/operations/storage и
возвращает только physical fields: counts, quantity, service/result/source.
Ключей `rate_kopecks`, `amount_kopecks`, `accrued_*`, `unpriced_count`,
`reversal_total_kopecks`, `net_total_kopecks` и денежных значений storage в
JSON нет вообще. При `true` добавляются только integer kopecks fields: rate,
amount, gross/reversal/net totals, `unpriced_count`; frontend показывает
kopecks один раз через существующий formatter. Старые ledger/invoice endpoints
не меняются: отсутствие нового параметра в них продолжает возвращать их
сегодняшний денежный контракт.

Summary row: seller stable ID/name, `operation_count`, `item_quantity`,
`not_billable_count`, `details_target`. Finance-on добавляет
`unpriced_count`, gross/reversal/net kopecks. Page totals имеют те же поля;
счётчики reversal и чистый итог отдаются сервером отдельно. Operation detail:
occurred Moscow time, service, physical quantity (для legacy document-unit
unknown quantity — `null`, UI «—»), result (`completed`, `reversed`,
`not_billable`, `unpriced` только finance-on), product/SKU snapshots when
known, stable `source_type`, `source_id` и explicit `source_target` supplied
by server. UI opens only supported target; не строит route из guessed ID.
Finance-on detail has `billing_ledger_entry_id` and
`invoice_history={state:"known",count:N}` only for a `legacy_billing` row with
an exact valid snapshot chain. `N` counts distinct same-tenant/seller legacy
invoices, including cancelled invoices. A legacy row with a missing/malformed
snapshot anywhere in the same tenant/seller snapshot corpus, every
`OperationFact`, and storage use
`invoice_history={state:"unknown"}`; no count is emitted. Finance-off emits
neither `billing_ledger_entry_id` nor `invoice_history`.

### Единственная строка хранения

`storage_row` строится для конкретного tenant+seller+exact interval из
операционных `InventoryMovement`, historical `ProductDimensionEvent` и
day-effective legacy `BillingTariffVersion(storage_liter_day)`. Повторно
используется segment algorithm из `storage_measurement_service`: movement and
dimension boundaries split holdings; litres-days/amount are summed over the
actual interval and all operational warehouses/products. Missing dimension for
any held product produces `status="missing_dimensions"`, no finance amount and
an explanatory UI state. Строка не получает document link и не предлагает
drilldown.

На первой странице details server returns exactly one object:
`kind="storage"`, selected dates, total `liter_days`, status, and finance-on
`amount_kopecks`; later cursor pages return `storage_row: null`. Thus UI renders
one row once, before/alongside paginated operational entries. Existing monthly
statement/ledger is never summed or changed.

The server computes a deterministic SHA-256 fingerprint over tenant/seller,
Moscow bounds, ordered movement IDs+timestamps+deltas, effective dimension
events/volumes, selected tariff IDs+intervals+rates, liter-days and amount. It
signs canonical `{version, fingerprint, payload}` by HMAC-SHA256 using a
domain-separated key derived from existing `settings.jwt_secret_key`, then
returns the opaque base64url `calculation_token`; no DB row or new secret is
written. Wave 3 only previews this token. Wave 4 must verify HMAC and recompute
before invoice write: a changed movement/dimension/tariff yields named 409
`storage_calculation_stale` and requires refresh. The token is tenant- and
seller-bound; foreign/replayed/tampered token is invalid. This is backward
compatible because no old storage document or endpoint changes.

### Экран и states

Existing charges tab is renamed to **«Селлеры»**. Legacy «Счета» remains
present and unmodified until Wave 4; no «Сотрудники» tab or placeholder in this
wave. Filters: seller/search, reusable Moscow date range, fast today/7/30
days/current month/previous month, and one Finance switch persisted in `localStorage` by
`tenant_id:user_id:billing:sellers:finance`. The user can choose any valid
range; frontend prevalidates but server is authoritative.

Finance-off has no invoice-history column. Finance-on remains view-only: it
adds fixed column «Счёт выставлялся», with known count 0 as `—`, known positive
count as unobtrusive `✓` and its number (including 1), and unknown as «Нет
данных о старом счёте» with Tooltip. It uses existing text/tooltip ui-kit
composition, not a new chip/control; it has neither select checkbox nor
«Выставить счёт».

Seller summary is `DataTable size=small` with fixed columns: Seller,
Operations, Items, Not billable, Show operations; Finance-on adds Unpriced and
Accrued. At most four `ReportMetricStrip` values: sellers, operations, items,
and accrued only finance-on. Clicking a seller opens a separate detail block
under the summary, not a custom expandable table. It keeps last successful
summary on detail failure, aborts stale fetch on filter/seller change, uses
skeletons for tables, `ErrorNotice` for errors, actionable empty text, and
Tooltip explanation for unavailable source/missing dimensions. At 1600px each
table follows existing ui-kit fixed columns; any horizontal overflow is inside
its real `TableContainer` only.

## 6. Границы файлов, зависимости и порядок

The literal main `--files` list in §0 is exhaustive after the separate ui-kit
prerequisite closes. Only a new report service is
allowed under `backend/app`; it must not turn `billing.py` legacy handlers into
the report implementation. `storage_measurement_service.py` may receive only
an extracted/reused pure interval helper with equivalent monthly behaviour;
no rebuild, statement, storage pricing or monthly document semantics change.

No migration is planned: report reads existing durable rows and token is signed
not stored. If implementation discovers that an extra persisted field/index or
any unlisted path is necessary, stop `BLOCKED` and amend/review this TASK before
editing it. Do not silently widen the NARYAD.

## 7. Что запрещено и что остаётся неизменным

The existing Storage page, stock/movement report, tariff matrix, operational
writers, 2A recovery/cutover, ledger uniqueness, legacy invoice list/open/
cancel/print/form, RBAC roles and `/app/ff/billing` route remain intact. There
is no finance data for staff, shift lead or seller. No custom UI primitives,
new design, raw table, route, export, seller portal, automatic invoice, FBS
screen, data backfill, delete or rewrite of historical rows.

## 8. Тесты, гейты, PostgreSQL и браузер

Implement `CASES.md` before code. Required targeted commands:

```bash
cd backend && uv run pytest tests/test_billing_seller_report_service.py tests/test_billing_seller_report_api.py tests/test_billing_invoice_service.py -q
cd frontend && npm run test:unit -- FfBillingScreen.test.ts
cd frontend && npx playwright test tests-e2e/billing-seller-report.spec.ts tests-e2e/billing-ledger.spec.ts tests-e2e/billing-invoices.spec.ts
```

Then mandatory gates, all to exit code 0: `cd backend && uv run ruff check .`,
`cd backend && uv run mypy .`, full `cd backend && uv run pytest`,
`python3 scripts/ci/back_guard.py`, `python3 scripts/ci/check_migrations.py`,
`cd frontend && npm run test:unit`, `cd frontend && npx tsc --noEmit -p
tsconfig.app.json`, `cd frontend && npm run build`, `python3
scripts/ui/ui_guard.py`, targeted Playwright and both named legacy regressions.

`billing-ledger.spec.ts` may replace its stale charges/performer DOM cases with
contract-aligned Sellers DOM regression (period, finance-off omission,
finance-on and seller detail). This is a frontend-only screen assertion;
backward compatibility of legacy `/api/billing/ledger` stays covered by backend
API tests and is not removed. `billing-invoices.spec.ts` may replace or move
**only** these two stale non-invoice charges-zone cases: kopecks display
(line 30) and `billing charge tariff issue targets tariff settings` (line 119).
They move into seller-report coverage or an invoice-line money assertion. Its
true invoice-tab list/columns, open, source snapshots, print, cancel and error
regressions remain unchanged. No other scenario in either file may be deleted,
weakened or repurposed.

At least one seller report uses real test DB/server aggregation, not mocked API;
also run a disposable local PostgreSQL proof of tenant isolation, 366-day
boundary, cursor totals and exact three-day storage interval/fingerprint stale
case. No migration is expected; `check_migrations` and single-head check prove
that this statement stays true. Separate Terra ui-critic and live-browser judge
inspect 1600px finance-off/on, loading/error/empty, one storage row and source
links. Invoice print and employee browser evidence are explicitly deferred.

## 9. Отчёт, доказательства, commit и push

Evidence lives only at the three paths listed in §0. `SELLER-REPORT-PROOF.md`
records commands, duration/exit code, test DB aggregation/SQL result, PostgreSQL
proof, token stale proof, and review verdict. Browser folder contains 1600px
normal finance-on/off screenshots, invariants/ui_guard output and `VERDICT.md`.

Final report format:

```text
Полоса: обычная
Экран: /app/ff/billing (unregistered; BILLING-SCREEN.md)
Стадия: Wave 3 seller report
Статус: <BLOCKED | готово в ветке | залито на staging>
Base SHA: 797bf2e3007b92e2ce08aec58e27506a53cfcf90
Commit: <SHA>
Доказательства: <paths>
Раунд правок: <0|1|2>
Блокеры: <нет|точно>
```

Only after every gate/review/browser proof: one Wave-3 commit and push. Wave 4
starts from that verified SHA and owns selection, V2 invoice-source writes,
preview/print and the invoice tab; Wave 5 owns employees. Wave 3's legacy
invoice-history mark/count remains read-only and does not block repeat issuance.
