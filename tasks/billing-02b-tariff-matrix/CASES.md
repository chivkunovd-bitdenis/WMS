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
2. Admin enables a service, selects allowed unit, enters rate/time and saves:
   loading disables only save/action with explanation; success reloads visible
   version. A document unit disables product override with reason.
3. Network/API error is `ErrorNotice` in panel, does not erase last rendered
   matrix; empty config explains what to configure; loading is table skeleton.
4. Staff/seller do not see the panel or its values. Existing staff permissions,
   Billing ledger and invoices Playwright scenarios remain green.
5. Separate Terra ui-critic checks UX canon and separate Terra judge manually
   checks live browser success/error/empty/disabled at 1600px; both save
   screenshots plus invariants/ui_guard output to evidence.
