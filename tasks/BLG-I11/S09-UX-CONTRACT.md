# S09 UX_CONTRACT_AND_MOCKUPS - BLG-I11

## Source and operator outcome

Backlog item `BLG-I11` adds an explicit exception for a supply when some of its
orders have unfilled Честный Знак (ЧЗ) marking codes. Today the only route is a
manual data intervention, which hides both the operational risk and the person
who accepted it.

The operator must be able to see exactly which orders are affected, understand
that continuing is an exception, give a reason, and explicitly confirm it. The
exception applies to the supply, not to individual scanned codes: an existing
scanned code is never removed, ignored, or replaced by this flow.

This is not a definition of when ЧЗ is required, which role is authorised, or
what external circulation outcome follows. Those decisions remain blocked by
`BLK-PROD-001` until the Product oracle for `requiredMeta`, `optionalMeta`, and
`sgtinApplied` is approved.

## UX contract

### Entry and permission boundary

- The changed zone is the existing supply workspace. BLG-I11 creates no new
  page, separate exception register, or parallel shipping flow.
- When the current supply has one or more orders with unfilled marking codes,
  the actions area exposes `Пропустить маркировку` only as the explicit
  exception entry point. It must not run automatically as part of packing,
  scanning, or the usual continue action.
- The action is available only after the server has confirmed that the current
  user has the Product-approved permission. This contract intentionally does
  not assign a role name, permission key, approval chain, or fallback person.
- A user without that permission sees the action unavailable with the reason:
  `Пропуск маркировки доступен только уполномоченной роли.` The interface does
  not suggest changing data, retrying under another account, or bypassing the
  restriction.
- If the supply has no affected orders, the action is unavailable with the
  reason: `В этой поставке нет заказов с незаполненной маркировкой.`

### Confirmation and retained data

1. An authorised user opens `Пропустить маркировку` for the current supply.
2. A confirmation dialog names the supply and shows an affected-orders table.
   Each row is an order affected by the unfilled marking code; the normal
   supply contents and any already scanned codes remain outside this exception
   list and unchanged.
3. The dialog gives the operator the warning:
   `В выбранных заказах не заполнена маркировка. Продолжение будет явным
   исключением по этой поставке и будет зафиксировано для проверки.`
   It also states: `Уже отсканированные коды не изменятся.`
4. The operator enters a non-empty reason in `Причина пропуска`. The final
   command remains unavailable until a reason is present.
5. The final danger action is `Подтвердить пропуск`. It records the supplied
   reason and the acting user through the future backend contract, then allows
   the supply to continue only if the server accepts the exception.
6. Closing or cancelling the dialog creates no exception and leaves the supply,
   affected-order list, and scanned codes unchanged.

The contract does not prescribe the reason taxonomy, minimum length, audit
retention period, permission implementation, or the source of the affected
orders. Those are Product/oracle and later API decisions, not local UI policy.

## UI-kit mapping by zone

| Zone | Component and required use |
| --- | --- |
| Existing supply frame | Existing `ScreenShell` and `ScreenHeader` remain. BLG-I11 adds no duplicate header or page. |
| Supply actions | `ToolbarLine` with `ActionGroup`; the exception entry is `DangerAction` `Пропустить маркировку`. Its unavailable states use `disabledReason`, never a hidden bypass. |
| Existing supply contents | Existing `DataTable` remains the normal supply view. Its order rows and scanned-code presentation are not altered by this card. |
| Exception confirmation | `ModalDialog` titled `Пропустить маркировку` with `SecondaryAction` `Отмена` and `DangerAction` `Подтвердить пропуск`. |
| Affected orders | `DataTable` inside the dialog lists only affected orders. The exact business columns are inherited from the existing order identity presentation; at minimum each row identifies the affected order without exposing a scanned code as missing. |
| Reason and validation | `TextInput` for `Причина пропуска`; its inline validation explains that a reason is required before confirmation. |
| Feedback | `ErrorNotice` reports an unconfirmed request in plain warehouse language. `StatusChip` may show a server-confirmed exception state only after the request succeeds; it must not imply that missing codes were scanned or validated. |
| Filters, tabs and menu | `FilterBar`, `TabsBar`, and `ActionMenu` are not changed. No local substitute is permitted. |

All visible controls in the changed zone map to existing exports from
`frontend/src/ui-kit/index.ts`. No new UI-kit component is needed, therefore
S09 has no `DESIGN_SYSTEM_GAP` blocker.

## Textual mockups and states

### A. Affected supply, authorised user

```text
ScreenShell
  [existing ScreenHeader and supply DataTable]
  ToolbarLine / ActionGroup
    DangerAction: "Пропустить маркировку"

ModalDialog: "Пропустить маркировку"
  "В выбранных заказах не заполнена маркировка. Продолжение будет явным
   исключением по этой поставке и будет зафиксировано для проверки."
  "Уже отсканированные коды не изменятся."
  DataTable: affected orders only
  TextInput: "Причина пропуска" [                         ]
  SecondaryAction: "Отмена"
  DangerAction: "Подтвердить пропуск" (unavailable until reason is present)
```

### B. Forbidden or not applicable

```text
ToolbarLine / ActionGroup
  DangerAction: "Пропустить маркировку" (unavailable)
  Tooltip, forbidden: "Пропуск маркировки доступен только уполномоченной роли."

ToolbarLine / ActionGroup
  DangerAction: "Пропустить маркировку" (unavailable)
  Tooltip, no affected orders: "В этой поставке нет заказов с незаполненной маркировкой."
```

The disabled control makes the restriction and the absence of affected orders
observable without offering a route around either state.

### C. Invalid, cancelled, loading, error and success

```text
TextInput: "Причина пропуска" [ ]
  "Укажите причину пропуска"
DangerAction: "Подтвердить пропуск" (unavailable)

ModalDialog while request is pending
  DangerAction: "Подтвердить пропуск" (unavailable; no second submission)

ErrorNotice
  "Пропуск маркировки не подтверждён. Поставка не изменена. Проверьте данные и повторите действие."

After server-confirmed success
  StatusChip: server-confirmed exception state
  Existing supply flow remains visible; affected orders are not silently removed.
```

- **Loading:** the affected-order list uses the existing table loading treatment;
  confirmation is unavailable until the list and permission result are known.
- **Empty:** no affected orders means no confirmation dialog and the explicit
  unavailable reason above. A response that cannot establish the list is an
  error, not an empty state.
- **Error:** a failed or unknown confirmation keeps the supply unchanged in the
  UI and shows `ErrorNotice`; no automatic retry is sent.
- **Forbidden:** the server's permission result controls availability. The UI
  never treats a hidden or stale client flag as authorisation.
- **Partial:** a response that cannot confirm the exception for every affected
  order is not rendered as a completed supply exception. It remains an error
  until the later Product/API contract defines a truthful partial state.
- **Repeat:** while a confirmation is pending, a second confirmation cannot be
  sent. On reload or retry, only a server-confirmed state may be displayed as
  complete; the UI must not infer completion from a prior click.
- **Cancel:** Escape, close, or `Отмена` dismisses the dialog without changing
  the supply or scanned codes. Reopening starts from the current server data.

## Required review focus

- S10 checks that the danger action and confirmation are recognisable as a
  supply-level exception, fit the scanner-first workspace, and do not obscure
  the existing scan/packing path or long order identifiers.
- S10 checks narrow viewport, long affected-order lists, loading, empty,
  error, forbidden, partial, cancel, and reload/repeat presentation.
- S11 must approve the actual authorised role/permission, when a code is
  considered unfilled, the precise risk/consequence wording, reason rules,
  audit record, and server outcome. It may reject or revise this contract; S09
  does not resolve `BLK-PROD-001`.
- S15 must cover unauthorised access, no affected orders, reason required,
  cancel, pending double-submit prevention, server rejection/unknown outcome,
  read-back after success, and proof that scanned codes remain intact.

## Out of scope

No implementation, API or worker change, permission-policy decision, oracle
decision, database/audit schema decision, marketplace call, deployment, secret
access, or live-browser acceptance is part of S09.

## S09 verdict

`UX_CONTRACT_READY`: the visible exception flow, warning, confirmation,
permission boundary, and all required states are concrete and use existing
UI-kit components. `BLK-PROD-001` remains open for the later Product/oracle
decision; this verdict neither resolves it nor authorises implementation.
