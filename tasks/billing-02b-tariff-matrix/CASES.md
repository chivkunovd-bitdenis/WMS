# Кейсы волны 2Б: тарифная матрица

## Позитивные

1. Администратор сохраняет одной matrix common inbound `document`, seller
   outbound `item`, item product override и employee inbound rate; все строки
   принадлежат его tenant и имеют один Moscow `valid_from_at`.
2. Product override выигрывает у seller/common item rate; при отсутствии
   product price применяется seller, затем common.
3. `inbound` и `marketplace_outbound` после migration остаются enabled с
   эквивалентным non-storage legacy rate; `packing` и `return` по умолчанию
   disabled. Disabled service виден как «Не тарифицируется», но деньги не
   создаёт.
4. Изменённая ставка закрывает predecessor точно в new start, создаёт новую
   immutable V2 row; повторение неизменённого payload возвращает тот же
   revision и не добавляет row.
5. New employee zero rate is explicit configured rate; historical zero
   PackagingTask is `billing_rate_configured=false`; historical nonzero is true.
6. Storage остаётся в legacy daily table: ставка действует целый Moscow day,
   storage product override/employee rate/intraday V2 не появляются.
7. Обычная регистрация и bootstrap-admin создают один persisted tenant matrix
   со всеми non-storage services disabled; повтор bootstrap возвращает тот же
   state, а не missing-row default.
8. Один inbound request и один shipped marketplace unload с несколькими
   products создают один ledger parent и immutable child lines с разными
   product overrides/rates; parent amount равен сумме independently rounded
   lines, parent rate при разных rates равен `null`.

## Негативные и atomicity

1. foreign seller, product, employee, warehouse/service scope или product
   другого seller/tenant отклоняются до записи; ответ не раскрывает чужие данные.
2. Product override при `document`, storage in V2, packing employee rate,
   отрицательная/overflow rate, disabled service with contradictory rate и
   malformed Moscow timestamp — 4xx и zero writes.
3. Overlapping intervals, same scope timestamp, end <= start и stale revision
   отклоняются. PostgreSQL и service оба проверяют schedule; interval boundary
   `[start,end)` не даёт двойную ставку.
4. Один payload содержит валидную первую строку и невалидную вторую: neither
   version, enabled flag, close time, ledger link nor rate-configured marker
   changes after rollback.
5. Concurrent saves one stream serialize: one succeeds, other gets named
   conflict/reloads draft; partial configuration never appears.
6. Сбой configuration во время registration/bootstrap откатывает и Tenant;
   concurrent/repeated bootstrap не создаёт второй config или service states.
7. Foreign parent/product/fact/tariff для `BillingLedgerLine`, отсутствующая
   tenant matrix или aggregate write с невалидной product line отклоняются без
   parent и без частичных lines.

## Регрессия финансов и миграции

1. `uq_billing_ledger_source_event` remains unique and its columns/name are
   unchanged; same source retry remains one legacy/V2 charge, reversal remains
   immutable.
2. Legacy ledger and invoices open/print/cancel exactly as before; old
   `tariff_version_id` remains valid and V2 nullable link does not rewrite
   amount/rate/snapshot.
3. Backfill copies every non-storage legacy interval as Moscow timestamp
   interval without gap/overlap; old inclusive date end becomes next excluded
   midnight. No historical pre-2A fact is reconstructed.
4. Date at Moscow midnight, three-day range, month/year edge and explicit
   timezone/DST-validity cases resolve one active rate, not browser-local day.
5. Existing storage tariff API/screen, monthly storage statement and packaging
   payroll regression pass untouched.
6. Повтор source event возвращает исходный parent с исходным набором child
   lines; reversal создаёт signed immutable counterparts ровно один раз.
   Legacy parent без child lines, его amount/rate/snapshot и invoices остаются
   без guessed backfill и без изменения.

## API, RBAC and OpenAPI

1. Fulfillment admin GET/atomic save returns only own tenant and validates
   schema in OpenAPI tests.
2. fulfillment_staff, seller, shift lead and unauthenticated request cannot
   read or save matrix; another tenant cannot use IDs even if guessed.
3. Old `/billing/tariffs`, ledger and invoices response contracts remain
   backward compatible until later report/invoice waves deliberately extend
   them.

## Browser S-19 at 1600px

1. Admin opens existing `/app/ff/settings`: panel follows staff, has expected
   headers/columns and horizontal overflow inside table container only; header,
   warehouse and staff zones have unchanged geometry.
2. Existing `/app/ff/settings?tab=tariffs` scrolls and focuses the stable
   tariff panel anchor after it is rendered; without the query normal Settings
   content and scroll remain unchanged. `FfBillingScreen` and routes are not
   edited.
3. Admin enables a service, selects allowed unit, enters rate/time and saves:
   loading disables only save/action with explanation; success reloads visible
   version. A document unit disables product override with reason.
4. Network/API error is `ErrorNotice` in panel, does not erase last rendered
   matrix; empty config explains what to configure; loading is table skeleton.
5. Staff/seller do not see the panel or its values. Existing staff permissions,
   Billing ledger and invoices Playwright scenarios remain green.
6. Separate Terra ui-critic checks UX canon and separate Terra judge manually
   checks live browser success/error/empty/disabled at 1600px; both save
   screenshots plus invariants/ui_guard output to evidence.
7. `FfBillingTariffMatrixPanel` remains an internal S-19 composition only:
   it adds no route/screen/UI primitive and the Settings monolith guard stays at
   its approved baseline.

## UI-kit prerequisite before S-19 correction

1. Separate prerequisite tests prove generic `TextInput`, `NumberInput`,
   `SelectInput` and `MoscowDateTimeInput`: every field has a programmatic
   label, linked help/error text, invalid and disabled/loading state; numeric
   value is right-aligned and respects bounds; select options are keyboard
   reachable and expose disabled choices.
2. Moscow field renders Moscow wall time regardless of browser timezone and
   returns an explicit UTC ISO instant; invalid/ambiguous wall time stays an
   accessible validation error rather than silently using browser-local time.
3. `UiKitShowcase` renders isolated examples of all four primitives. `ui_guard`
   and typecheck stay green. No existing kit component or legacy screen is
   refactored, and the S-19 panel does not import raw MUI input/select/date
   controls after the prerequisite.
