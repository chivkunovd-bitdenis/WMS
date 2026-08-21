# S11 PRODUCT_CONTRACT_APPROVAL - BLG-I04

## Product decision

Product approves the existing FBS print action with one independent copies
value and an exact preflight sheet total. The operator's selection defines
which labels are required; it never defines how many copies of those labels
must be printed.

Every newly opened print action starts with one copy of each required label.
The product invariant is:

```text
totalSheets = sheetsPerOneCopy * copiesPerRequiredLabel
```

`sheetsPerOneCopy` comes from the existing print layout for the selected
printable items. `copiesPerRequiredLabel` is the single operator-editable
positive integer and defaults to `1`. The selected order count must not be
written into, copied into, or multiplied again as the copies value.

The exact `totalSheets` shown before submission is the print run the system
must attempt to create. If the current selection, layout result or copies value
changes, the total must be recalculated before submission. A mismatch between
the visible total and the job that would be created fails closed: no print job
is submitted until the operator sees the current total.

## Large-run policy

The approved large-print threshold is **100 sheets, inclusive**:

```text
largePrintThresholdSheets = 100
largePrintRun = totalSheets >= 100
```

The threshold is a central WMS Product policy for this flow. It is not editable
by an operator, does not vary by user or browser session, and must not be
invented separately by individual screens. This card does not add an admin
setting; any future change to the threshold is a versioned product decision.

The rationale is operational: a routine run below 100 sheets remains one-step,
while the common accidental squaring case of ten selected labels and ten copies
already reaches 100 and receives a deliberate second check. A legitimate run
of 100 or more sheets is allowed after confirmation; this contract adds no hard
maximum that could block planned warehouse work.

## Approved operator journey

1. The operator keeps the current selected orders and opens the existing print
   action for the concrete printable item.
2. The copies field opens with `1`. The form separately shows the number of
   selected orders and `К печати: N листов`; the latter is the authoritative
   preflight total.
3. Invalid copies - empty, zero, negative, fractional or non-numeric - disable
   submission and show the inline instruction to enter a whole number greater
   than zero.
4. For `totalSheets < 100`, the primary action submits the currently displayed
   run directly.
5. For `totalSheets >= 100`, the first action creates no job. It opens the S09
   confirmation dialog with the same total and requires the explicit action
   `Печать N листов`.
6. Cancel, Escape or close creates no job and preserves the entered copies
   value. A changed selection, layout result or copies value invalidates the
   prior confirmation and requires confirmation of the recalculated total.
7. While recalculation or submission is in progress, a second submission is
   unavailable. A rejected or unknown result is not retried automatically; the
   operator first sees the unchanged current total and deliberately retries.

The separate selection count explains scope, the copies field expresses the
operator's intent, and the sheet total exposes the physical cost before paper
and printer time are consumed. The large-run dialog exists only to confirm an
unusual physical volume; it must not become a second place to edit quantity.

## Operational result and wording

- With ten selected one-sheet labels and untouched default copies, the job is
  ten sheets, not one hundred.
- With ten selected one-sheet labels and copies explicitly changed to ten, the
  preflight total is one hundred and confirmation is required.
- Multi-page layouts remain valid because the total uses the layout-calculated
  `sheetsPerOneCopy`, not an assumption that one order always equals one sheet.
- Opening a new print action, including a later repeat-print action, starts
  again at one copy. A previous unusual copies value is never carried silently
  into a new run.
- Success wording may state that the request or job was accepted/sent. It must
  not claim that paper was physically printed without printer evidence.
- An unknown request outcome must say that the job was not confirmed. It must
  not claim that nothing reached the printer and must not silently duplicate
  the request.

No selected orders, printable items, row-selection behavior, table columns,
filters, tabs or menus change under this contract. The UI-kit mapping and
textual states in `S09-UX-CONTRACT.md` are approved as the operator surface.

## Required downstream proof

S15 must preserve the S09 cases and add explicit boundary and invariant proof:

- default one copy for one, ten and at least one multi-page selection;
- selected count and copies remain independent in the print request;
- totals of 99 sheets print directly, while 100 sheets and larger require
  confirmation;
- ten selected one-sheet labels at default copies produce ten sheets;
- ten selected one-sheet labels at ten copies produce 100 sheets and require
  confirmation;
- invalid quantity, no printable selection and recalculation-in-progress create
  no job;
- cancel and stale confirmation create no job;
- repeated submit, timeout, rejected request and unknown outcome do not create
  an automatic duplicate;
- reload or reopening the action resets copies to one and recalculates the
  total from current printable items;
- printer or approved-device evidence proves the requested content, layout,
  size and copy count required by the `print` trait.

S22, S23 and S25 must compare the visible preflight total, the accepted print
job and printer/device evidence for the same run. Browser acceptance alone does
not prove physical output, and printer evidence without the operator preflight
does not prove this product contract.

## Out of scope

S11 does not approve code, API or worker design, a new printing workflow, a new
screen, an operator-configurable threshold, a hard print cap, changes to label
content or layout, automatic retry, commit, push, deploy, secret access, live
WB/Ozon calls or production printer operations.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: one copy of every required label is the default,
the operator sees the exact calculated sheet total before submission, and every
run of 100 sheets or more requires an explicit confirmation tied to the current
selection, layout and copies value.
