# Кейсы Wave 3: отчёт по селлерам

## Отдельная UI-kit prerequisite до main-волны

1. `MoscowDateInput` and `MoscowDateRangeInput` are browser-timezone
   independent, have visible/programmatic label, linked help/error,
   disabled/loading and keyboard semantics; reversed, malformed, over-366-day
   and future end values are accessible validation errors.
2. `PreferenceSwitch` is a labelled controlled generic view switch with
   disabled/loading semantics. Its API/text/style contains no billing/seller/
   finance concept.
3. `FormFields.test.tsx`, tsc, ui_guard and isolated `UiKitShowcase` proof pass
   in the prerequisite commit. No existing screen is refactored there.

## Позитивные и серверные

1. `fulfillment_admin` requests a three-day Moscow range containing operational
   facts/legacy ledger on both sides of cutover: each appears once, summary and
   detail server totals match independently computed gross/reversal/net.
2. Inclusive one day, 366 days, month/year boundary and Moscow midnight return
   `[start, end+1day)` exactly; 367 days, reversed, malformed and future Moscow
   end dates fail with 422 before a write.
3. Finance-off and finance-on have identical seller/operation/storage
   composition. Finance-off JSON contains no money/unpriced keys; finance-on
   returns integer kopecks, independently formatted once in UI.
4. Summary totals cover all matching rows, not just the first 50 detail rows.
   Cursor next page has no duplicate/gap and does not recalculate a second
   storage row.
5. Disabled service is physical `not_billable`; unpriced billable service is a
   finance-on problem and does not enter accrued/net totals.
6. Detail source target opens only the named original inbound/marketplace
   document. Unsupported/deleted source is visible unavailable, not guessed.
7. Finance-on legacy row with exact `documents[].id == billing_ledger_entry_id`
   returns `invoice_history={state:"known",count:N}`: zero is 0; two distinct
   invoices give 2 even if the entry appears twice within one invoice. Issued
   and cancelled invoices both count.
8. The complete charge/reversal chain is considered. A cross-tenant or
   other-seller invoice never counts. Any missing/malformed `documents[].id` in
   the same tenant/seller snapshot corpus makes the state unknown even for a
   seemingly matching row; same document number/date/amount/source text never
   substitutes for it. `OperationFact` and storage are unknown.
9. Finance-off omits both `billing_ledger_entry_id` and `invoice_history`;
   finance-on returns the count only for known legacy rows.

## Storage

1. Two warehouses/two products give exactly one `storage_row`, no link and no
   product/day/warehouse breakdown. Monthly `storage_liter_day` ledger rows do
   not affect it.
2. A three-day slice inside a month equals an independent segment calculation,
   not the whole monthly statement; tariff changes at Moscow day boundary use
   both correct daily rates.
3. A held product without valid dimension yields `missing_dimensions`, no
   finance amount and no synthetic zero price.
4. Fingerprint/token is stable for unchanged ordered source data; changing a
   movement, effective dimension or tariff produces a different fingerprint.
   Wave-4-validation helper rejects old token with named stale result, foreign
   tenant/seller token and malformed signature.

## Negative, access and compatibility

1. unauthenticated, `fulfillment_staff`, seller and `shift_lead` get no new
   report data; guessed foreign seller/detail/cursor returns no foreign data.
2. API/service failure preserves rendered summary and produces `ErrorNotice`,
   not a false empty report. A fast filter change aborts/ignores stale response.
3. Legacy `/api/billing/ledger` and `/api/billing/invoices`, invoice open,
   cancel and print retain existing responses/behaviour; their current
   Playwright regressions pass without edits.
4. Finance-on shows `—` for known 0, `✓ 1`/`✓ N` for known positive and
   tooltip-explained «Нет данных о старом счёте» for unknown. It remains
   read-only: no checkbox, selection or button blocks/creates a repeated
   invoice; Wave 3 creates no invoice, V2 source or employee data.

## Browser at 1600px

1. Admin opens existing billing route: renamed Sellers tab has fixed columns, summary,
   at most four metrics and separate detail block; no custom table or route.
2. Finance off screenshot: rate/amount/accrued/unpriced, invoice-history
   column/IDs, invoice controls and money totals are absent. Finance on adds
   report money and known/zero/unknown invoice-history marks, with kopecks
   converted once.
3. Loading uses skeleton, empty state explains how to change period, server
   failure is an error alert, and detail failure does not erase summary.
4. One storage row is visible for the selected seller/period and horizontal
   overflow, if required, belongs to the real table container. UI critic and
   live judge separately run these states; `ui_guard`/invariants evidence is
   saved. Old Invoices remains unchanged; no Employees placeholder, invoice
   selection/control or print appears. Invoice print and Employees are not part
   of this browser suite.
