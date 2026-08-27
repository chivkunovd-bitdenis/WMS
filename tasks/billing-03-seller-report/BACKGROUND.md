# Фон и контракт данных: Wave 3 seller report

## Граница read-model

Wave 3 is read-only. It creates neither financial charge nor invoice, and does
not alter 2A/2B source-of-truth rows. `OperationFact` covers events at/after its
cutover; legacy `BillingLedgerEntry` covers the earlier half. The report service
must apply that boundary in both summary and detail queries, otherwise a single
operation can double count. Its tenant predicate is mandatory on every join and
lookup, including seller, product, source, tariff, movement and dimension.

`BillingLedgerEntry.storage_liter_day` is excluded unconditionally. It exists
for monthly storage history and legacy invoices only. The report's `storage`
kind is computed from raw source data once per seller+period and is not saved as
a ledger row, OperationFact, StorageStatement or monthly draft.

## Money and response shape

Money crosses this read-model only as integer kopecks. Finance-off Pydantic
models are distinct from finance-on models, so serialisation cannot emit an
accidental `null` monetary key. Physical `item_quantity` stays physical; a
legacy document-unit amount with no reconstructible item count exposes `null`,
not invented quantity. Charge and reversal stay immutable separate rows; gross,
reversal and net are independently calculated server aggregates.

`not_billable` means disabled/no billable service and remains visible without
finance. `unpriced` means a billable item has no price and is only a finance-on
problem. It is never silently converted to zero money.

## Cursor and stable links

The report detail cursor is opaque and tied to tenant, seller, period and
finance mode. Its position is the full deterministic order key; a cursor from a
different filter/tenant is 422/404 without data disclosure. Sources carry
explicit server `source_target` (known route or inbound target) and source
identity. Storage deliberately carries no target. A missing/deleted target is
shown as unavailable, not routed by guessed client convention.

## Exact storage and stale token

The reusable interval helper must use the same Moscow-aware movement/dimension
segmentation as storage measurements. It starts from stock state before the
lower bound, clamps every segment to the exact half-open interval, aggregates
all operational warehouses/products, and applies the effective daily storage
tariff for every interval day. It must report missing dimensions rather than
backfilling a later volume to an earlier period.

Fingerprint inputs and output are canonically serialised and ordered before
SHA-256/signing; values use non-float Decimal strings/kopecks. The HMAC key is
domain-separated from existing `settings.jwt_secret_key`, so the wave requires
neither a new secret nor an unlisted settings path. A token contains no
authority to write. Wave 4 validates it in the same transaction as invoice
creation, recomputes source fingerprint and returns 409 on mismatch. This
preserves the exact quote/review boundary without storing an accidental second
storage document.

## Invoice-history transition

Wave 3 exposes invoice history without changing invoices. It applies only to a
finance-on `legacy_billing` detail row and returns its
`billing_ledger_entry_id` plus `invoice_history`. Current `form_invoice`
persists each legacy source snapshot as
`BillingInvoice.lines[].documents[]` with `id=str(BillingLedgerEntry.id)`;
that exact ID is the only primary link. The complete charge/reversal chain is
checked, and distinct `BillingInvoice.id` values are counted only inside the
same tenant and seller. Cancelled invoices count: their cancellation does not
erase prior issuance.

Known count 0 is allowed only when **every** persisted `documents[]` snapshot in
the candidate tenant/seller legacy-invoice corpus has a parseable exact ledger
ID. Any missing or malformed snapshot ID makes the result
`invoice_history={state:"unknown"}` rather than claiming a negative; this is a
deliberately conservative all-snapshots rule. `OperationFact` and synthetic
storage are also unknown; they never receive a guessed ledger/invoice link.
Document number, date, amount, seller, service and UI route are prohibited join
keys. Finance-off omits both `billing_ledger_entry_id` and `invoice_history`
entirely.

This is read-only: there is no checkbox, selection or invoice write, so repeated
issuance remains allowed. Wave 4 adds `BillingInvoiceV2Source`, selection,
preview and print without retroactively guessing Wave-3 unknown history.

## Compatibility and integrity

There is no schema migration in this wave. Existing old `/billing/ledger` and
`/billing/invoices` retain their request and response semantics, including their
money fields when called without any new parameter. The new read endpoints are
additive. No index/constraint is removed or weakened, especially
`uq_billing_ledger_source_event`; no monthly statement, ledger row, tariff,
invoice, operation fact, source movement or dimension event is written by a GET.
