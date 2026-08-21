# S12 TASK_CUT - BLG-I04

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-I04-C1`
**Title:** Print one explicit copy of every currently required FBS label and
show the exact current sheet total before the print run is submitted.

This is one vertical card, not separate UI, calculation, confirmation and
print-transport cards. A copies field without a bound print invocation can
still produce the squared run; a corrected request without a truthful visible
total still leaves the operator unable to prevent paper waste. The observable
warehouse result exists only when the same current selection, layout result and
one independent copies value drive both the displayed total and the print run.

## Card contract

**Observable operator result.** In the existing FBS print action, a newly
opened run starts at one copy per required label. The selection answers which
labels are needed; it never supplies or changes the copies value. Before an
operator can submit, the action shows the current calculated number of sheets:

```text
totalSheets = sheetsPerOneCopy * copiesPerRequiredLabel
```

`sheetsPerOneCopy` is the current layout result for the printable selection;
it may be more than the number of selected orders. `copiesPerRequiredLabel` is
the one editable, positive whole-number value and begins at `1` every time the
action opens. The requested print run must match the total that is visibly
current at submission time.

Runs below 100 sheets submit directly. A run of 100 sheets or more first shows
an explicit confirmation for that same total; only its second, explicit print
action may submit. Cancel, Escape, closing the dialog, invalid quantity, no
printable selection, in-progress recalculation, stale confirmation, rejected
or unknown outcome create no automatic duplicate run. An accepted/sent result
does not claim that paper has physically printed.

**Scope of the card.** The card includes the existing FBS print action from
its selected printable items through its quantity/preflight state, large-run
confirmation and the currently applicable print invocation or print-job
contract. It includes the propagation of the authoritative quantity and sheet
total across that boundary, so a selection count cannot be reintroduced as a
copies value downstream.

It does not change selected orders, label content or layout, table columns,
filters, tabs, menus, other print flows, printer configuration, a printer's
physical behaviour, an operator-configurable threshold, automatic retries or
a maximum run size. It does not authorize live printing, marketplace calls,
secret access, deployment or release.

## Implementation and review boundaries

S13 must map the actual existing FBS print path end to end: selection and
printable-item derivation, layout sheet calculation, editable copies state,
preflight rendering, confirmation invalidation, request or browser-print
boundary, duplicate-submission protection, error/unknown outcome handling and
the source of the central inclusive threshold of 100 sheets. It must decide
the smallest safe file and contract boundaries, including whether an existing
API or worker contract is involved; S12 does not choose that mechanism.

S14 must independently try to falsify the plan with selection-count reuse,
multi-page layout arithmetic, default copies surviving a reopen, threshold
off-by-one behaviour, stale confirmation after a changed selection/layout/
quantity, double activation, timeout or unknown result, and wording that
mistakes request acceptance for physical output. Any unresolved way to submit
a run different from the visible total returns to S12 or the owning contract
stage, rather than being papered over in implementation.

S18 may implement only the bounded existing FBS print-flow behaviour described
here and approved in S09/S11. It must not introduce a new print workflow,
change physical printer settings or label layout, modify unrelated screens, or
invent a per-screen/operator threshold. Any API, worker or persistence change
found necessary must remain limited to making the existing print invocation
match the current displayed total and receive the planned tests and review.

S20 must reject a change that only makes the UI look correct while the invoked
print run still consumes selected count as copies, relies on a stale visible
total, allows automatic duplicate submission, or reports physical printing
from request-level evidence. It must also reject a value of 100 that bypasses
the mandatory confirmation.

## Acceptance cases for S15

| ID | Fixture or oracle | Required result |
| --- | --- | --- |
| `I04-C1-AC01` | One selected one-sheet printable item; newly opened action | Copies is `1`, visible total is one sheet, and the invoked run requests one copy rather than deriving copies from selected count. |
| `I04-C1-AC02` | Ten selected one-sheet printable items; untouched default | Visible total and invoked run are ten sheets, never one hundred. |
| `I04-C1-AC03` | Multi-page layout with a known `sheetsPerOneCopy` and copies `1`, then `3` | Total and invoked run use the layout result multiplied once by copies; selected-order count is not substituted for either operand. |
| `I04-C1-AC04` | Totals of 99, 100 and more than 100 sheets | 99 submits directly; 100 and every larger total require the explicit second confirmation and cannot create a job at the first action. |
| `I04-C1-AC05` | Quantity empty, zero, negative, fractional, non-numeric; no printable selection; recalculation in progress | Submission is unavailable with the approved reason where applicable, and no print run is created. |
| `I04-C1-AC06` | Large-run dialog followed by cancel, Escape or close | No run is created and the entered quantity remains available for correction or deliberate retry. |
| `I04-C1-AC07` | Open confirmation, then change selection, layout result or copies | The old confirmation is invalid; the UI shows the recalculated total and requires a new confirmation when the current total is at least 100. |
| `I04-C1-AC08` | Double activation, rejected request, timeout or unknown outcome | At most one invocation is attempted for one deliberate submission; there is no automatic retry or claim that nothing reached the printer when the outcome is unknown. |
| `I04-C1-AC09` | Reload or close and reopen after a prior non-default quantity | Copies resets to `1`; total is recalculated from the current printable items and layout. |
| `I04-C1-AC10` | Same accepted run observed through later test and acceptance evidence | Preflight total, accepted invocation/job and available printer or approved-device evidence are tied to the same run; request-level success alone is not accepted as physical-output proof. |

S15 must make the direct and destructive cases executable with local,
deterministic fixtures. It must keep physical printer/device proof separate
from browser/API evidence and use no live printer, WB, Ozon or production
system.

## Handoff and explicit exclusions

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
the `print` task is classified high risk and the card spans the visible
operator preflight and the actual print-invocation boundary. S13 and the
independent S14 review must complete before the S15 case factory and the later
Product-before-Dev decision.

S22/S23 must compare the current visible preflight total with the accepted
invocation/job for the same run. S25 Product Browser acceptance must cover the
operator journey, but neither browser acceptance nor request evidence alone
proves physical output; the print/device evidence required by the task trait
remains distinct.

This stage produces no architecture selection, implementation, test execution,
commit, push, merge, deployment, live printer operation, release authorization
or acceptance verdict. A changed product contract, threshold, card boundary or
oracle invalidates this cut and requires S12 rework before downstream approval.

## Verdict

`TASK_CUT_READY`: `BLG-I04-C1` keeps the anti-squaring behaviour, truthful
preflight total and high-volume confirmation as one independently observable
FBS print outcome, with explicit downstream ownership for the actual print
boundary and its destructive cases.
