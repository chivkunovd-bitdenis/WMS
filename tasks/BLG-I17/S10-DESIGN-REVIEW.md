# S10 DESIGN_REVIEW - BLG-I17

## Review scope

Role: `pipeline-product`
Model policy: `gpt-5.6-sol` / `expensive`
Reviewed input: `tasks/BLG-I17/S09-UX-CONTRACT.md`
Canon: `docs/product/UX_CANON_RU.md`

The review covers the operator path for a packed WB order that is not assigned
to any box: finding the exact order, selecting a box, confirming the assignment,
reading back fresh workspace state, recalculating readiness, and keeping the
recovery action clear in long-data and narrow-viewport states.

## What is accepted in the direction

- The discrepancy is defined by concrete order IDs, not by a product aggregate
  or `total - assigned` arithmetic.
- The operator assigns one identifiable WB order to one explicitly selected
  existing box; the dialog repeats the order and product context.
- A successful assignment is intended to refresh the workspace and recalculate
  readiness from server state rather than by optimistic local decrement.
- No-box, delivered/non-editable, loading, assignment-in-progress, partial,
  cancel, and ordinary failure states are named.
- The recovery action is placed before the handover command and does not hide
  inside the existing box menu.

## Blocking design findings

### 1. The warning zone is a nested card

The component mapping says the existing boxes stage uses `ScreenSection`, then
assigns another `ScreenSection` to the lost-orders warning. Mockup A repeats the
same nesting. This contradicts its own statement that BLG-I17 adds no nested
card and violates canon R-01: a card inside a card is a defect. It also spends
scarce vertical space before the existing box controls.

Required S09 rework: keep one existing `ScreenSection` for the boxes stage and
render the warning heading/status plus `DataTable` as an unframed zone inside
it, separated by the existing layout primitives. Do not add a second outlined
container.

### 2. The ui-kit mapping does not match the actual component contracts

The column `Артикул / штрихкод` joins two identifiers although canon R-10 and
the `ProductCell` contract require distinct entity columns. `ProductCell`
accepts only photo plus SKU and therefore does not represent the free-form
product-name cell described by the mockup. `PlanFactCell` accepts only
`fact`/`plan`; it can render `Распределено 8 из 10`, but it cannot render the
independent labelled fact `Не в коробах: 2` as specified.

Required S09 rework: name separate fixed-width columns for product, seller
article and barcode using components according to their actual props. Map the
distributed plan/fact pair to `PlanFactCell`; map the independent lost-order
count to a suitable existing numeric/text primitive. If no existing primitive
can express the approved summary without local layout, declare
`DESIGN_SYSTEM_GAP` instead of claiming full kit coverage.

### 3. Successful write without confirmed read-back is unsafe

The contract reloads after a successful assignment, but it has no distinct
state for: the write is accepted, then workspace reload fails; or the write
outcome is unknown, then read-back is unavailable. The current generic error
state keeps the old row and permits retry after choosing a box again. That can
submit a duplicate assignment and can show stale readiness, contrary to the
freshness rule and canon R-24.

Required S09 rework: success and recalculated readiness may be shown only after
a fresh workspace response confirms that the exact order belongs to the chosen
box and is absent from the lost-order list. Until that read-back succeeds,
disable handover and repeat assignment for that order, preserve an explicit
`ErrorNotice`, and offer only a workspace refresh/reconciliation action. Define
the operator text for both accepted-write/read-back-failed and unknown-write
outcomes.

### 4. The narrow-viewport mockup does not preserve the direct recovery action

The proposed table has long product data plus identifier, status, and action
columns. `ActionGroup` gives its button a 168 px minimum width, while the action
is the last column. The contract asks S10 to verify a narrow viewport but does
not define column widths, truncation, scroll behavior, or how the operator can
still discover `Поместить в короб`. The supplied text mockup cannot demonstrate
that the action remains usable without covering box controls.

Required S09 rework: add an explicit long-data/narrow-viewport mockup with
fixed column widths, `TextCell` truncation plus full-value tooltip, non-wrapping
headers/buttons per R-36, and the direct row action reachable without overlap.
State whether the table scrolls horizontally and where the action sits in that
reading order.

## Re-review acceptance

S10 can approve after S09 resolves all four findings while preserving the exact
lost-order list, explicit box confirmation, non-optimistic readiness, other
existing handover checks, and the no-implicit-box rule. No implementation,
external marketplace call, deploy, secret access, or live-browser acceptance is
part of this verdict.

## Verdict

`DESIGN_REWORK`: return to S09. The route is deterministic and needs no owner
decision; the blocking findings are design-contract defects with stated
operator impact and correction criteria.
