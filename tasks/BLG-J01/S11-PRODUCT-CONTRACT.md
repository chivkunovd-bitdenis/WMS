# S11 PRODUCT_CONTRACT_APPROVAL - BLG-J01

## Product decision

The operator problem is confirmed: a bare six-symbol value beside a product is
ambiguous and can look like damaged scan data. The approved outcome is to keep
the existing value in the existing scan-dialog product context and identify it
as `Последние 6 символов КИЗ: <tail>`.

This is a labeling-only product change. It must not change accepted identifiers,
KIZ parsing, storage, duplicate handling, order state, required code quantity,
API or marketplace behaviour.

## Operator journey and warehouse rationale

1. The operator opens the existing marking-code scan dialog and scans through
   the existing focused input.
2. After the existing flow accepts a KIZ, the matching product context shows the
   exact confirmed six-symbol tail with the explanatory label.
3. The operator can immediately understand what the short value represents and
   compare the visible tail with the physical code without treating it as noise
   or a damaged identifier.
4. The same scan input remains ready for the next code. The label introduces no
   click, acknowledgement, focus change, timeout, animation or second field.

The product identity explains which item is being checked. The label explains
the meaning of the shortened value. The six-symbol tail supports quick visual
comparison. None of these elements is a new status or action, so the scan input
continues to hold the primary visual and interaction priority.

## Approved visible contract

- Show `Последние 6 символов КИЗ: <tail>` only for an existing accepted result
  that supplies exactly six displayable KIZ-tail symbols.
- Keep the line in the existing product context, directly below the product
  identity, visually secondary to the active scan affordance and input.
- Keep all six symbols fully legible on narrow dialogs and with long product
  names; the line must not overlap or displace the scan input or dialog actions.
- Omit the whole line when the accepted identifier is not a KIZ or the confirmed
  six-symbol tail is unavailable. Do not show an empty label, placeholder,
  guessed value, new truncation or padding.
- A rejected or failed scan must not make its raw input appear as a confirmed
  tail. A previously confirmed product context may remain only under the
  existing scan-dialog behaviour and must stay distinguishable from the error.
- Closing the dialog, changing the order or leaving the current marking row
  clears the context under the existing lifecycle; a tail must not leak to
  another product or order.

## Product acceptance boundaries

S12 may cut this as one atomic vertical card because the observable result is a
single coherent operator outcome: the existing KIZ tail becomes understandable
without slowing scanning. S15 must preserve the S09 state matrix, including
rapid consecutive scans, no-tail and non-KIZ cases, rejected scans, long data,
narrow viewport and context cleanup.

Before final acceptance, the exact implemented artifact must prove in a live
operator browser that the label is understandable at a glance, the tail remains
easy to compare, focus is ready for the next scan without a click, and no new
visual noise or extra step has appeared. This S11 decision does not accept an
implementation or replace S24 design implementation review or S25 Product
Browser acceptance.

## Out of scope

No new scanner logic, parser, persistence, API, external call, database change,
order transition, action, status, notification, deployment or live WB/Ozon
operation is approved by this contract.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: the S09 UX contract and S10 design verdict support
the stated warehouse outcome, preserve scanner-first cadence and keep the
change within the requested explanatory label.
