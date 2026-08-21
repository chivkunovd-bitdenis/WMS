# S13 ARCHITECT_PLAN - BLG-I04

## Verdict

`ARCH_PLAN_READY`

`BLG-I04-C1` remains one vertical high-risk FBS print card. The safe boundary is
not a cosmetic quantity-field change: one immutable print-plan snapshot must
drive the visible sheet total, the large-run decision, the mutating FBS tape
request and the browser print document. The plan below keeps the existing FBS
action and print layout, adds no second operator workflow, and prevents an order
count from becoming an implicit copies value at any boundary.

No implementation, test run, commit, push, deployment, live printer action,
marketplace call, secret access or acceptance verdict is performed at S13.

## Approved inputs and observed current path

- `tasks/BLG-I04/S09-UX-CONTRACT.md` defines the visible quantities and UI-kit
  components.
- `tasks/BLG-I04/S11-PRODUCT-CONTRACT.md` owns the inclusive threshold of 100
  sheets and the formula
  `totalSheets = sheetsPerOneCopy * copiesPerRequiredLabel`.
- `tasks/BLG-I04/S12-TASK-CUT.md` keeps the visible preflight and actual FBS
  print boundary in one card.
- The current bulk action in
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` derives
  `unprintedPackingOrders`, opens the shared `MarkingPrintDialog`, and passes
  those order IDs plus `layout_json` to the existing `order-print-tape` POST
  route.
- `frontend/src/components/MarkingPrintDialog.tsx` currently uses several
  quantities with different meanings: `qtyNeedPack` is the required-unit count,
  `layout.units[].copies` repeats a block inside one item's layout, and
  `wbBarcodeQty` is a client-side label count. The same component immediately
  performs the mutating request and constructs the browser print document.
- `backend/app/services/fbs_order_tape_print_service.py` parses the layout,
  processes each requested order, obtains/reuses one marking code per applicable
  order, may obtain the order QR, and returns the material from which the client
  builds pages. It does not currently expose an authoritative print-plan total,
  a plan fingerprint or a request idempotency key.
- `FbsPrintAsset` already makes ready order stickers durable and unique per
  order/kind. `FbsWbOperation` already provides a seller/kind/idempotency journal
  with request and response summaries. Those existing resources are sufficient;
  this plan requires no migration or new worker.

The current tip does not contain one explicit assignment named
`selectedOrders -> copies`. The architectural defect is the ambiguous contract
between the three quantities above: a future or existing caller can encode the
selected count in layout/client copies, while neither API nor renderer proves
that the submitted pages equal the total shown to the operator. S18 must remove
that ambiguity rather than patch one multiplication expression.

## Resource graph

```text
current FBS printable order set + current normalized layout
  + independent copiesPerRequiredLabel (default 1)
    -> read-only order-print-tape preflight
      -> canonical PrintPlan + fingerprint + threshold decision
        -> visible selected count and exact totalSheets
          -> direct submit (<100) OR fingerprint-bound confirmation (>=100)
            -> idempotent order-print-tape commit with expected fingerprint
              -> existing QR / marking-code material
                -> exact base-page renderer assertion
                  -> outer-copy expansion exactly once
                    -> browser print invocation
                      -> later browser/device evidence for the same plan
```

The selection decides which required labels exist. The layout decides the
ordered pages in one set. `copiesPerRequiredLabel` repeats each resulting page
and is never written into the selection or normalized layout.

## Architectural decisions

### A1. Three typed quantities with one multiplication edge

Introduce a print-plan contract with these integer fields:

```text
selectedOrderCount       read-only scope count
sheetsPerOneCopy         canonical pages produced by one normalized layout pass
copiesPerRequiredLabel   one editable positive integer, reset to 1 on every open
totalSheets              sheetsPerOneCopy * copiesPerRequiredLabel
```

`layout.units[].copies` retains its existing meaning: copies of a `cz` or
`label` block inside the layout of one required item. It is part of calculating
`sheetsPerOneCopy`; it is not the new outer copies value. The implementation
must not multiply `layout.units[].copies`, `order_ids.length`, `qtyNeedPack` or
`wbBarcodeQty` by `copiesPerRequiredLabel` before the final page-expansion edge.

For the FBS tape mode, one-copy pages are deterministic:

- one order-QR page per selected order when `include_order_qr` is true;
- for an order requiring Honest Sign, one page for every normalized layout
  block emitted for its single assigned/reused code;
- for an order not requiring Honest Sign, one required WB product-label page;
- unavailable or invalid items are blockers or an explicitly returned partial
  plan; they are never silently counted and then omitted.

The arithmetic accepts a positive whole number without an operational hard
maximum. It uses checked safe-integer calculation in the browser and Python's
exact integer arithmetic on the server. A value whose exact total cannot be
represented by the client is rejected as an invalid exact-total input, never
clamped or rounded.

### A2. Read-only server preflight is the source of truth

Add a read-only, authenticated route alongside the existing commit route:

```text
POST /operations/fbs-supplies/{supply_id}/order-print-tape/preflight
```

Its request contains the ordered `order_ids`, normalized `layout_json`,
`allow_partial`, `include_order_qr`, `reprint`, and
`copies_per_required_label`. It performs no code allocation, marking event,
asset fetch, WB/Ozon call, print-window open or state mutation.

The response contains at least:

```text
plan_version
plan_fingerprint
selected_order_count
printable_order_count
sheets_per_one_copy
copies_per_required_label
total_sheets
large_print_threshold_sheets
large_confirmation_required
blockers / shortage summary
```

The backend normalizes the layout with the existing parser and computes the
plan from tenant-scoped current orders. The fingerprint hashes the plan version,
supply, ordered selected IDs, printable subset, per-order printable kind,
normalized layout, partial/reprint/QR flags, outer copies and total. It contains
no CIS, barcode, token or other secret.

The central threshold lives once in a small backend print policy module and is
returned by preflight. The frontend must not hard-code 100. The mutating route
uses the same policy function, so a direct API caller cannot bypass the
inclusive `total_sheets >= 100` rule.

Preflight is repeated whenever selection, layout, partial mode, reprint mode or
outer copies changes. While it is pending, failed, or stale, submission is
unavailable. This preserves exact multi-page totals without requiring a live
marketplace request merely to render the form.

### A3. Fingerprint-bound commit contract

Extend the existing `order-print-tape` body additively with:

```text
copies_per_required_label
expected_plan_fingerprint
expected_total_sheets
large_run_confirmed
idempotency_key
```

Before any print mutation or marketplace call, the service reloads the
tenant-scoped supply and selected orders, parses the layout, and recomputes the
canonical plan. It rejects the request without side effects when the
fingerprint or total differs, when the selection is no longer printable, or
when a run of 100 or more sheets lacks `large_run_confirmed=true`. A stale
response returns a structured `print_plan_stale` result so the UI can show the
new preflight rather than printing the old count.

The success response carries the accepted plan version, fingerprint,
`sheets_per_one_copy`, outer copies and `total_sheets` together with the
existing order/asset/code material. These are the run identity used by S22,
S23 and S25; request-level success still does not prove paper output.

The API remains additive for other consumers. Existing non-FBS catalog and
packaging-line print routes are not moved into this contract by BLG-I04.

### A4. Confirmation is a state transition, not a second calculator

The FBS zone uses the approved UI-kit components already exported by
`frontend/src/ui-kit/index.ts`: `TextInput`, `QtyCell`, `ToolbarLine`,
`ActionGroup`, concrete `PrintAction`, `ModalDialog`, `SecondaryAction`,
`PrimaryAction` and `ErrorNotice`.

The client state machine is:

```text
closed
  -> preflighting(copies=1)
  -> ready(plan fingerprint F)
  -> submitting(F)                         when total < 100
  -> confirming(F) -> submitting(F)        when total >= 100
  -> accepted(F) | rejected(F) | unknown(F)
```

The large-run modal stores only fingerprint `F`; it does not copy or recalculate
the total independently. Any plan input change closes/invalidates that modal,
starts a new preflight and disables submission until a new fingerprint exists.
Cancel, Escape and close retain the copies field but make no commit request.
The second action submits only if the current fingerprint is still `F`.

Opening a later normal or repeat-print action constructs a new state machine,
sets copies to `1`, and obtains a new preflight. No prior unusual value or
confirmation survives close/reopen, workspace reload or a changed order set.

### A5. One deliberate submission, durable idempotency

Generate one idempotency key when a preflight fingerprint becomes ready and
retain it across the corresponding direct/confirmed submit and any deliberate
retry after an unknown response. A changed fingerprint gets a new key. Busy
state disables every submit/confirm control before the request promise starts;
one activation invokes the API at most once.

Reuse `fbs_wb_operations` with a new operation kind such as
`order_print_tape`. Its request hash includes every plan input and the accepted
fingerprint. The journal stores only sanitized order/code/asset identifiers,
counts, hashes and outcome metadata; raw CIS values and binary labels are read
from their existing protected records and are never copied into the journal.
No schema change is needed.

Same-key behavior is mandatory:

- same key and same request hash returns/reconstructs the same accepted result
  or reports the same pending/unknown state; it does not allocate another code,
  create another asset or repeat an unverified external effect;
- same key with a different request hash returns `idempotency_key_reused`;
- a pending operation is reconciled from durable order markings, print assets
  and operation state before any resume; it is never blindly replayed;
- an accepted replay may reopen the browser print document only after a new
  explicit operator action. There is no automatic retry.

Create/read the operation identity before order mutation. Within database work,
lock the operation row, then the supply, selected orders in ascending UUID, and
their marking-code rows. Do not hold those row locks across WB HTTP. If the
existing service cannot make the pending intent durable and reconcile an
uncertain external step without a migration or broader workflow change, S18
must stop and return to S13/S02 for reclassification; it must not hide the gap
with a client-only busy flag.

### A6. Renderer has a fail-closed page-count postcondition

The browser renderer first builds one ordered `baseSections` array from the
accepted server material. It must assert:

```text
baseSections.length == acceptedPlan.sheetsPerOneCopy
```

It then expands outer copies exactly once, adjacent per required page, and
asserts:

```text
printSections.length == acceptedPlan.totalSheets
```

Only after both checks pass may `printTapeSections`/`window.print` be called. A
missing QR, missing code artifact, partial response, renderer error or count
mismatch opens no print window and is shown as an unconfirmed request. The
renderer must not recover by substituting `selectedOrderCount` as a copies
value or by silently dropping pages.

Browser print APIs do not provide reliable physical completion evidence.
Success wording may say that the accepted run or print dialog was opened; it
must not say the paper printed. S25 browser evidence and the separate approved
device/printer evidence remain distinct as required by the `print` trait.

## Future S18 resource ownership

S17 should allocate one exclusive card lock for the following bounded write
set. Exact new helper filenames may be refined by S14/S17 without changing
their responsibilities.

| Resource | Planned responsibility |
| --- | --- |
| `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` | Keep the existing printable-order derivation, pass current selection identity, and use the concrete UI-kit `PrintAction`; no table/row behavior change. |
| `frontend/src/components/MarkingPrintDialog.tsx` | FBS-only copies/preflight/confirmation/request state, approved UI-kit controls, truthful errors and reset-on-open. Generic catalog/line modes remain behaviorally unchanged. |
| `frontend/src/screens/v2/fbsApi.ts` | Typed preflight and additive commit request/response contracts, including fingerprint and idempotency key. |
| `frontend/src/utils/fbsPrintPlan.ts` (new) | Pure checked arithmetic, fingerprint-bound client state helpers, and exact one-time outer page expansion; no policy threshold constant. |
| `frontend/src/utils/fbsPrintPlan.test.ts` (new) | Arithmetic, multi-page, 10-not-100 default, outer copies, safe-integer and renderer-count unit cases. |
| `frontend/src/screens/v2/FfFbsSupplyWorkspace.test.ts` | Selection/reset/stale-context integration coverage. |
| `frontend/tests-e2e/ff-fbs-full-flow.spec.ts` | Deterministic operator preflight, inclusive confirmation, cancel, stale confirmation, double activation and unknown-outcome browser flow. |
| `backend/app/api/fbs_supplies.py` | Read-only preflight route and additive guarded commit fields/response; preserve FBS authorization and structured errors. |
| `backend/app/services/print_run_policy.py` (new) | Single backend-owned inclusive threshold and checked plan policy used by preflight and commit. |
| `backend/app/services/fbs_order_tape_print_service.py` | Canonical plan calculation, stale/large-run guards, idempotent operation orchestration and accepted-plan response. |
| `backend/app/services/fbs_supply_reconcile_service.py` | `order_print_tape` request hash and existing-journal helpers; no general supply-operation redesign. |
| `backend/tests/test_fbs_order_tape_print_plan.py` (new) | Route/service behavior, authorization, exact totals, threshold, stale plan, replay/unknown result and no-side-effect negative cases. |
| Existing focused FBS/marking tests selected by S15 | Regression that one code per order, layout block semantics, QR assets and marking events remain intact. |

No Alembic migration, model column, Celery task, Redis namespace, mobile
consumer, print-template schema, label content/size, printer setting, table
selection, filter, tab, menu, marketplace client contract, secret, deploy or
release file belongs to this write set. Discovery of a required write there
returns to architecture/impact classification before Dev expands scope.

## Contract and compatibility boundaries

- The preflight route is additive and must have behavior tests because it is a
  new route.
- Existing `layout_json` limits and parsing remain authoritative. Outer copies
  do not alter saved templates or `PrintLayout` serialization.
- `MarkingCodeEvent.copies` keeps its current per-code/layout meaning. It is not
  overloaded as the total run size; the run-level operation summary owns outer
  copies and total sheets.
- Existing consumers that do not send the new commit fields must not silently
  bypass the product contract. S18 must either make the guarded fields required
  for `order-print-tape` and update its only known typed caller in the same
  card, or prove an explicit versioned compatibility path that still performs
  canonical preflight and large-run enforcement. A default such as
  `large_run_confirmed=true` is forbidden.
- Preflight and commit are tenant-scoped through the existing FBS operator
  dependency and supply lookup. Foreign tenant/seller/order identifiers reveal
  no plan counts or existence details.
- The route performs no live call during preflight. S15/S22 use local fixtures
  and the marketplace emulator only; no live WB/Ozon or printer is authorized.

## Required S15 and S22 proof

S15 should bind the approved `I04-C1-AC01..AC10` cases to these concrete lanes:

1. One and ten one-page items at copies `1`; both preflight and accepted result
   equal 1 and 10, with no order-count reuse in layout or outer copies.
2. A known multi-page mixed layout where `sheetsPerOneCopy` differs from order
   count; copies `1` and `3` multiply only the final base-page count once.
3. Totals 99, 100 and 101 from deterministic fixtures; only 99 can commit
   without a second confirmation, and a direct API call cannot bypass 100.
4. Empty, zero, negative, fractional, non-numeric and non-representable copies;
   no preflight-ready state and no commit or print window.
5. Empty/non-printable selection, shortage and explicit partial-plan fixtures;
   visible counts equal the exact returned printable plan or submission remains
   blocked.
6. Cancel/Escape/close at large confirmation; zero commit calls and retained
   copies value.
7. Change order set, layout or copies while confirmation is open; old
   fingerprint rejected client-side and server-side, then a new total appears.
8. Double click, two same-key requests, timeout before response, and process
   restart between pending and read-back; one durable intent and no blind
   repeated mutation.
9. Close/reopen and ordinary workspace reload after a non-default value;
   copies resets to 1 and a fresh plan is fetched.
10. Renderer fixtures with a missing asset or deliberately wrong section count;
    no `window.print`, no false success, and an `ErrorNotice` with the unchanged
    accepted total.
11. Cross-tenant and wrong-supply order IDs; no counts, code allocation, asset
    access, journal row or external emulator call escapes the authorized scope.
12. Same run identity across visible preflight, accepted operation summary,
    browser document page count and later approved-device evidence, with
    request acceptance explicitly separated from physical output.

Evidence for mutating cases records sanitized plan version/fingerprint,
idempotency-key fingerprint, selected/printable counts, normalized layout hash,
copies, base/total sheets, threshold decision, operation state, API invocation
count, renderer section count and emulator call count. It must not contain raw
CIS, labels, Authorization data or marketplace credentials.

## S14 falsification handoff

The independent architect must try to disprove this plan with at least:

- selection count leaking into `layout.units[].copies`, `wbBarcodeQty`, outer
  copies or renderer loops;
- a ten-item default run producing 100 pages;
- a mixed/multi-page layout where client and server count different pages;
- non-Honest-Sign and mixed selections using different fallback rules;
- total 100 bypassing confirmation through direct API use;
- a selection/layout/copies change after modal open but before the second click;
- a preflight response racing a newer input and replacing its total;
- missing QR, shortage or partial result after commit changing the rendered
  page count without a new visible preflight;
- double activation before busy state is committed;
- same-key concurrency, timeout and process death causing another code, asset,
  metadata delivery or operation row;
- different request data accepted under one key;
- row locks held across marketplace HTTP or an unrecoverable pending journal;
- close/reopen retaining copies or confirmation;
- integer overflow, rounding, hidden clamping or an invented hard maximum;
- success wording or evidence claiming physical print from HTTP/browser state;
- generic catalog, packaging-line, reprint, label-layout or mobile behavior
  changing outside the approved FBS card.

Any unresolved path that can submit/render a run different from the displayed
`totalSheets`, any need for a schema/worker/external-contract change, or any
non-reconcilable unknown outcome returns `ARCH_REVIEW_REWORK` to S13 (and S02 if
traits change). S14 does not implement or accept this plan.

## Stop criteria and minimum rework closure

S18 must stop and return to the owning stage if one of these is discovered:

- the server cannot calculate one-copy pages without a live marketplace call;
- current assets/order markings cannot reconstruct a same-key result without
  storing sensitive print content in the operation journal;
- exact partial behavior cannot be represented by the fingerprint;
- an additive API contract cannot preserve known consumers;
- a migration, worker or marketplace-contract change is actually required;
- the existing UI-kit cannot express an approved visible state;
- the accepted server plan and rendered section count cannot be made identical.

Minimum closure is a revised resource graph plus contract that restores one
authoritative plan, server-enforced inclusive threshold, stale-plan rejection,
durable same-key behavior and an exact renderer postcondition. Dev must not
replace any missing closure with a local constant or a selected-count
multiplier.

## Final verdict

`ARCH_PLAN_READY`: one canonical server preflight owns the exact plan and
threshold, one fingerprint binds UI confirmation to commit, one durable
idempotency identity controls unknown outcomes, and one final renderer edge
applies independent copies exactly once while asserting that the physical page
document matches the total shown to the operator.
