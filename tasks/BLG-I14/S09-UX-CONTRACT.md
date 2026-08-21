# S09 UX_CONTRACT_AND_MOCKUPS - BLG-I14

## Source and operator outcome

Backlog item `BLG-I14` prevents an operator from choosing delivery through a
Wildberries pickup point (PVZ) for a supply that contains orders whose stored
`can_pvz` value is `false`. The existing delivery-method flow remains the
entry point. This card adds no second shipping workflow and does not change the
supply composition.

Before the operator can confirm PVZ, the screen must evaluate every order in
the current supply. When one or more orders cannot be delivered through PVZ,
PVZ is not selected or confirmed. The operator sees the exact number of
blocking orders and can open their complete list, then choose an already
available eligible delivery method instead.

## UX contract

### Decision rule and operator-visible result

- The blocking set is every order in the current supply for which
  `can_pvz=false`. Its displayed count is the size of that set, not a rounded,
  loaded-page, or selected-row count.
- When the blocking set is empty, the existing PVZ choice and confirmation work
  unchanged. This card does not add a success message for the ordinary case.
- When the blocking set is non-empty, an attempt to choose or confirm PVZ opens
  the blocking dialog and leaves the currently selected delivery method
  unchanged. The PVZ confirmation command is unavailable; it must not submit a
  partial supply or silently switch to another method.
- The dialog headline and body use the exact current count, for example:
  `ПВЗ недоступен для 3 заказов` and `В поставке 3 заказа нельзя сдать через
  ПВЗ. Выберите другой способ сдачи.` The count uses the correct Russian form
  (`1 заказ`, `2 заказа`, `5 заказов`); the numeric value is always visible.
- The dialog list contains all and only blocking orders. Each row shows the
  stable order number and the status `Нельзя сдать через ПВЗ`. It must not
  infer a reason that is absent from the source data.

### Required states

1. **Eligible supply (success / normal).** All current orders have
   `can_pvz=true`; the existing PVZ option can be chosen and confirmed. No new
   table, banner, or success chip is shown.
2. **Mixed or ineligible supply (blocked).** At least one current order has
   `can_pvz=false`. PVZ cannot be selected or confirmed. The blocking dialog
   shows the exact count and list; closing it or choosing `Другой способ сдачи`
   makes no delivery request and retains the current supply.
3. **Long blocking list.** The dialog retains its headline count and presents
   all blocking orders in the `DataTable`; its existing pagination/scrolling
   behaviour is used so the count never becomes a count of visible rows.
4. **Check loading.** While the order eligibility set has not been resolved,
   PVZ confirmation is unavailable with a visible `Проверяем возможность сдачи
   через ПВЗ` state. The UI neither treats missing data as eligible nor opens a
   false blocking list.
5. **Eligibility-check error or unknown result.** PVZ confirmation remains
   unavailable. `ErrorNotice` says `Не удалось проверить возможность сдачи
   через ПВЗ. Попробуйте ещё раз.` A retry rechecks the same current supply;
   it does not submit or change the delivery method.
6. **Empty supply.** With no orders, the existing delivery-method action is
   unavailable. No blocking count or empty blocking dialog is shown, because
   there is no PVZ decision to make.
7. **Forbidden.** If the operator lacks the existing permission to change a
   delivery method, the current screen's forbidden state remains authoritative.
   This card does not reveal or enable PVZ confirmation through the dialog.
8. **Partial data / changed supply.** If the supply changes while the dialog is
   open or the eligibility result is incomplete, its prior count and list are
   discarded. The dialog closes or returns to loading, PVZ stays unavailable,
   and a fresh check is required before any confirmation. There is no partial
   PVZ confirmation.

### UI-kit mapping by zone

| Zone | Required component and use |
| --- | --- |
| Existing screen frame | `ScreenShell` and the existing `ScreenHeader`; BLG-I14 creates no new page header or card. |
| Existing delivery-method controls | The existing `ToolbarLine` and `ActionGroup` remain the action area. The PVZ command uses the existing method-selection control; its unavailable state is represented by the existing control, not a local imitation. |
| PVZ check state | `StatusChip` with a neutral processing state beside the affected action while eligibility is loading. It is not used to claim a confirmed delivery result. |
| Blocking explanation and list | `ModalDialog` containing `DataTable`. The table uses `TextCell` for `Номер заказа` and `StatusChip` for `Нельзя сдать через ПВЗ`; its row data is the complete `can_pvz=false` set. |
| Dialog actions | `SecondaryAction` `Закрыть` and `SecondaryAction` `Другой способ сдачи`. Neither action confirms PVZ or changes the delivery method automatically. |
| Failed eligibility check | `ErrorNotice` with the human-readable retry message. |
| Empty and forbidden states | Existing `EmptyState` and the current permission/forbidden presentation remain unchanged; no local replacement is allowed. |
| Filters, tabs and menus | `FilterBar`, `TabsBar`, and `ActionMenu` are not touched. |

All visible controls in the touched zone use components exported by
`frontend/src/ui-kit/index.ts`. The contract needs no missing component and
therefore has no `DESIGN_SYSTEM_GAP` blocker.

## Textual mockups

### A. Supply eligible for PVZ

```text
ScreenShell
  [existing ScreenHeader and supply orders DataTable]
  ToolbarLine / ActionGroup
    [existing PVZ delivery-method command: available]
```

No extra status is added: PVZ is simply available when every order is eligible.

### B. PVZ blocked by part of the supply

```text
ModalDialog: "ПВЗ недоступен для 3 заказов"
  "В поставке 3 заказа нельзя сдать через ПВЗ. Выберите другой способ сдачи."

  DataTable
    Номер заказа                 Статус
    WB-123456                    [Нельзя сдать через ПВЗ]
    WB-123457                    [Нельзя сдать через ПВЗ]
    WB-123458                    [Нельзя сдать через ПВЗ]

  SecondaryAction: "Закрыть"
  SecondaryAction: "Другой способ сдачи"
```

The list example contains three rows solely to show the count-to-list binding;
production values come from the current supply. The dialog cannot contain a
PVZ confirmation action.

### C. Check is loading or cannot be completed

```text
ToolbarLine / ActionGroup
  [PVZ confirmation: unavailable]
  StatusChip: "Проверяем возможность сдачи через ПВЗ"

ErrorNotice
  "Не удалось проверить возможность сдачи через ПВЗ. Попробуйте ещё раз."
```

Only one of the loading chip and error notice is shown for a given check.

## Required review focus

- S10 checks that the exact count remains visible with a long list and a narrow
  warehouse viewport, and that the modal does not cover the only route to an
  eligible alternative.
- S10 checks scanner-first flow: no extra data entry is introduced, and the
  operator can leave the dialog without losing the supply or a valid current
  method.
- S11 confirms the wording, operator rationale, and ownership of the
  `can_pvz` truth source; it may refine the existing alternative-method flow
  but may not permit partial PVZ confirmation.
- S15 must cover zero blockers, one blocker, multiple blockers, a long list,
  exact count/list agreement, loading, failed/unknown check, empty supply,
  forbidden permission, supply change while open, retry, close, and no partial
  delivery request.

## Out of scope

No implementation, API/data-contract change, delivery submission, live
Wildberries call, deployment, secret access, or live-browser acceptance is part
of S09.

## S09 verdict

`UX_CONTRACT_READY`: the changed operator flow, every required visible state,
textual mockups, exact count/list rule, and UI-kit components are concrete
enough for independent Design Review and Product Contract approval.
