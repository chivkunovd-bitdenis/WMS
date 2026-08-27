# Волна 4: счета из операций и ручные счета

## 0. Статус, границы и порядок старта

Это исполняемый контракт для **Волны 4** модуля «Расчёты». Он не разрешает
начинать разработку до независимого review этого файла и до принятия Волны 3
живым браузером. Нормативный источник продукта —
`tasks/billing-module-20260825/TASK.FINAL.md`, разделы 7, 8, 11.3 и сценарии
14–30. Wave 3 (`tasks/billing-03-seller-report/TASK.md`) — обязательный
read-model, в том числе его signed `storage_calculation_token`.

Работа выполняется только в постоянном worktree
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826`, ветка
`codex/billing-module-20260826`. Это обычная полоса, существующий экран
`/app/ff/billing` не имеет S-ID в реестре. Перед первой правкой автор сверяет
принятый/опубликованный tip Wave 3, читает весь этот пакет и открывает ровно
один наряд. Нельзя закрывать или подменять активный наряд другой волны.

После принятия Wave 3 literal-команда наряда обязательна и исполнима именно
так (одна строка, без placeholder). `/app/ff/billing` отсутствует в screen
registry, поэтому команда задаёт полную узкую границу только через список
файлов:

```bash
python3 scripts/naryad.py new "Волна 4 модуля «Расчёты»: счета на существующем /app/ff/billing" --lane обычная --files backend/app/models/billing.py,backend/app/models/operation_fact.py,backend/app/models/__init__.py,backend/app/services/billing_invoice_v2_service.py,backend/app/services/billing_invoice_service.py,backend/app/services/billing_seller_report_service.py,backend/app/api/billing.py,backend/app/api/billing_invoice_v2_schemas.py,backend/app/tasks/billing_tasks.py,backend/app/celery_app.py,backend/alembic/versions/20260827_0114_billing_invoice_v2.py,backend/tests/test_billing_invoice_v2_service.py,backend/tests/test_billing_invoice_v2_api.py,backend/tests/test_billing_invoice_service.py,backend/tests/test_billing_invoice_api.py,backend/tests/test_billing_seller_report_service.py,backend/tests/test_billing_tasks.py,frontend/src/screens/ff/FfBillingScreen.tsx,frontend/src/screens/ff/FfBillingScreen.test.ts,frontend/tests-e2e/billing-invoice-v2.spec.ts,frontend/tests-e2e/billing-seller-report.spec.ts,frontend/tests-e2e/billing-invoices.spec.ts,docs/evidence/billing-04-invoices/INVOICE-V2-PROOF.md,docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PREVIEW-1600.jpg,docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PREVIEW-1280.jpg,docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PRINT-1600.jpg,docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/VERDICT.md
```

Фактическая allowlist — ровно все пути из команды; пути чужих registry-экранов
в неё не входят и запрещены. Если путь понадобился после открытия наряда,
работа останавливается на узком amendment, а не расширяет границу молча.
Детерминированный evidence path для этого текста наряда —
`docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/`.

`frontend/src/ui-kit/**` не входит в Wave 4. Перед кодом разработчик обязан
зафиксировать audit нужных уже существующих primitives: labelled checkbox,
modal/dialog с фокусом и закрытием по Escape, доступное денежное поле,
`TextInput`, `NumberInput`, `SelectInput`, `DataTable`, `FilterBar`,
`ActionGroup`, `PrimaryAction`, `SecondaryAction`, `DangerAction`,
`PrintAction`, `MoneyCell`, `TextCell`, `StatusChip`, `ErrorNotice` и
`TableSkeletonBody`. Если хотя бы одного общего primitive нет, локальный MUI,
самодельная кнопка, checkbox, select, таблица или модалка запрещены: текущий
наряд закрывается, отдельный узкий shared UI-kit prerequisite проходит свой
наряд, тесты, независимое принятие, commit/push, и только затем Wave 4
открывается заново. Это не разрешение менять соседние экраны или переписывать
унаследованную зону `/app/ff/billing`.

Никаких production/staging, секретов, смены маршрута, `App.tsx`, screen
registry, Wave 5, тарифной матрицы, исторического storage UI или массового
рефакторинга. Миграция только добавляющая, с единственным parent
`20260827_0113`; опубликованные 0110–0113 не переписываются.

## 1. Цель и явные нецели

Администратор ФФ при включённых финансах выбирает честно рассчитанные услуги
одного селлера за уже открытый произвольный московский период либо создаёт
ручной счёт. До сохранения он видит ровно тот документ, который будет
сохранён; после сохранения может открыть, распечатать, отменить и повторно
выставить счёт. История не теряет старые месячные счета.

Не входит: автоматическое формирование счетов, отправка счета клиенту,
оплата, PDF-файловое хранилище, бухгалтерская проводка, перерасчёт тарифа,
новая детализация хранения, изменение начислений/operation facts, выплаты
сотрудникам и изменение уже существующих счетов. Счёт — снимок, не источник
пересчёта.

## 2. Экран и UX без регрессии

Меняется только новая invoice-зона существующего `FfBillingScreen`.
Существующие фильтры, сводка и детализация селлера Wave 3 сохраняют геометрию,
колонки, viewport и поведение. Никаких глобальных перемещений столбцов,
микрошрифта, горизонтального overflow страницы, переделки табов или соседних
экранов «заодно». Любой горизонтальный scroll возможен только внутри
`DataTable`/его штатного контейнера.

* При `include_finance=false` в ответах и UI нет денег, чекбоксов, истории
  счетов для строки и кнопки «Выставить счёт».
* При `include_finance=true` у select-able детализации виден штатный checkbox;
  он доступен только на корневой рассчитанной цепочке. Строка `reversed`
  видна, но не имеет самостоятельного checkbox. `not_billable`, `unpriced`,
  отсутствующая/проблемная storage-строка имеют disabled-state и краткую
  причину, а не молчаливый ноль.
* В выбранной детализации одного селлера кнопка «Выставить счёт» видна всегда
  при finance-on. Ноль выбранных операций открывает ручную форму; один и более
  выбранных — preview автоматического счета. Селлера из детализации/фильтра
  ручная форма подставляет, но разрешает сменить до preview.
* Ручная форма содержит от одной до десяти строк: обязательные «Описание
  услуги» и «Сумма», необязательная «Цена за штуку», «Добавить строку» и
  удаление (единственную строку удалить нельзя). Валидация visible и
  доступная: пустое описание, больше десяти строк, отрицательное значение,
  более двух знаков после запятой и пустая сумма не дают перейти к preview.
* Preview показывает реквизиты ФФ и селлера, номер и дату, период только для
  автоматического счета, строки «Услуга»/«Сумма» и итог. Ручной preview
  показывает колонку цены за штуку, только если она заполнена хотя бы в одной
  строке; иначе такой колонки нет, а частично пустые цены отображаются «—».
  До успешного POST нет сохраненного счета и нет кнопки печати.
* «Выставить и сохранить» блокируется на время одного запроса, после успеха
  открывает сохраненный immutable snapshot и даёт «Распечатать». «Назад» не
  теряет введенную ручную форму или selection. Ошибка сети/409/422 остаётся в
  модалке с безопасным повтором; клиент не заявляет, что счет создан.
* Верхняя вкладка называется «Выставленные счета» (не новый route). В таблице
  ровно: номер, дата выставления, селлер, период или «Ручной», сумма, статус
  «Выставлен»/«Отменён», «Открыть». Сортировка по дате/номеру стабильна,
  поиск/period/status/seller не ломают legacy history. Empty/loading/error —
  штатные `EmptyState`/`TableSkeletonBody`/`ErrorNotice` с повтором.
* Открытый v2 счет показывает снимки и печатается тем же утверждённым
  оформлением. Отмена подтверждается отдельным штатным dialog; она меняет
  только статус на «Отменён», не удаляет и не освобождает связи. Повторное
  выставление разрешено и создаёт новый номер. Существующий legacy modal,
  print и cancel сохраняют прежние данные и визуальное поведение.

Live browser verdict обязан проверить ширины 1600 и 1280, отсутствие page
overflow/наложений, keyboard/focus/error path, finance-off, ручной и
автоматический flow, cancelled/reissued, legacy open/print/cancel и print
media. Скриншоты должны быть настоящими, не Playwright-артефактом или mock-up.

## 3. Данные и миграция

Старая `BillingInvoice` и её unique `(tenant_id, seller_id, period)` остаются
неизменными. Нельзя добавлять ей nullable period, менять `lines`, пересчитывать
`total_amount`, мигрировать legacy rows либо использовать ее unique для v2.
Добавляется независимая схема:

```text
BillingInvoiceV2
  id, tenant_id, seller_id, number
  creation_mode: selected_operations | manual
  period_start nullable, period_end nullable       # date, inclusive display bounds
  status: issued | cancelled
  issued_at, issued_by_user_id nullable
  ff_profile_snapshot, seller_profile_snapshot
  total_amount_kopecks: integer

BillingInvoiceV2Line
  id, tenant_id, invoice_id
  description_snapshot
  unit_price_kopecks nullable
  total_amount_kopecks: integer
  sort_order

BillingInvoiceV2Source
  id, tenant_id, invoice_line_id
  operation_fact_id nullable
  billing_ledger_entry_id nullable
  storage_calculation_token nullable
  signed_amount_kopecks_snapshot: integer
```

Every v2 table has required `tenant_id`, `UNIQUE (tenant_id, id)` and an index
beginning with `tenant_id`. `BillingInvoiceV2Line` has composite FK
`(tenant_id, invoice_id) → BillingInvoiceV2(tenant_id, id)`; source has
`(tenant_id, invoice_line_id) → BillingInvoiceV2Line(tenant_id, id)`. 0114
also adds `UNIQUE (tenant_id, id)` to `operation_facts` (and the matching model
constraint), because it is absent today and is required for source safety.
`BillingInvoiceV2Source(tenant_id, operation_fact_id)` then has composite FK
to `operation_facts(tenant_id, id)`, and `(tenant_id,
billing_ledger_entry_id)` has composite FK to the already tenant-unique ledger
entry. The source-row CHECK enforces exactly one of fact, ledger or storage
token; a manual line has no source. A storage token has no relational target,
so its HMAC verification and recomputation under the same parent tenant/seller
is the required service invariant, tested as strictly as the composite FKs.

The invoice's `seller_id`, `issued_by_user_id`, every fact/ledger seller and
the verified token seller are checked in the same transaction against the
parent `tenant_id`; a direct single-column FK is never treated as tenant proof.
V2 `number` is unique per tenant and source indexes `(tenant_id,
operation_fact_id)`, `(tenant_id, billing_ledger_entry_id)` and `(tenant_id,
invoice_line_id)` serve opening and Wave-3 prior-issuance lookup. A source may
be referenced by arbitrarily many v2 invoices — no unique constraint on
operation/ledger/storage source. FKs restrict deletion of retained facts but
do not cascade-delete invoice history. `total_amount_kopecks` and all v2 money
are integer kopecks, including negative chain net; float is forbidden.

The migration creates empty v2 tables/indexes/checks only and leaves legacy
rows/readers printable. Downgrade removes only those v2 objects. It also proves
on PostgreSQL that 0110→0114 upgrade and 0114 downgrade/re-upgrade retain one
head and preserve legacy invoice totals/JSON unchanged.

## 4. Источник суммы, selection и storage

Preview and save share one discriminated, typed `InvoiceV2DraftRequest`; save
adds only the HTTP `Idempotency-Key`. Both modes send `seller_id` as a context
identifier. `selected_operations` also sends required `date_from`/`date_to`,
selected root IDs and optional storage token; server validates the Moscow
interval and that every root belongs to that seller/date scope. `manual` sends
`seller_id` and 1..10 manual draft lines, with date context and selected IDs
absent; the user may change that seller before preview. The client never sends
rate, amount, chain members, totals, snapshots or a trusted storage amount.
The service reloads everything under tenant scope and creates the preview/save
snapshot server-side.

For an `OperationFact` root, selection is the complete connected reversal
chain rooted through `reversal_of_id`; its priced `BillingLedgerEntry`/line
records give the signed contribution. For a legacy `BillingLedgerEntry`, the
complete charge/reversal chain through `reversal_of_id` is used. The chain is
walked tenant-scoped with a visited set; malformed/cyclic/cross-seller chains,
unpriced source, disabled/non-billable result, missing seller or an operation
outside the selected detail scope fail closed with named 409/422. A reversal
cannot be selected separately. Each automatic service row aggregates selected
chains by the canonical service description, and persists each exact linked
fact/ledger member and signed kopeck contribution so its historical total is
auditable after new reversals/tariffs.

The Wave-3 `storage_calculation_token` is required for the one selected
storage row. The service verifies the signed, versioned, tenant/seller-bound
token and recomputes the exact storage interval before write; changed movement,
dimension or tariff produces `409 storage_calculation_stale`, never an old
amount. A missing dimension cannot be selected. Storage persists one v2 line
and one token source with its signed snapshot, without product/day/warehouse
breakdown.

Manual lines create no source and therefore do not make an operation appear as
previously invoiced. For both modes the service snapshots the then-current FF
and seller requisites, descriptions, period, amounts and number. Subsequent
profile, product, tariff, movement and source changes do not rewrite it.

## 5. API, RBAC, idempotency and concurrency

Only fulfillment admin routes may read/write v2 invoices. Every query and
mutation scopes `tenant_id` from authenticated user; an absent, foreign or
deleted seller/invoice/source returns 404 without cross-tenant disclosure.
Pydantic request/response models live in
`backend/app/api/billing_invoice_v2_schemas.py`; `billing.py` retains only
router/RBAC wiring and must remain below the `back_guard` limit without a
baseline edit. Responses use integer `*_kopecks`, ISO date/date-time, explicit
`creation_mode`, status and stable IDs; OpenAPI tests resolve all refs.

Required endpoints (names may be mechanically adjusted only if they collide
with an existing route; semantics do not change):

* `POST /api/billing/invoices-v2/preview` — accepts the shared
  `InvoiceV2DraftRequest`; validates context and returns an unsaved server
  preview. `selected_operations` requires at least one eligible root;
  `manual` requires 1..10 lines. Decimal grammar is `^-?\d+(\.\d{1,2})?$`,
  business amounts are non-negative, and `Decimal` converts with exact
  two-place validation and `ROUND_HALF_UP` to kopecks. No float or locale
  ambiguity.
* `POST /api/billing/invoices-v2` — accepts that **same**
  `InvoiceV2DraftRequest` plus required opaque `Idempotency-Key`. It recomputes
  rather than trusts preview, assigns the shared invoice document number under
  its existing locking discipline, persists one snapshot transactionally, and
  returns it.
* `GET /api/billing/invoices-v2` — tenant-filtered cursor list with optional
  seller, date range, status, number search and limit 1..100; stable keyset
  order `(issued_at DESC, id DESC)` and signed cursor bound to all filters.
* `GET /api/billing/invoices-v2/{id}` and
  `POST /api/billing/invoices-v2/{id}/cancel` — exact snapshot and idempotent
  cancellation. Concurrent cancel is safe: only `issued→cancelled` occurs.
* `GET /api/billing/invoices` is the compatibility facade. Its envelope stays
  `{"invoices": [...], "issues": [...]}`: `issues` retains the exact legacy
  `BillingRunIssue` computation and shape, and every legacy invoice keeps all
  current field names and values. `invoices` is the union of legacy monthly
  rows and v2 rows, globally ordered by `(issued_at DESC, source_kind DESC,
  id DESC)`, where the fixed source-kind tie-breaker is part of a signed cursor.
  Optional `limit` (1..100) and `cursor` add pagination without removing
  current filters; no foreign/filter-replayed cursor is accepted. V2 rows add
  `creation_mode`, `period_start`, `period_end` and integer
  `total_amount_kopecks`; legacy rows retain their old decimal `total_amount`
  and need no new discriminator. The frontend opens a row carrying
  `creation_mode` through `/invoices-v2/{id}` and every other row through the
  untouched legacy endpoint.

  Existing `period=YYYY-MM` semantics stay exact for legacy monthly rows.
  For selected-operation v2 rows it means inclusive Moscow-period overlap with
  that calendar month; manual v2 rows have no period and are excluded whenever
  `period` is present. With no `period`, all three modes remain eligible. The
  old `seller_id`, `status` and `number` filters apply identically to both
  sources; `next_cursor` is an additive envelope key. This makes the merged
  list deterministic without turning a manual invoice into a fictitious month.

The idempotency record (or equally durable unique request-key storage) is
tenant+user+idempotency-key scoped, hashes canonical request input and stores
the final invoice ID/response. Same key + same canonical request returns the
same invoice; same key + different request returns 409; a concurrently racing
submit cannot allocate two numbers or invoices. A fresh key deliberately
permits reissue. Number generation checks uniqueness across both legacy
`BillingInvoice.number` and v2 numbers inside the retry/transaction boundary.
Preview is not an authorization or pricing grant; save recomputes and may
return stale/validation conflict.

The legacy endpoints `/billing/invoices/{seller_id}/{period}/form`, legacy
`GET /billing/invoices/{id}`, legacy cancellation and their response shapes
continue to work exactly for old rows. New v2 writes never call legacy
`form_invoice`.

Wave 3's prior-issuance projection is extended narrowly, not replaced: for an
eligible fact/ledger/storage source it counts distinct same-tenant v2 invoice
IDs through `BillingInvoiceV2Source`, including cancelled invoices. It must
never infer a count from source text, number, date, amount or seller. An old
malformed legacy snapshot remains `unknown` exactly as Wave 3 specifies; a v2
link cannot manufacture certainty for broken legacy data. Finance-off still
omits all invoice-history identifiers/fields.

## 6. Отключение старого автомата

Before removal from beat, `wms.billing_invoices_daily` receives a server-side
kill switch at the task entry point. It is a durable code path that returns
without querying/creating an invoice, even for a message enqueued by an older
application. `backend/tests/test_billing_tasks.py` must prove a simulated
already-queued task calls neither `SessionLocal` nor `form_invoice`, and that
its public Celery wrapper is the same safe no-op. The same file must assert
`celery_app.conf.beat_schedule` has no value or task equal to
`wms.billing_invoices_daily` after the change. Only after both checks are green
is the beat entry removed; the task name stays registered as a safe no-op
during the compatibility window. No feature flag default or environment
setting may re-enable automatic creation silently. Existing automatically
created legacy invoices remain visible.

## 7. States, errors and consistency guarantees

Server is source of truth for availability, money and validity. Named outcomes:

* 401/403 — no session/not fulfillment admin; no data leak.
* 404 — tenant-external invoice, seller or source; identical non-enumerating
  response.
* 422 — invalid date/limit/cursor shape, manual decimal/line count/description,
  no selection or unsupported source type; no write.
* 409 — `storage_calculation_stale`, foreign/filter-mismatched cursor,
  malformed/reversal-chain conflict, changed idempotency payload or concurrent
  incompatible save; no fabricated success.
* 409/422 eligible-state error — unpriced, not billable, missing dimensions or
  standalone reversal. UI keeps selection/form and names the exact next step.
* 5xx/network after submit — UI says outcome is unconfirmed and offers only a
  repeat with the same idempotency key; it does not clear the draft or mint a
  new key automatically.

List/detail loading skeletons do not erase an already opened immutable invoice.
Empty history, zero selected items, manual draft and no matching filter are
distinct. A cancelled invoice remains in list/open/print and contributes to
the Wave-3 mark «Счёт выставлялся». The selection data itself is not mutated by
invoice creation; reloading a detail reflects the extra count from durable v2
sources, including cancelled/reissued invoices.

## 8. Required test cases and evidence

Every automation maps to the test coverage table in the eventual PR.

| TC-ID | Applies | Given / When / Then and negative/restriction |
|---|---:|---|
| TC-NEW-0401 | Y | Given one seller with charge+reversal chain, when root selected, then preview has one net service line and saves every exact source; reversal alone is rejected. |
| TC-NEW-0402 | Y | Given an unpriced/not-billable/missing-dimension row, when selected, then checkbox/API reject it with named reason and no invoice is written. |
| TC-NEW-0403 | Y | Given a valid signed storage token, when saved, then one aggregate storage line/source snapshot is stored; tampered, foreign or stale token returns `storage_calculation_stale` and writes nothing. |
| TC-NEW-0404 | Y | Given no selected rows, when the same typed preview/save body contains a manually changeable seller and 1..10 valid lines, then exact decimal strings become integer kopecks, no source exists, and invalid decimals/descriptions/11th row are blocked. |
| TC-NEW-0405 | Y | Given a request retried/raced, when same idempotency key and payload are submitted, then exactly one invoice/number exists; a changed payload with the same key is 409; a new key may reissue. |
| TC-NEW-0406 | Y | Given an issued v2 invoice, when tariff/profile/source changes and later it is opened/printed, then snapshot/sum stay unchanged; cancellation preserves history and prior-issuance mark. |
| TC-NEW-0407 | Y | Given two tenants or a non-admin, when reading/writing/listing/cancelling/cursor replaying, then foreign resources are undisclosed and finance/RBAC contracts hold. |
| TC-NEW-0408 | Y | Given legacy monthly invoices and new v2 invoices, when the compatibility facade filters/lists with a signed global cursor, then its `invoices`+`issues` envelope and legacy values stay intact, selected v2 matches overlapping month, and manual v2 is excluded by `period`. |
| TC-NEW-0409 | Y | Given an already queued old scheduled-task message, when Wave 4 task code runs, then it touches neither DB session nor `form_invoice`; beat has no daily invoice entry. |
| TC-NEW-0410 | Y | Given 1600/1280 live browser, when finance-off/on, selection, preview, save, print, cancel and reissue are traversed, then all visible states are usable, focusable and have no page overflow/overlap. |

Backend: focused service/API/OpenAPI/migration tests plus full `ruff check .`,
`mypy .`, `pytest`; PostgreSQL migration proof; no skipped failure. Frontend:
unit tests for request/decimal/print presentation, build, full unit and full
Playwright, with user-visible E2E routes/actions through UI and stable
`data-testid`. `ui_guard` and geometry invariants are mandatory. Test proof
records commands, exact output, migrated head, source-chain/reversal/storage,
idempotency race and legacy compatibility; it never substitutes for browser
acceptance.

Independent reviewer must test the diff against this contract. Independent
Terra product browser judge uses an isolated deterministic fixture containing:
two tenants, one eligible chain, standalone reversal, unpriced row, storage
row/token, manual seller, legacy invoice and cancelled/reissued v2 invoices.
Verdict names URL, role, clicks, visible outcomes and either
`PRODUCT_BROWSER_APPROVED`, `PRODUCT_REWORK_REQUIRED` or
`PRODUCT_BROWSER_BLOCKED`, with the prescribed 1600 preview, 1280 preview and
1600 print screenshots at the exact evidence path above. Only then may the
Wave 4 commit be pushed. This is not deployment or permission to merge.
