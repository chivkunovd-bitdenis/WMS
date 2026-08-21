# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D14

## Product decision

Product approves the operational outcome in which creating a large supply is a
reliable operator action even when the Wildberries status poller concurrently
processes some of the same orders. A temporary database concurrency conflict is
an internal coordination event, not evidence that the operator selected invalid
orders and not a reason to discard the operator's work.

The operator must reach one of two honest outcomes:

1. the intended supply is created exactly once from the accepted order set and
   WMS shows the resulting supply through normal read-back; or
2. WMS reports that the action did not complete and offers a clear retry path
   without forcing the operator to rebuild the still-valid selection or re-enter
   still-valid data.

This decision does not allow WMS to force through an order whose business state
really changed while the action was running. A genuine eligibility change is a
business conflict and must be shown separately from a temporary technical
concurrency conflict.

## Operator meaning and states

The complete operator journey has the following product states. The exact UI
component and wording remain downstream decisions, but the meaning must be
unambiguous.

- **Ready.** The operator has a valid selected order set and any required supply
  data. Starting creation preserves that intent as the input of this attempt.
- **Processing.** WMS has accepted the action and is resolving the transaction.
  Repeated clicks or a delayed response must not create additional supplies.
- **Succeeded.** One supply exists for the accepted order set, its identifier and
  resulting order membership are available through read-back, and an ordinary
  reload shows the same result.
- **Temporary conflict being recovered.** WMS may recover from a transient
  concurrency conflict without asking the operator to repeat the action. This
  state must not erase the selection, create a partial hidden supply or present a
  business-validation error.
- **Retry available.** If the architecture-approved recovery policy is exhausted,
  WMS states that a temporary conflict prevented completion and gives the
  operator a direct way to retry the same intent. The selected orders and
  still-valid entered data remain available; a page reload, manual re-selection
  of a large batch or guessing whether a supply was created is not an acceptable
  recovery procedure.
- **Business state changed.** If one or more orders became genuinely ineligible,
  WMS does not overwrite that state or retry indefinitely. It identifies the
  affected orders or reason, keeps the unaffected operator context where safe,
  and requires a new valid decision rather than calling this a deadlock.
- **Non-recoverable failure.** An unrelated validation, authorization, external or
  system failure keeps its own existing meaning. It must not be relabelled as a
  temporary concurrency conflict merely to offer retry.

If satisfying these visible states requires a new or changed operator-facing UI
surface, S12/S13 or post-diff classification must add `ui_change` and route the
task through S09, S10, S24 and Product Browser acceptance. This S11 verdict does
not silently waive those stages.

## Warehouse and data invariants

- One operator intent creates at most one supply. A retry after a timeout,
  uncertain response or worker overlap returns the already completed result or
  performs the action once; it never creates a duplicate supply.
- An order is not attached to two supplies and is not left in a hidden
  intermediate membership state.
- A failed attempt does not leave a partially visible supply, silently drop part
  of the selection or report success before durable read-back confirms the
  result.
- Successful supply creation does not lose a legitimate status update from the
  background poller. Conversely, polling must not overwrite the committed
  supply membership with stale data.
- Authorization, tenant, seller, warehouse and order-eligibility checks retain
  their existing force. Concurrency recovery must not bypass them.
- Repeating the same request, replaying a worker event, restarting a worker or
  reloading the operator screen preserves the same final business result.
- Audit evidence must distinguish initial attempt, internal recovery, operator
  retry, completed result and rejected business-state change without exposing
  sensitive order or marketplace data in Git evidence.

## Retry experience boundary

Product approves bounded recovery semantics, not a particular technical retry
algorithm. Automatic recovery is allowed only for a failure classified as a
temporary transaction/concurrency conflict and only while the original business
preconditions can be revalidated. It must eventually resolve to success or to
the visible `Retry available` state; an indefinite spinner or endless background
retry is not acceptable.

The operator's explicit retry represents the same business intent. Before
continuing, WMS must determine whether the previous attempt already committed.
If it did, WMS returns that result. If it did not, WMS may execute a fresh attempt
against current business state. The operator is never asked to choose between
"try again" and "risk creating a duplicate".

S11 intentionally does not choose lock acquisition order, transaction scope,
retry count, backoff, jitter, timeout values, database primitives or worker
scheduling. Those decisions belong to S13 and must be falsified at S14.

## Acceptance boundaries

S12 must keep this as a vertical outcome: operator action, API/service behavior,
database result, overlapping background poll, retry/read-back and reload cannot
be accepted as unrelated partial cards.

S13 must close the architecture contract before development by defining the
resource/lock graph, one safe lock ordering, transaction boundaries, bounded
retry and timeout policy, idempotency/replay behavior and observability. Its
load case must include a supply of at least 155 orders with a deliberately
overlapping status-poll operation. S14 must independently attack that plan.

S15 must create direct and breaker cases covering at least:

- a large supply of at least 155 valid orders without overlap;
- the same operation while polling overlaps all or a subset of its orders;
- polling of non-overlapping orders as a control case;
- a transient conflict recovered automatically;
- exhaustion of the approved recovery policy with preserved selection and a
  safe operator retry;
- retry after the first attempt committed but its response was lost;
- repeated click/request, worker replay and worker restart;
- a real order-eligibility change during creation;
- partial failure, timeout and reload/read-back;
- tenant, seller, warehouse and authorization boundaries;
- queue isolation, migration compatibility, integrity reconciliation and
  restore/rollback evidence required by the declared traits.

S22 and S23 must prove the result on an isolated production-like stack with the
background worker active. A green API response alone is insufficient: evidence
must bind the operator intent to exactly one durable supply, exact order
membership, worker effects, audit trace and read-back after reload. Tests must
not call live Wildberries/Ozon or use production data.

## Open architecture blocker

`BLK-ARCH-002` remains open and owned by `solution-architect` with resume stage
S13. This S11 artifact supplies the product constraints needed by architecture;
it does not close the blocker and contains no invented lock ordering or numeric
retry/timeout policy. S13 cannot pass until its minimum closure artifact exists:
lock ordering, retry/timeout policy and a load case for at least 155 orders.

The open blocker does not prevent S11 from approving the product contract
because its unresolved decisions are explicitly downstream architecture work.
It remains a hard boundary against development until valid S13 closure and S14
falsification receipts exist.

## Out of scope and authorization

S11 does not implement code, choose schema or migration mechanics, modify the
polling schedule, access secrets, call live WB/Ozon, mutate production data,
deploy, commit or push. It does not approve a new warehouse process, a bulk
selection redesign or unrelated supply behavior.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: a large-supply action must finish exactly once or
end in a truthful, retryable state that preserves the operator's valid intent;
real business-state changes remain protected, and `BLK-ARCH-002` must be closed
by S13 architecture before development.
