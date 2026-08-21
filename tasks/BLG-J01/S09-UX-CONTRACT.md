# S09 UX_CONTRACT_AND_MOCKUPS - BLG-J01

## Source and operator outcome

Backlog item `BLG-J01` addresses the marking-code tail already displayed beside
the product in the FBS order metadata scan dialog. A bare six-character value
looks like damaged scan data or screen noise. When the scanned identifier is a
KIZ (the product marking code), the operator must instead see exactly what the
short value means: the final six symbols of that KIZ.

This is a labeling-only UI change. It does not change what a scanner accepts,
how the marking code is parsed or stored, the scan request, order status, or
the quantity of codes required for the order. The scan field remains the only
active control in the scan flow.

## Scanner-first interaction contract

1. The existing scan dialog opens with its existing active `ScannerLine` and
   focused `TextInput` for the next code. The dialog does not add a new screen,
   a confirmation, or a second field.
2. After a KIZ scan is accepted by the existing flow, the product area shows
   the human-readable label `Последние 6 символов КИЗ:` followed by the exact
   six-symbol tail returned for that KIZ, for example `A1B2C3`.
3. The label and tail are read-only contextual information, not a chip, button,
   filter, status, or value the operator must copy. They appear in the same
   product context as the existing bare tail, immediately below the product
   identity, so they can be checked at a glance without competing with the
   scan field.
4. Rendering this context never interrupts the scan cadence: no focus move,
   toast, animation, dialog re-open, deliberate timeout, or acknowledgement is
   introduced. Once the existing scan result is processed, focus returns to
   the same scan `TextInput` under the existing flow; the next scanner input
   can be read immediately.
5. A repeated accepted scan follows the existing idempotency and duplicate
   rules. Its product context may refresh, but BLG-J01 does not add another
   warning or action solely because the six-symbol tail is already visible.

## Visible states and content rules

| State | Visible result | Scanner and data result |
| --- | --- | --- |
| Accepted KIZ with a six-symbol tail | `Последние 6 символов КИЗ: A1B2C3` appears below the matching product identity. | Existing accepted-scan result only; scan input remains ready for the next code. |
| KIZ response still loading or next scan is being submitted | The last confirmed product context remains stable; no placeholder replaces the tail and no new blocking state is introduced. | Existing busy protection may prevent a duplicate request, but must not lose the pending or next scan focus when it resolves. |
| Accepted non-KIZ identifier, or product has no displayable KIZ tail | No KIZ-tail label is shown. In particular, UIN, IMEI and GTIN are not relabelled as KIZ. | Existing identifier-specific result is unchanged. |
| Rejected, malformed, duplicate-as-error, or transport-failed scan | The existing `ErrorNotice` remains the only error feedback. No tail from the rejected raw input is shown as confirmed. | Existing retry/recovery behaviour remains; no code is stored or newly inferred by this task. |
| Long product name, long SKU, or narrow dialog viewport | Product identity wraps before the label; the label and six-symbol tail stay together on their own readable line. The tail is never clipped or overlaid by dialog actions. | The scan `TextInput` stays visible and reachable without horizontal scrolling. |
| Dialog closed, order changed, or marking row is no longer current | The former product/tail context is removed with the existing dialog context. | No tail is retained, copied, or applied to another order. |

The value is displayed only when it is exactly a six-symbol KIZ tail supplied
by the existing accepted result. A missing, shorter, longer, or otherwise
unavailable value must be omitted rather than padded, truncated anew, or
presented as a valid KIZ tail. This prevents the label from lending false
confidence to an incomplete code.

## UI-kit mapping by zone

| Zone | Required ui-kit component | Required use |
| --- | --- | --- |
| Existing scan dialog | `ModalDialog` | Keeps the existing modal boundary, title, close behaviour and action area; BLG-J01 adds no nested dialog. |
| Active scan affordance | `ScannerLine` | Continues to state that the scanner is active and what it expects. Its position and active state are not changed by the label. |
| Scan entry | `TextInput` | Remains the single focused input for scanner data. The label is not implemented as an input, helper control, or editable field. |
| Product and KIZ-tail context | `ScreenSection` | Contains the existing product identity and one secondary read-only line, `Последние 6 символов КИЗ: <tail>`. No local card, table, chip, or badge is introduced. |
| Scan failure | `ErrorNotice` | Keeps an existing scan failure in warehouse language; it must not expose a raw rejected KIZ or technical error code. |
| Dialog actions | `PrimaryAction`, `SecondaryAction` only where already present | Existing actions retain their names and availability. The new label creates no action. |
| Screen shell, tabs, filters, menus and tables | `ScreenShell`, `TabsBar`, `FilterBar`, `ActionMenu`, `DataTable` | Not changed by this task; no local substitute may be introduced. |

All changed visible UI uses the named exports from `frontend/src/ui-kit/index.ts`.
The required presentation is a text line within existing kit composition; no
missing ui-kit component exists, therefore S09 has no `DESIGN_SYSTEM_GAP`.

## Textual mockups

### A. Accepted KIZ, ready for the next scan

```text
ModalDialog: "Сканирование кода маркировки"
  ScannerLine: "Сканер активен - сканируйте КИЗ"
  ScreenSection
    Товар: Футболка, белая, M
    Артикул: TSHIRT-WHT-M
    Последние 6 символов КИЗ: A1B2C3

  TextInput: "Сканируйте код" [focused]
```

The tail line is below the product identity and above neither the focused input
nor dialog actions. A scan ending in Enter or scanner suffix does not require a
click before the next scan.

### B. No KIZ tail to label

```text
ModalDialog: "Сканирование кода маркировки"
  ScannerLine: "Сканер активен - сканируйте идентификатор"
  ScreenSection
    Товар: Футболка, белая, M
    Артикул: TSHIRT-WHT-M

  TextInput: "Сканируйте код" [focused]
```

There is no empty label, dash, guessed tail, or KIZ wording for a non-KIZ
identifier or an unavailable tail.

### C. Scan failure without false confirmation

```text
ModalDialog: "Сканирование кода маркировки"
  ScannerLine: "Сканер активен - сканируйте КИЗ"
  ErrorNotice: "Код не принят. Проверьте код и отсканируйте его ещё раз."
  ScreenSection
    Товар: Футболка, белая, M
    Последние 6 символов КИЗ: A1B2C3   [last confirmed value, if one exists]

  TextInput: "Сканируйте код" [focused after existing error recovery]
```

The example keeps a previously confirmed tail distinct from the rejected scan;
when no confirmed tail exists, the product section simply omits that line.

### D. Narrow viewport and long product identity

```text
ModalDialog
  ScreenSection
    Товар: Комплект спортивной одежды для тренировок, белый, размер M
    Артикул: SPORT-KIT-WHITE-M
    Последние 6 символов КИЗ: A1B2C3

  TextInput: "Сканируйте код" [focused]
```

The product text may wrap; the label and value form one secondary line and
wrap as a unit before they can overlap the input or actions. The six symbols
must remain fully legible.

## Review and case focus

- S10 checks that the label reads as a KIZ explanation rather than a status or
  a second scan instruction, and that it stays visually secondary to the scan
  input on desktop and narrow operator viewports.
- S10 checks long product data, no-tail state, rejected scans and that no raw
  code or technical error becomes visible through the label.
- S15 must cover accepted KIZ with an exact six-symbol tail, an accepted
  non-KIZ identifier, unavailable/malformed tail omission, rapid consecutive
  accepted scans, rejected scan with and without a prior confirmed tail, long
  product data, narrow viewport, and close/order-change cleanup.
- S18 must preserve the existing scan request, parsing, persistence and
  duplicate handling. It may consume an existing display tail only; it must
  not create a new external call, delay, polling loop, or scanner confirmation.

## Out of scope

No scanner implementation, API contract, marking-code parser, database write,
order lifecycle, external marketplace operation, secret access, deploy, or
live-browser acceptance is performed in S09.

## S09 verdict

`UX_CONTRACT_READY`: concrete scan-dialog states and mockups identify the
KIZ-tail value in plain warehouse language, use the existing ui-kit vocabulary,
and preserve a no-extra-step scanner flow.
