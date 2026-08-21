# S09 UX_CONTRACT_AND_MOCKUPS - BLG-I04

## Source and operator outcome

Backlog item `BLG-I04` fixes the case where the count of selected orders is also
used as the number of copies. The resulting print run is squared: for example,
10 selected orders can become 100 sheets. The operator must see one independent
copy quantity, defaulted to `1`, and the exact number of sheets that will be sent
before the print job is created.

The changed zone is the existing FBS print action. It does not create a new
screen, change the selected orders, or add a second printing workflow.

## UX contract

### Independent quantities

- `selectedOrders` is a read-only selection context. Its count is never used as
  the number of copies.
- `copiesPerRequiredLabel` is the only editable print quantity. It is a positive
  integer and opens with value `1` for every new print action.
- `sheetsPerOneCopy` is calculated by the existing print layout from the current
  selected printable items. `totalSheets = sheetsPerOneCopy * copiesPerRequiredLabel`.
  The UI shows the resulting `totalSheets`, not a multiplication based only on
  the order count. This preserves multi-page layouts while removing the
  accidental squaring.
- Editing the copy quantity or changing the current selection recalculates the
  displayed total before the operator can start printing.

### Normal print

1. The operator opens the existing print action for the current selection.
2. The quantity field contains `1`; the summary states both the selection and
   the result, for example: `Выбрано заказов: 10` and `К печати: 10 листов`.
3. With a total below the large-batch threshold, the operator starts printing
   directly. The print request contains the displayed quantity and has one copy
   per required label by default.
4. A successful request may report that the job was sent, but that status must
   not claim that physical printing completed.

### Quantity validation and unavailable action

- Empty, zero, negative, fractional or non-numeric quantity is invalid. The
  primary print command is unavailable until the field contains a positive
  integer, and the inline reason tells the operator to enter a whole number
  greater than zero.
- With no printable selected items, `PrintAction` is unavailable with the reason
  `Нет выбранных этикеток для печати`; no quantity dialog is opened.
- While the sheet total is recalculating or a print request is being sent, the
  initiating command cannot submit a second request.
- If the request is rejected or its outcome is unknown, `ErrorNotice` explains
  that the job was not confirmed and offers a safe retry only after the operator
  sees the unchanged total again. The screen must not silently submit another
  job.

### Large-batch confirmation

`largePrintThresholdSheets` is a product-configured number of sheets. It is not
defined by the BLG-I04 source, so S11 must approve its value and ownership; S18
must not invent a local threshold. Until then, this contract defines the state
as `totalSheets >= largePrintThresholdSheets`.

When that state is true, the first print command opens a confirmation dialog
instead of creating the job. The dialog repeats the same total that was visible
in the form and requires an explicit second action. Cancelling or closing the
dialog creates no job and retains the entered quantity. If the selection or
quantity changes while the dialog is open, its total is recalculated; an
out-of-date confirmation cannot print the old count.

## UI-kit mapping by zone

| Zone | Component and required use |
| --- | --- |
| Existing screen shell | `ScreenShell` and existing `ScreenHeader`; BLG-I04 adds no separate screen or page header. |
| Existing selected-orders table | Existing `DataTable` remains the selection source. Its row selection and columns are not changed by this card. |
| Print actions | `ToolbarLine` with `ActionGroup`; the initiating command is the existing `PrintAction` with the concrete `Printable` name, never a generic `Печать`. |
| Quantity form and total | `TextInput` for `Количество копий`, constrained to a positive integer; `QtyCell` for the right-aligned read-only totals `Выбрано заказов` and `К печати`. |
| Status and request feedback | `StatusChip` only for a job/request state when the parent screen already exposes it; `ErrorNotice` for a rejected or unknown request result. No success chip may imply a paper output. |
| Large-batch confirmation | `ModalDialog` with `SecondaryAction` `Отмена` and `PrimaryAction` `Печать N листов`; `N` equals the current displayed total. |
| Tabs, filters and menus | `TabsBar`, `FilterBar` and `ActionMenu` are not touched. No local substitute is allowed. |

All visible controls in the changed zone use the listed components from
`frontend/src/ui-kit/index.ts`. The contract requires no missing component, so
there is no `DESIGN_SYSTEM_GAP` blocker.

## Textual mockups

### A. Usual batch, default one copy

```text
ScreenShell
  [existing ScreenHeader and selected-orders DataTable]
  ToolbarLine / ActionGroup
    PrintAction: "Печать <конкретный Printable>"

  Print quantity area
    TextInput: "Количество копий" [ 1 ]
    QtyCell: "Выбрано заказов: 10"
    QtyCell: "К печати: 10 листов"
    Primary print command: "Печать 10 листов"
```

The primary command sends one copy of every required label. `10` in the example
is a calculated sheet total, not a second copies value.

### B. Large batch requires confirmation

```text
ModalDialog: "Подтвердить печать"
  "К печати: 240 листов. Проверьте тираж перед отправкой на принтер."
  SecondaryAction: "Отмена"
  PrimaryAction: "Печать 240 листов"
```

`Отмена`, Escape, or closing the dialog returns to the quantity area without
creating a job. Only the explicit primary action submits the displayed total.

### C. Invalid quantity or failed request

```text
TextInput: "Количество копий" [ 0 ]
  "Введите целое число больше нуля"
Primary print command: unavailable

ErrorNotice
  "Печать не подтверждена. Тираж не отправлен повторно. Проверьте 10 листов и попробуйте ещё раз."
```

## Required review focus

- S10 checks that the quantity field, two counts, and print command fit the
  scanner-first operator flow without obscuring the selected orders.
- S10 checks long totals, a narrow operator viewport, and that the concrete
  print label follows the `Printable` naming rule.
- S11 approves `largePrintThresholdSheets`; it may refine copy policy, but may
  not reintroduce selection count as a default number of copies.
- S15 must cover default `1`, a multi-page layout total, a changed quantity,
  boundary-at-threshold confirmation, cancel, stale-confirmation recalculation,
  invalid quantity, unavailable no-selection action, and an unknown request
  result without duplicate submission.

## Out of scope

No print implementation, API or worker change, printer operation, deploy,
external marketplace call, secret access, or live-browser acceptance is part of
S09.

## S09 verdict

`UX_CONTRACT_READY`: the visible states are concrete, use existing UI-kit
components, and leave the only missing product value - the large-batch threshold
- explicitly for S11 approval.
