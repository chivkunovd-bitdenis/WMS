# S12 TASK_CUT - BLG-D14

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-D14-C1`
**Title:** Create one large supply exactly once while the Wildberries status
poller overlaps its orders, without losing a valid operator intent.

This remains one atomic vertical card. It must not be split into a database-lock
change, a poller change, an API retry, and an operator retry surface: none of
those fragments alone proves the warehouse outcome. The completed card exists
only when one accepted large-order intent reaches exactly one durable supply, or
truthfully becomes retryable with the valid selection and data preserved, while
the overlapping background poller retains legitimate status updates.

## Scope and observable contract

For a valid set of at least 155 eligible orders, the operator starts supply
creation while the background status poller may process all, some, or none of
the same orders. The observable result is exactly one of these product-approved
outcomes:

1. One supply is durably created for the accepted order set and is returned by
   read-back and ordinary reload.
2. A temporary concurrency conflict is recovered within the architecture-
   approved bounded policy, without duplicate supply creation, hidden partial
   membership, or loss of selection.
3. After that policy is exhausted, the operator receives an unambiguous retry
   path for the same intent. Before retrying, WMS determines whether the first
   attempt committed and returns that result when it did.
4. A genuine eligibility or other business-state change is reported as such;
   it is not retried or relabelled as a temporary deadlock.

Authorization and tenant, seller, warehouse, order-eligibility, audit and
external-failure semantics remain in force. This card does not authorize a
selection-flow redesign, an unrelated supply-process change, a polling-schedule
change, a live Wildberries request, production data mutation, deployment,
commit, push or merge.

## Acceptance cases reserved for S15

| ID | Fixture/oracle | Required result |
| --- | --- | --- |
| `BLG-D14-AC01` | At least 155 valid orders; no overlapping poller work | One durable supply contains the accepted orders exactly once; read-back and reload return the same membership. |
| `BLG-D14-AC02` | At least 155 valid orders; poller deliberately overlaps all selected orders | The operation reaches exactly one supply or an honest retryable outcome; no deadlock leak, duplicate, hidden partial supply, or lost valid status update. |
| `BLG-D14-AC03` | Same creation with poller overlap on only a subset, then on no selected orders | The overlap classification is correct and non-overlapping polling remains a control case, not a source of changed membership. |
| `BLG-D14-AC04` | A transient database concurrency conflict permitted by S13 policy | Recovery is bounded, revalidates business preconditions, and succeeds once without asking the operator to rebuild the selection. |
| `BLG-D14-AC05` | Recovery policy exhausted before commit | The operator can retry the preserved intent; no indefinite spinner, false success, or silent selection/data loss occurs. |
| `BLG-D14-AC06` | First attempt committed but its response was lost; repeated click, explicit retry, worker replay and worker restart | Each path returns the existing outcome or performs it once; at most one supply exists for the intent. |
| `BLG-D14-AC07` | An order becomes ineligible during creation | WMS identifies the business conflict, never forces stale membership, and does not classify it as a retryable deadlock. |
| `BLG-D14-AC08` | Timeout, partial failure, reload/read-back, and audit trace | No hidden partial result is accepted; evidence joins intent, recovery/retry decision, durable membership and worker effects. |
| `BLG-D14-AC09` | Different tenant, seller, warehouse, role and isolated worker queue | Recovery cannot bypass authorization or isolation, and one task queue cannot contaminate another. |
| `BLG-D14-AC10` | Additive migration compatibility, integrity reconciliation and restore/rollback fixture | Schema and data boundaries remain compatible; reconciliation detects any invalid duplicate or dual membership. |

S15 must choose deterministic non-production fixtures, reset strategy, oracle,
executor type and planned S19 binding for every case. Tests must not call live
Wildberries/Ozon or use production data.

## S13 architecture boundary and open blocker

`BLK-ARCH-002` stays **open**, owned by `solution-architect`, and resumes at
S13. S12 neither closes it nor selects database primitives, a resource/lock
order, transaction scope, retry count, backoff, jitter, timeout values or worker
scheduling.

Before S13 can pass, its minimum closure artifact must define and justify:

- the resource graph for supply creation and status polling, including the
  order, supply, worker and durable intent/idempotency resources affected;
- one safe lock-acquisition ordering and transaction boundaries for every
  overlap path, including the handling of revalidation after a retry;
- a bounded retry, timeout and failure-classification policy that separates
  transient concurrency from business-state changes and uncertain responses;
- idempotency, replay and read-back behavior for operator retry, repeated
  request, worker replay and restart; and
- a reproducible load case for at least 155 orders with deliberately overlapping
  polling, required traces and explicit stop conditions.

S14 independently falsifies this plan, including inverse lock order, stale
poller writes, retry-after-commit, timeout ambiguity, queue/replay overlap and
the 155-order load case. A missing or unconvincing closure leaves the blocker
open and prohibits development.

## Implementation and review boundary

S18 may implement only the S13/S14-approved plan and the S15/S16-approved
cases needed for this card. It must not broaden into a general supply rewrite,
polling redesign, bulk-selection redesign, cross-tenant behavior change,
unrelated schema work, external marketplace call, release action or UI change.
If the approved retry outcome needs a new or materially changed operator
surface, post-diff classification must add `ui_change` and route the required
UX, design and Product Browser gates; this card does not waive them.

S20 review must reject an implementation that merely suppresses an error,
changes lock behavior without the approved S13 graph/order, retries unboundedly,
assumes a timeout means rollback, creates a duplicate supply, loses a legitimate
poller update, weakens authorization/isolation, or offers retry without durable
read-back/idempotency proof. S22/S23 must execute the approved load and overlap
cases on an isolated production-like stack with the worker active and bind
operator intent to exactly one durable supply, exact membership, worker effects,
audit trace and reload/read-back.

## Handoff

- **Next stage:** `S13 ARCHITECT_PLAN`, role `solution-architect`.
- **Gate:** `BLK-ARCH-002` remains open until S13 produces its minimum closure
  artifact; S14 must then independently falsify it.
- **S16 packet condition:** Product receives this card, S11 contract, S13/S14
  architecture receipts and S15 cases. Any material change invalidates the
  downstream Product-before-Dev decision.

## Verdict

`TASK_CUT_READY`: `BLG-D14-C1` preserves the complete observable concurrency
outcome as one card, gives the architecture and case stages concrete boundaries,
and does not replace the open architecture decision with an invented policy.
