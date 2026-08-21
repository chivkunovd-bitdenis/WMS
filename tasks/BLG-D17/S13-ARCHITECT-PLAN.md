# S13 ARCHITECT_PLAN - BLG-D17

## Verdict

`ARCH_PLAN_BLOCKED`

The architecture cannot honestly receive `ARCH_PLAN_READY` on the current
controller packet. The product outcome is implementable, and the provisional
plan below fixes the resource, state, transaction, migration and dependency
boundaries, but three required inputs are not yet controller-valid:

1. The approved Product contract requires an authorized user to see an
   unavailable reason. The existing pool-code history API already returns an
   event `reason`, but `HonestSignPoolPage` neither types nor renders that
   field. The current task traits omit `ui_change`, so S09, S10, S24 and S25
   are absent even though a visible change is mandatory.
2. The task is a runtime behavior change, but the current required-stage set
   omits S08. The canonical process requires an S08 behavior contract or an
   explicit machine-approved equivalent before the architecture package can
   be accepted.
3. The task snapshot pins `base_sha=69c271678782d7dcfa39df97cd905cbee1678727`,
   whose checkout does not contain `backend/app/services/fbs_kiz_service.py`.
   The affected `void` transition is present in canonical `origin/etalon` at
   inspected SHA `7e44cd618d6b441523518503b8e29a131c64027a`: replacement calls WB first and
   then changes the old code to `void` in `_void_existing_sgtin_marking_locally`.
   S17 cannot allocate or prove the actual fix against a baseline that lacks
   the affected operation.

A fourth input is fail-closed rather than an independent reason to mutate the
task here: no accepted input proves which versioned WB read-back result means
"this exact SGTIN is definitively absent". Empty, missing, timed out or
unparsed metadata remains `EXTERNAL_OUTCOME_UNKNOWN`; it can never authorize
recovery. S03/S04 must be added if no current reusable external-contract
receipt establishes a stronger oracle.

## Minimum closure before S13 can pass

The controller owner must provide one refreshed packet in which all of the
following are true:

1. Impact is reclassified through the controller to include `ui_change`, and
   the required-stage set also contains S08. Any upstream receipts invalidated
   by that profile change are recreated by their owning roles; this architect
   does not self-approve Product, BA or Design work.
2. S09/S10 approve the exact existing authorized read surface and visible
   states for unavailable reasons. The intended surface is the Honest Sign
   pool code list/history zone; architecture does not pre-approve its UX.
3. The implementation baseline is pinned to an exact SHA containing the
   canonical FBS KIZ replacement/cancel flow and its matching models, APIs,
   migrations and tests. A branch name or historical commit observation is not
   sufficient.
4. A versioned accepted contract or emulator receipt distinguishes
   `ABSENT_CONFIRMED` from timeout, missing order, missing response, partial
   payload, parse failure and contradictory evidence. Otherwise the task is
   reclassified with `external_contract` and passes S03/S04 before returning
   to S13.

After closure, this artifact must be rebound to the new packet/input hashes and
reviewed at S14. The provisional decisions below are not a pass receipt.

## Provisional authoritative state model

`MarkingCode.status` remains the allocation projection. D17 does not introduce
a second allocatable state machine:

- only `available` is selectable by pool allocation;
- C1 never changes a code status;
- C2 is the only D17 transition from `void` to `available`;
- every new write to `void` carries a stable current unavailable reason;
- historical `MarkingCodeEvent` rows are append-only and are never rewritten.

The binding/recovery workflow uses separate durable operation state:

```text
binding attempt
  PREPARED
    -> EXTERNAL_BOUND_CONFIRMED -> CLOSED_BOUND
    -> EXTERNAL_ABSENT_CONFIRMED -> FAILED_UNBOUND
    -> EXTERNAL_OUTCOME_UNKNOWN -> RECONCILIATION_REQUIRED
    -> CONTRADICTORY -> RECONCILIATION_REQUIRED

C1 decision for one code and one evidence version
  RECOVERY_ELIGIBLE
  UNAVAILABLE(<reason code>)

C2 apply for a current RECOVERY_ELIGIBLE decision
  APPLYING
    -> RECOVERED_AVAILABLE
    -> STALE_OR_CONCURRENT_CHANGE
    -> UNAVAILABLE(<new reason code>)
    -> APPLY_FAILED_NO_STATE_CHANGE
```

An attempt outcome and a code status are related facts, not aliases. A failed
request is not proof of external absence. A `void` row without a definitive
attempt link is classified as historical evidence insufficient and remains
unavailable.

## Unavailable reason taxonomy

Persist stable machine codes; render approved, tenant-safe Russian text at the
API/UI boundary. The minimum taxonomy is:

| Code | Meaning and reconsideration boundary |
| --- | --- |
| `EXTERNAL_BINDING_CONFIRMED` | WB or another accepted external oracle confirms binding/use. No automatic reconsideration. |
| `EXTERNAL_OUTCOME_UNKNOWN` | Timeout, missing/partial response, parse failure or unavailable reconciliation. Reconsider only after definitive read-back. |
| `LOCAL_USE_PRESENT` | Reservation, print, application, shipment or another local commitment exists. Reconsider only through its owning business process. |
| `SCOPE_OR_OWNERSHIP_MISMATCH` | Tenant, seller, product or pool ownership does not match. Never move ownership through recovery. |
| `CODE_IDENTITY_CONFLICT` | Duplicate, malformed or contradictory code identity. Requires controlled data review. |
| `MANUAL_DEFECT_POLICY_INVALIDATION` | Independent manual, defect or policy decision keeps the code unavailable. |
| `STALE_OR_CONCURRENT_CHANGE` | Evidence changed after C1 or during C2. Run a fresh C1 evaluation. |
| `ATOMIC_RECOVERY_FAILED` | No recovery transaction committed. Retry with the same operation key after read-back. |
| `HISTORICAL_EVIDENCE_INSUFFICIENT` | A legacy `void` row has no complete proof of absence. It remains unavailable until evidence is reconstructed. |

`RECOVERY_ELIGIBLE` is a decision disposition, not an unavailable reason.
Generic `void`, `error`, `failed`, raw exception text and empty values are not
valid user explanations.

## Persistence and additive migration

The exact Alembic revision ID is selected only after the correct S17 baseline
is pinned. The migration is additive and introduces:

1. `marking_code_binding_attempts`: tenant, seller, order, code, old/new marking
   references, idempotency key, request hash, operation kind, durable phase,
   external outcome class, observed contract version/time, sanitized evidence
   hash, actor/job, timestamps and monotonic version. The unique key is scoped
   by tenant plus operation intent, not globally by client text.
2. `marking_code_recovery_runs`: tenant/seller/pool scope, policy version,
   started/completed state, source count, disposition counters, actor/job and
   idempotency key. It is a batch accounting header, never authority to mutate
   a code.
3. `marking_code_recovery_decisions`: run, code and attempt references; captured
   code version; ownership/pool/product snapshot; each mandatory eligibility
   result; sanitized evidence hash; disposition; reason code; supersedes link;
   created actor/time. Rows are append-only. One current decision is selected
   by version, not overwritten.
4. Nullable current-projection fields on `marking_codes`:
   `unavailable_reason_code`, `unavailable_reason_decision_id` and a monotonic
   `state_version`. Allocation continues to read `status`; these fields explain
   exclusion and fence stale decisions.

During mixed-version rollout, a database compatibility guard maps any legacy
write of `status='void'` without a reason to
`HISTORICAL_EVIDENCE_INSUFFICIENT`. New code dual-writes the precise reason and
append-only event/decision. After all writers are upgraded and C1 accounts for
the historical population, a validated constraint enforces
`status != 'void' OR unavailable_reason_code IS NOT NULL`. Old readers ignore
the additive fields; old writers cannot recreate a silently reasonless void.

No destructive down migration is claimed. Application rollback may stop new
recovery while retaining tables, reason projections and audit rows. Data is
never changed back from a later legitimate use merely to imitate schema
rollback.

## Sources of truth and eligibility evaluation

C1 combines accepted facts only:

- external: a versioned WB order-metadata read-back for the exact order and
  exact normalized SGTIN, classified by an accepted contract adapter;
- local binding: tenant-scoped `FbsOrderMarking` plus the durable binding
  attempt, not a missing response or client assertion;
- local use: `MarkingCode` lifecycle fields, `MarkingCodeEvent`, unique
  `FbsOrderMarking.marking_code_id`, packaging line/application references and
  shipment/consumption evidence;
- ownership: tenant, seller, pool and product links checked independently;
- invalidation: current reason and append-only defect/manual/policy events.

Absence from one query is not sufficient when the order is missing, the WB row
is partial, the adapter cannot classify the response, or local/external facts
conflict. C1 records one disposition for every source row and asserts:

```text
source_count = eligible + unavailable_by_reason + concurrently_changed
             + evaluation_failed
```

No raw CIS/DataMatrix, token, response body or foreign-tenant identifier enters
ordinary logs, receipts, UI or Git evidence. Evidence uses code IDs plus stable
masked fingerprints.

## Transaction, idempotency and concurrency boundary

All D17 and existing FBS KIZ paths that can bind, replace, cancel or recover the
same code must use one canonical session-level advisory lock namespace. Locks
are acquired in this order:

```text
tenant/seller -> order UUID -> marking-code UUID(s), sorted ascending
```

The advisory lock may span an external read-back, but no database row lock or
open transaction may span network I/O. Each wait is bounded and observable.
Discovery of a writer that does not honor this lock returns to S13.

C1 under the advisory lock performs external read-back, then opens a short
transaction, locks the binding attempt and code rows in canonical order,
rechecks local facts, increments/reads `state_version`, writes one decision and
updates the current unavailable projection. It never changes allocation state.

C2 acquires the same advisory lock, performs a fresh external read-back without
row locks, and then opens one short transaction. It locks the current C1
decision, code, attempt, matching FBS marking and affected packaging reference
in the declared order, rechecks authorization and recomputes the evidence hash.
Only an exact match may atomically:

- change `void` to `available`;
- clear only transient reservation/binding fields proved to belong to the
  failed attempt;
- retain original tenant, seller, pool and product ownership;
- close the failed attempt and C2 operation;
- update the current reason projection;
- append the recovery event/decision;
- increment `state_version`.

Printed/applied/introduced/shipped/consumed timestamps are never cleared. If
any is present, the row is `LOCAL_USE_PRESENT`, not recoverable. Available
counts are derived from the committed status, so there is no separately
mutable counter to drift.

Each C1/C2 request uses a tenant-scoped idempotency key plus immutable request
hash. Same key plus same hash returns durable read-back; same key plus another
hash is rejected. Batch execution commits per code, retains a complete run
accounting row, and cannot turn one ambiguous row into a batch-wide success.

## Resource graph and locks

The graph is conditional on the refreshed exact baseline:

```text
FBS KIZ replace/cancel and marking scan paths
  -> durable binding attempt + accepted WB read-back classifier
  -> C1 tenant/seller/pool inventory
       -> local-use and ownership checks
       -> append-only recovery decision + current reason projection
       -> authorized Honest Sign read-back
  -> C2 current-decision apply
       -> advisory lock + fresh external read-back
       -> short atomic void-to-available transaction
       -> available count, history and reload read-back
```

| Resource | Planned ownership | Lock / boundary |
| --- | --- | --- |
| `backend/app/models/marking_code.py` and new recovery model module | Current projection, attempts, runs and append-only decisions | Exclusive marking lifecycle schema lock |
| one new Alembic revision after the pinned head | Additive schema, compatibility guard and later-validatable constraint | Exclusive migration-chain lock |
| `backend/app/services/fbs_kiz_service.py` | Replace/cancel attempt journaling and shared lock discipline | Exact baseline required; no live call in this stage |
| `backend/app/services/fbs_marking_service.py` | Reuse accepted tenant-scoped WB read-back adapter only | External contract lock; missing absence oracle blocks auto-recovery |
| new `backend/app/services/marking_code_recovery_service.py` | C1/C2 policy, evidence hash, idempotency, transactions and reconciliation | Per tenant/seller/order/code advisory locks |
| `backend/app/services/marking_code_service.py` | Available counts, masked history/read models and audit helpers | No second allocation rule |
| `backend/app/api/marking_codes.py` | Authorized C1/C2 and reason/history read-back contract | New routes require behavior tests; no client tenant trust |
| existing FBS KIZ API | Preserve current operator replacement contract while adding durable attempt semantics | No new operator action without Product/UX stages |
| Honest Sign pool code/history zone | Render approved reason and reconsideration text | `ui_change`; exact UI files/components come from S09/S10 |
| focused PostgreSQL and API tests plus frontend/browser tests | Concurrency, migration, tenant and read-surface proof | Emulator only; no live WB/Ozon |

S17 must allocate exact files from the refreshed baseline and serialize any
other card touching these tables, FBS KIZ replacement, WB SGTIN metadata or the
Honest Sign pool code/history zone. A new resource found by Dev returns to S13;
Dev does not widen scope.

## Delivery order

1. Profile/oracle/baseline closure and fresh upstream receipts.
2. Expand migration plus model/read compatibility; no status mutation.
3. C1 attempt/reconciliation service, population accounting, reason projection
   and authorized read-back. Historical rows remain unavailable.
4. S09/S10-approved reason visibility on the existing surface, if the refreshed
   packet approves it.
5. C2 atomic apply for current C1 decisions only, including restartable
   per-code historical processing and post-write read-back.
6. Independent S19/S20/S22/S23 evidence on PostgreSQL and emulator fixtures.

C1 precedes C2. The two cards do not run in parallel because C2 consumes C1's
versioned decisions and both lock the same lifecycle resources.

## BLG-F01 dependency boundary

`BLG-F01` owns the canonical Pipeline blocker/dependency registry and its
controller enforcement. D17 owns domain reason codes, affected operation,
evidence and the controlled reconsideration condition. D17 must not edit any
F01 artifact or create a second blocker registry.

The current controller reports `blocked_by=[]`, so unfinished F01 does not
block this S13 analysis. Until F01 is accepted, D17 retains its reason and
dependency locally in the task/domain artifacts. S21/S23 may claim canonical
registry integration only against F01's accepted interface and exact artifact;
otherwise that integration remains an explicit dependency risk and cannot be
silently marked complete.

## S14 falsification handoff

After minimum closure, the independent architect must try to disprove at least:

- an empty/partial WB payload being classified as definitive absence;
- a successful external change followed by process death before local commit;
- a local rollback being reported as external rollback;
- any KIZ bind/replace/cancel path bypassing the advisory lock or attempt
  journal;
- stale C1 evidence racing reservation, print, application, shipment, seller or
  pool ownership change;
- lock inversion across order, code, marking and packaging rows;
- duplicate request, key reuse, worker replay or restart creating two outcomes;
- a mixed batch losing a row or applying an ambiguous row;
- a foreign tenant/seller match influencing evidence or leaking existence;
- a reasonless legacy writer bypassing compatibility protection;
- rollback erasing later legitimate use or append-only history;
- the UI showing only `void`/`error`, omitting reason or exposing raw CIS;
- the implementation baseline lacking the actual affected FBS KIZ flow; and
- D17 inventing a local substitute for the unfinished F01 registry.

Any unresolved external-absence oracle, profile gap, baseline mismatch, lock
bypass, unsafe rollback or invisible reason keeps S13 blocked or returns S14 to
S13. S14 does not implement the correction.

## Explicit exclusions

This stage performs no Product, BA, Reviewer, Dev or acceptance work. It makes
no code/schema/UI change, no data repair, no production query or mutation, no
live WB/Ozon call, no secret access, no build, no test execution, no commit,
push, merge, deploy or release action. It does not modify BLG-F01 artifacts and
does not approve bulk `void -> available` recovery.

## Final verdict

`ARCH_PLAN_BLOCKED`: the provisional design is concrete, but a positive S13
receipt would be unsafe while the controller profile omits mandatory runtime
and UI gates, the pinned task baseline lacks the affected operation, and no
accepted external oracle proves definitive SGTIN absence. The minimum closure
above is required before `ARCH_PLAN_READY` can be issued.
