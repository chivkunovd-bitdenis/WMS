# S12 TASK_CUT - BLG-F01

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

`BLG-F01` remains one atomic control-plane card: **create one canonical,
auditable blocker registry and dependency decision that is enforced identically
at every supported Pipeline v2 entrypoint.**

It must not be split into a registry/documentation card and a later controller
enforcement card. A registry which can be authored, validated or reported but
is not consulted before the affected operation still permits the unsafe
continuation that the product contract forbids. Conversely, an entrypoint
integration without the stable registry, lifecycle evidence and dependency map
creates a second source of blocker truth. Neither fragment has a safe,
independently observable operational result.

## Card contract

**Observable operational result.** Before dispatch, hold/resume, stage
advance, final acceptance, release authorization or report of a task, the
controller determines the applicable `BLK-*` entries from one canonical
registry and dependency map. An open applicable entry refuses only its stated
operation and returns the stable ID, business harm, affected scope, owner,
minimum closure evidence, resume condition and resume stage. An unrelated
card continues. A closed entry remains traceable in history and cannot stop
work unless it is validly reopened; a narrowed entry permits only the scope
proven safe.

**Card boundary.** The card includes the canonical machine-readable registry
contract and validation; stable blocker identities; directional dependency
evaluation; atomic open/narrow/close/supersede/reopen history; authoritative
controller binding for task classification, dispatch, hold/resume, stage
advance, final acceptance and release authorization; consistent packet/state/
report projection; and automated fail-closed checks for invalid, stale,
contradictory or unverifiable blocker data.

The card includes no warehouse UI/API/workflow redesign, no relaxation of
stock, marking, tenant, authorization or marketplace invariants, and no
decision to adjudicate or close an existing domain blocker. An existing
operator-facing rule may be inventoried and linked, but a new operator-visible
message, action or flow is a separate correctly classified card.

## Required acceptance shape for S15

S15 must create runnable direct and destructive cases for the complete card,
using deterministic local fixtures and no live marketplace or production
systems:

- a valid open blocker refuses its exact affected transition and exposes every
  approved explanation and resume field;
- an unrelated task continues while a different card is blocked;
- release-only, oracle-only and stage-specific blockers stop at their declared
  boundaries and do not over-block earlier permitted work;
- a narrowed blocker permits only the evidenced safe scope, while the named
  remaining scope stays stopped;
- valid closure evidence from the required role/oracle returns to the declared
  stage without skipping invalidated Product, architecture, case, review,
  test, acceptance or release gates;
- missing, stale, wrong-role or manually edited closure evidence and stale
  task snapshots fail closed;
- missing mandatory fields, duplicate IDs, unknown task/stage references,
  dangling edges, cycles and contradictory active states are rejected;
- closed, superseded and reopened entries retain a traceable, non-rewritable
  history;
- every supported entrypoint makes the same decision for identical blocker and
  task state; worker self-unblocking and self-approval are rejected; and
- controller restart/recovery preserves active blocker and dependency truth.

S20 independently reviews authority boundaries, entrypoint parity, narrow
scope, stale-snapshot resistance and history immutability. S22/S23 run the
registry checks and Pipeline v2 metatests against the exact candidate,
including negative bypass cases. S25 inspects machine evidence that one
decision is visible in controller packet, state and report outputs while an
independent card is not stopped.

## Delivery order and ownership boundaries

1. S13 `ARCHITECT_PLAN` maps all registry consumers and mutation boundaries:
   classification, dispatch, hold/resume, advance, acceptance, release, CI
   and reporting. It chooses the storage/schema, authority, versioning,
   locking, atomic lifecycle update, recovery and exact file boundaries. S12
   does not select implementation mechanisms.
2. S14 `ARCHITECT_FALSIFICATION` independently attacks bypass entrypoints,
   stale read-only snapshots, inconsistent registry projections, over-broad
   dependencies and self-authorized closure. An unresolved critical conflict
   blocks development.
3. S15 binds the listed acceptance shape to executable cases before code. S16
   separately decides whether the resulting card is approved for development.
4. S17-S23 deliver and independently verify the implementation. S25 accepts
   this declared internal control-plane surface; it does not mean a warehouse
   browser flow was changed or accepted.
5. S26 may authorize only the immutable reviewed candidate according to the
   controller. This task neither deploys nor implies a production operation.

## Explicit exclusions

This stage performs no architecture selection, implementation, schema change,
controller-state edit, commit, push, merge, deployment, release authorization,
secret access, production mutation or live Wildberries/Ozon request. It does
not authorize a worker to accept, unblock or approve its own work.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
this is a critical `pipeline_change` with controller, CI and release decision
surfaces. The architect receives this task cut and the S11 product contract.
Any change that makes the card documentation-only, separates registry truth
from enforcement, broadens affected scope, or changes warehouse behavior
requires S12 rework before subsequent Product approval for development.
