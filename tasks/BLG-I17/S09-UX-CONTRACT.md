# S09 UX_CONTRACT_AND_MOCKUPS - BLG-I17

## Source and operator outcome

Backlog item `BLG-I17` removes a dead end in the existing FBS supply workspace.
An order can already be marked packed but remain outside every box. The supply
cannot be handed over until the discrepancy is fixed, yet the current screen
only shows an aggregate remainder. The operator needs to see every affected
order, put it into a suitable existing box, and immediately see whether the
supply is now ready for handover.

The changed zone is the existing `boxes` stage of the FBS supply workspace. It
does not create a separate recovery screen, change packing, create boxes
automatically, or change an already delivered supply.

## UX contract

### Source of the discrepancy

- A lost order is an order whose packing status is `packed` and whose ID is not
  present in `assigned_order_ids` of any box in the current workspace.
- The list contains each lost order once. It is not a product aggregate: the
  operator must be able to identify and assign a concrete WB order.
- The displayed count is the number of lost orders. It is not inferred from
  `total - assigned`, because that aggregate can include orders not yet packed.
- The supply readiness shown in the boxes stage is recalculated from the fresh
  workspace response after a successful assignment. The UI must not claim that
  the supply is ready based on an optimistic local decrement.

### Normal recovery flow

1. In the boxes stage, when at least one lost order exists, the operator sees a
   visible warning zone above the box list: `Не распределены по коробам: N`.
2. The zone contains a compact `DataTable` of the lost orders with columns
   `Заказ WB`, `Товар`, `Артикул / штрихкод`, and `Статус`. `Статус` is the
   warning `StatusChip` `Упакован, не в коробе`.
3. Every row has the action `Поместить в короб`. It opens the assignment
   `ModalDialog` with that exact order preselected; the operator chooses one of
   the existing editable boxes and confirms `Добавить в короб`.
4. The dialog repeats the WB order and product being moved, so confirmation
   cannot silently assign a similarly named product or another order.
5. After a confirmed successful assignment, the dialog closes, the workspace
   is reloaded, the lost-orders table and box contents are refreshed, and the
   readiness summary is recalculated from that response. A success notice says
   `Заказ <WB order> добавлен в короб <number>.`
6. If other lost orders remain, the warning zone stays open with the refreshed
   list and count. If none remain, the zone disappears and the readiness
   summary states `Все упакованные заказы распределены по коробам.`

Bulk selection is intentionally out of scope for this card. The operator fixes
one identifiable order at a time; the existing box action may retain its
separate product-quantity workflow for ordinary filling.

### Readiness and handover

- The header summary keeps `Распределено N из M` but labels the unresolved
  condition directly: `Не в коробах: N`. The count is based only on packed,
  unassigned orders.
- While a lost order exists, `Передать в WB` is unavailable. The adjacent
  explanatory text is `Распределите упакованные заказы по коробам перед
  передачей.` It must not promise that this is the only possible handover
  condition.
- Once the refreshed response reports no lost orders, this BLG-I17-specific
  restriction is removed. Other existing readiness checks still govern the
  handover action and may keep it unavailable with their own visible reason.
- An order may be assigned only while the supply is editable. After delivery is
  confirmed, rows remain visible for diagnosis but `Поместить в короб` is
  unavailable and says `Поставка уже передана; изменить состав коробов нельзя.`

### Required states

- **No discrepancy:** there are no packed unassigned orders. No warning table
  is rendered; the normal boxes view remains compact and says that all packed
  orders are distributed.
- **One or many lost orders:** the warning zone shows the exact rows, its count
  matches the rows, and every editable row has a direct recovery action.
- **Loading:** before the workspace response arrives, `TableSkeletonBody`
  occupies the warning-table body; actions and handover cannot use stale data.
- **No boxes:** the warning table remains visible. `Поместить в короб` opens a
  dialog state explaining `Сначала добавьте короб`, with `SecondaryAction`
  `Закрыть` and `PrimaryAction` `Добавить короб`, which returns focus to the
  existing create-box control. It does not create a box implicitly.
- **Assignment in progress:** the chosen row, its dialog fields and its
  confirmation action are unavailable until the request resolves, preventing a
  duplicate placement.
- **Assignment rejected or unknown:** `ErrorNotice` keeps the lost-order table
  unchanged and explains that the assignment was not confirmed; the operator
  can retry only after selecting a box again. The UI does not remove the row or
  reduce readiness locally.
- **Stale or forbidden:** if the response says the box or supply can no longer
  be edited, the dialog closes, the fresh workspace is shown, and the human
  explanation names the relevant condition. No local retry is submitted.
- **Partial recovery:** after one success in a multi-order list, processed and
  remaining orders are distinguishable through the refreshed list and the
  success notice; no row is silently treated as repaired.
- **Cancel:** closing the box-choice dialog creates no assignment and leaves
  the list, counts and current box contents unchanged.

## UI-kit mapping by zone

| Zone | Component and required use |
| --- | --- |
| Existing workspace frame | `ScreenShell`, `ScreenHeader`, `ScreenSection`, and `ToolbarLine`; BLG-I17 adds no page or nested card. |
| Readiness summary | `PlanFactCell` for `Распределено` and `Не в коробах`; `StatusChip` only for the resolved or blocked state, with no local colors. |
| Lost-orders warning zone | `ScreenSection` with `DataTable`; `TableSkeletonBody` while the workspace refreshes, `EmptyState` only when an explicit empty diagnostic result must be shown, and `ErrorNotice` for retrieval or assignment failure. |
| Lost-order row | `TextCell` for WB order and identifiers, `ProductCell` for product, and warning `StatusChip` for `Упакован, не в коробе`. |
| Row action | `ActionGroup` with `PrimaryAction` `Поместить в короб`; unavailable state must expose the business reason. `IconAction` is not a substitute for this named recovery action. |
| Box selection | `ModalDialog`, `SelectField` for an existing box, `TextCell` for the immutable order/product context, `SecondaryAction` `Отмена`, and `PrimaryAction` `Добавить в короб`. |
| Existing box controls | Existing `ActionMenu` and box actions remain separate; they are not repurposed to hide lost-order recovery. |

All visible controls in the touched zone use components exported by
`frontend/src/ui-kit/index.ts`. The current kit covers the contract, so no
`DESIGN_SYSTEM_GAP` blocker is required.

## Textual mockups

### A. Lost orders are actionable

```text
ScreenSection: Короба
  PlanFactCell: Распределено 8 из 10
  PlanFactCell: Не в коробах: 2

  ScreenSection / warning
    StatusChip: Требует действия
    DataTable: Упакованные заказы вне короба
      Заказ WB | Товар | Артикул / штрихкод | Статус | Действие
      12345678 | Футболка | ART-01 / 460... | Упакован, не в коробе | [Поместить в короб]
      12345679 | Носки    | ART-02 / 461... | Упакован, не в коробе | [Поместить в короб]

  [existing box list]
  Передать в WB: unavailable
  Распределите упакованные заказы по коробам перед передачей.
```

### B. Assignment confirmation

```text
ModalDialog: Поместить заказ в короб
  Заказ WB: 12345678
  Товар: Футболка, ART-01 / 460...
  SelectField: Короб [Короб 3]
  SecondaryAction: Отмена
  PrimaryAction: Добавить в короб
```

### C. No box and failed assignment

```text
ModalDialog: Некуда поместить заказ
  Сначала добавьте короб.
  SecondaryAction: Закрыть
  PrimaryAction: Добавить короб

ErrorNotice
  Заказ не добавлен в короб. Распределение не изменилось. Выберите короб и попробуйте ещё раз.
```

## Required review focus

- S10 verifies that the warning zone is visible before the handover command,
  does not cover box controls, and remains scannable with long product names
  and a narrow operator viewport.
- S10 verifies that a row identifies a concrete WB order, not just a product
  count, and that the chosen box is visible at confirmation.
- S11 confirms the product wording and whether non-packed orders participate in
  another pre-existing readiness rule; it may not turn the BLG-I17 list into a
  generic aggregate remainder.
- S15 must cover no discrepancy, one and multiple lost orders, no boxes,
  successful assignment with refreshed readiness, partial recovery, rejected
  or unknown request, delivered/non-editable supply, cancel, duplicate-submit
  prevention, long data, and narrow viewport.

## Out of scope

No implementation, API or data-model change, automatic box creation, product
aggregation, external marketplace call, deploy, secret access, or live-browser
acceptance is part of S09.

## S09 verdict

`UX_CONTRACT_READY`: the operator can find each packed order without a box,
choose an existing box for that specific order, and trust a refreshed readiness
result. The contract is concrete enough for S10 Design Review and S11 Product
Contract Approval.
