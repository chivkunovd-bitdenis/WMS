# S09 UX_CONTRACT_AND_MOCKUPS — BLG-I12

## Source and operator outcome

Backlog item `BLG-I12`: «Предупреждать о закрытии с несохранёнными изменениями».

Оператор может открыть рабочую форму или модальное окно, начать ввод и по привычке закрыть его крестиком, клавишей Escape либо кликом по фону. Если подтверждённые данные ещё не сохранены, система не закрывает рабочий контекст молча: она предлагает остаться, сохранить данные или выйти без сохранения. Уже сохранённые данные этот сценарий не меняет.

## Scope and dirty rule

Контракт применяется ко всем существующим и новым редактируемым формам, включая формы внутри `ModalDialog`. Не применяется к просмотру без полей ввода, закрытию формы без изменений и к форме, чьё успешное сохранение уже завершилось.

Форма считается изменённой, когда хотя бы одно редактируемое поле имеет значение, отличающееся от исходного значения при открытии формы или последнего успешно сохранённого значения. Возврат всех полей к этому исходному значению снова делает форму чистой. Ошибка сохранения и незавершённое сохранение не сбрасывают признак изменений.

## UI-kit composition by zone

| Zone | Required ui-kit components | Purpose |
| --- | --- | --- |
| Existing screen or work area | `ScreenShell`, `ScreenHeader`, `ScreenSection`, `ToolbarLine` | Existing form keeps its normal operator context; this task does not introduce a new screen or panel. |
| Editable form | `TextInput`, `SelectField`, `CheckboxField`, `TabsBar` when the existing form uses these controls | The entered values remain visible and editable until a final exit or successful save. |
| Form actions | `ActionGroup`, `PrimaryAction`, `SecondaryAction`, `IconAction`, `ActionMenu` when the existing surface has those actions | Save stays the primary action; ordinary close/cancel starts the exit decision only for a dirty form. |
| Unsaved-changes confirmation | `ModalDialog`, `SecondaryAction`, `PrimaryAction`, `DangerAction` | A single confirmation on top of the still-open dirty form makes the consequence and three possible actions explicit. |
| Validation or save failure in the form | `ErrorNotice` | The form remains open with entered values; an error is not interpreted as a successful save or exit. |

No local button, dialog, overlay, colour or table implementation is permitted. `ModalDialog` and its supplied action types cover the confirmation; therefore no `DESIGN_SYSTEM_GAP` blocker is needed for S09.

## Concrete mockups and interaction contract

### A. Clean form: close immediately

The operator uses the form's visible close/cancel action, Escape, or the overlay click permitted by the existing modal. When the form is clean, the form closes immediately. No confirmation is shown and no value is written or removed by this task.

### B. Dirty form: request to close

For each of the following requests on a dirty form, keep the form open and open one `ModalDialog` above it:

1. Visible close/cancel action, including an `IconAction` close control.
2. Escape.
3. Click on the overlay outside the form modal.
4. A close or back action selected from the form's `ActionMenu`, where that action already exists.

The confirmation has the title `Есть несохранённые изменения` and the text `Изменения в форме не сохранены. Сохранить их перед выходом?`.

Its action order is fixed:

1. `SecondaryAction` `Остаться` is the non-destructive default. It closes only the confirmation and returns focus to the same dirty form and its values.
2. `PrimaryAction` `Сохранить` starts the form's existing save operation. It is enabled only when the form can currently be saved; otherwise `disabledReason` says what must be corrected. The form and confirmation remain present until the save result is known.
3. `DangerAction` `Выйти без сохранения` closes the confirmation and the original form, discarding only the values changed since the saved/open baseline.

The confirmation itself does not close on Escape or overlay click. Those events leave it open, so a repeated accidental gesture cannot discard data. If the form has its own close icon, it is visually inactive behind the confirmation and cannot create a second confirmation.

### C. Save result from the confirmation

On successful save, the confirmation closes, the form's dirty state is reset to the newly saved values, and the original close request completes: the form closes and the operator returns to the same screen/list position that initiated it.

On validation failure or transport/server failure, the confirmation closes, the original form remains open and dirty, and `ErrorNotice` explains the recoverable problem in warehouse language. No entered value is cleared, and the operator can correct the form and save again or request exit again.

If save is already in progress, all three confirmation actions are disabled until that attempt resolves. Repeating Escape, overlay click, or a close action during this period must neither start a second save nor close the form.

### D. Nested modal case

When the dirty form is itself inside a `ModalDialog`, the confirmation is a second `ModalDialog` above it. The underlying form modal stays mounted and retains focus-return target and field values. `Остаться` returns focus to the control that initiated the close when that control still exists; otherwise it returns focus to the first invalid field, or the first editable field. `Выйти без сохранения` closes both dialogs in one final action. This avoids leaving an orphan overlay or a hidden dirty form.

## Required states for later review and cases

| State | Visible result | Data result |
| --- | --- | --- |
| Clean close | Form closes without a confirmation. | No unsaved data exists. |
| Dirty close request | Confirmation with `Остаться`, `Сохранить`, `Выйти без сохранения` is visible. | Original form and all entered values remain intact. |
| Stay | Confirmation disappears; original form is active again. | No value changes. |
| Save succeeds | Form closes after the save response succeeds. | Existing save contract persists values once; no duplicate save. |
| Save fails | Original form remains with `ErrorNotice`. | Entered values remain dirty and editable. |
| Exit without saving | Confirmation and original form close. | Only unsaved edits are discarded; prior saved data is unchanged. |
| Escape/overlay on confirmation | Confirmation remains visible. | No save and no discard. |
| Repeated close while confirmation/save pending | Only one confirmation or one save attempt exists. | No duplicate discard or save. |

## Acceptance notes for S10

Design review must verify that the confirmation is only shown for a dirty form; that all three entry gestures lead to the same confirmation; that destructive exit is visually and semantically distinct from staying and saving; and that the underlying modal does not close behind the confirmation. It must also verify the Russian labels, action order, focus return, disabled-save explanation, narrow viewport wrapping, and that the dialog uses only the listed ui-kit components.

## Out of scope

This stage does not implement dirty tracking, change API contracts, create a new screen, run browser acceptance, deploy, contact WB/Ozon, or operate secrets.

## S09 verdict

`UX_CONTRACT_READY`: the UX contract specifies the concrete operator states, all requested close paths, nested-modal behaviour, and existing ui-kit components for S10 Design Review.
