# S12 TASK_CUT - BLG-J01

## Atomic card

**Card ID:** `BLG-J01-C1`
**Title:** Explain the displayed six-symbol KIZ tail in the order-marking dialog.
**Observable outcome:** In the existing order-marking dialog, an accepted KIZ
with an existing, exactly six-symbol display tail is shown as
`Последние 6 символов КИЗ: <tail>`. The operator can tell what the short
value means without a new action or interruption to the existing entry flow.

This is one vertical card. Splitting the text change from its type and value
guards would expose either an unexplained value or an incorrect KIZ claim, so
there is no useful independent frontend/backend split.

## Scope and allowed resources

The implementation may change only the existing display path and the focused
verification that proves it:

- `frontend/src/screens/v2/FfFbsSupplyDrawer.tsx` - render the approved
  read-only KIZ-tail explanation in `OrderMarkingsDialog` from the existing
  loaded marking result.
- `frontend/tests-e2e/ff-fbs-supply.spec.ts` - add or extend the focused
  browser scenario for the dialog, if it is the established fixture entrypoint
  for this FBS supply flow.
- `frontend/src/screens/v2/FfFbsSupplyDrawer.test.tsx` - a new focused
  component test is permitted only when the browser fixture cannot cover the
  value/type guard deterministically.

No other product file is in scope. In particular, do not change
`frontend/src/screens/v2/fbsApi.ts`, any backend route/service/model,
marking-code parser, persistence, scanner hook, ui-kit export, migration,
marketplace integration, or deployment configuration.

## Delivery rules

1. Reuse the marking record already returned by `getFbsOrderMarkings`; do not
   issue a new request or derive a tail from rejected raw input.
2. Render the approved wording only for an accepted KIZ/SGTIN result whose
   display tail is exactly six symbols. Keep it adjacent to the existing
   product/marking context and visually secondary to the active entry control.
3. For UIN, IMEI, GTIN, missing, short, long, malformed, loading, rejected or
   failed data, omit the entire KIZ-tail line. Do not show an empty label,
   placeholder, guessed value, new truncation, or a KIZ label for another kind.
4. Preserve existing add/reload/error/close behavior. The change must not add a
   field, action, modal, toast, focus change, delay, polling loop, API call, or
   persistence effect.
5. The line must wrap rather than overlap dialog actions or hide the entry
   control on a narrow viewport and with long product identity.

## Acceptance cases for S15

| ID | Oracle and fixture | Expected observable result |
| --- | --- | --- |
| `BLG-J01-AC01` | Existing FBS order-marking dialog fixture with one accepted `sgtin` and exact tail `A1B2C3` | The product/marking context contains exactly `Последние 6 символов КИЗ: A1B2C3`; the existing entry control remains usable for the next value. |
| `BLG-J01-AC02` | Same dialog with accepted `uin`, `imei`, or `gtin` records | No KIZ-tail label is rendered for any non-KIZ identifier; their existing type/value/status display is unchanged. |
| `BLG-J01-AC03` | Accepted KIZ record whose supplied display tail is absent, shorter, longer, or malformed | The whole explanatory line is absent; the implementation neither pads nor re-truncates data to manufacture a tail. |
| `BLG-J01-AC04` | Rejected or transport-failed add after an earlier confirmed KIZ, then the same condition without an earlier KIZ | `ErrorNotice`/existing error feedback remains authoritative; no raw rejected value appears as confirmed. A prior confirmed context may remain only under existing lifecycle behavior. |
| `BLG-J01-AC05` | Two rapid successful additions/reloads for distinct KIZ values | The latest confirmed product/marking context shows its own exact tail, with no extra acknowledgement, duplicate action, or stale tail leakage. |
| `BLG-J01-AC06` | Long product identity and narrow dialog viewport | Product text and explanatory line wrap cleanly; all six symbols, the entry control, and dialog actions remain visible and reachable without horizontal scrolling. |
| `BLG-J01-AC07` | Close dialog or switch to another order after a confirmed KIZ | The old tail is cleared with existing dialog context and is not shown for the next order. |

S15 must translate every row into the required case schema, select a
deterministic local fixture/reset, and assign a browser/component executor.
There is no API, DB, worker, external marketplace, print, authorization, or
transaction assertion for this labeling-only card; each is `N/A` because the
approved contract expressly preserves those layers.

## Handoff

- **Next stage:** `S15 CASE_FACTORY` owned by `pipeline-ba`.
- **S16 packet condition:** Product receives this card together with S09,
  S10, S11 and the completed S15 case matrix. Any change to this card or the
  approved contract invalidates the subsequent Product-before-Dev decision.
- **Not a completion claim:** no implementation, commit, push, deployment, or
  browser acceptance is produced by S12.

## Verdict

`TASK_CUT_READY`: one bounded vertical UI card supplies the approved operator
outcome, names the only permitted implementation/verification paths, and gives
S15 a complete acceptance surface without widening into scanner or API work.
