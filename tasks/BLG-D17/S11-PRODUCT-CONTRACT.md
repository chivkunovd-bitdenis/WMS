# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D17

## Product decision

Product approves a fail-closed recovery contract for marking codes that entered
`void` after an unsuccessful binding attempt. The warehouse must not lose a
usable code merely because an external binding did not happen, and it must not
silently return a code whose use is uncertain to the available pool.

Every affected code must reach one honest operational outcome:

1. **Recovered to available.** WMS has proved that the binding did not take
   effect, the code was not consumed or committed locally or externally, and
   the code is still eligible for the same tenant, seller and product context.
   The transition to `available` and closure of the failed attempt happen as
   one atomic business operation.
2. **Remains unavailable with a reason.** WMS has proof that the code cannot be
   reused, or it cannot safely establish that reuse is allowed. The code stays
   outside every available count and allocation path, while a durable reason
   and the evidence behind it remain reviewable and visible to the authorized
   user.

An unknown, timed-out, contradictory or partially observed binding outcome is
not equivalent to a failed binding. It fails closed to the second outcome until
reconciliation establishes one definitive result. Product does not approve a
blind bulk transition from `void` to `available`.

## Eligibility to recover a code

A code may return to `available` only when all of the following product facts
are true at the mutation boundary:

1. The code and the failed attempt belong to the authorized tenant and seller,
   and the code remains associated with the same valid product or marking-code
   pool. Recovery cannot move ownership or infer a different product.
2. The external binding is definitively absent. A timeout, lost response,
   unavailable marketplace response or missing local response record is not
   proof of absence.
3. No order, supply, shipment, reservation, print/application record,
   replacement flow or other local operation has consumed or committed the
   code.
4. No verified external result indicates that the code was accepted, bound,
   introduced into circulation or otherwise made non-reusable.
5. The code is not void for an independent business reason such as confirmed
   defect, manual invalidation, duplicate/conflicting identity, ownership
   conflict or policy prohibition.
6. The evidence used by a preview or reconciliation has not changed. A
   concurrent reservation, successful binding or ownership/state change stops
   recovery instead of applying a stale decision.

Failure of any check leaves the code unavailable. Automatic recovery is
allowed only when every mandatory check is positive and internally consistent;
operator convenience or shortage pressure is not an oracle for code safety.

## State and transaction contract

- Closing the failed binding attempt, changing the code state and updating the
  available-pool result form one atomic operation. No observable state may show
  the attempt closed while the code remains accidentally lost, or the code
  available while its binding outcome is unresolved.
- A recovered code appears exactly once in the correct available pool. It is
  not duplicated across products, sellers, tenants or warehouse contexts.
- A code that remains unavailable contributes to no available-code count and
  cannot be selected, reserved, printed, applied or shipped by any automatic or
  manual allocation path that expects an available code.
- Retry, duplicate delivery, worker replay, process restart and ordinary reload
  preserve the same result. Repeating recovery cannot create a second code,
  erase a later legitimate state or repeat an external side effect.
- A concurrent successful use wins over stale recovery. WMS must reject or
  reclassify the recovery attempt, never overwrite the newer business state.
- Partial batch failure is isolated per code. A valid recovery does not make an
  ambiguous row reusable, and one bad row does not falsify the result of other
  independently committed rows.
- Historical `void`, binding-attempt and recovery events are retained. Product
  approves a state correction with append-only evidence, not rewriting history
  to pretend that the erroneous or protective `void` never occurred.

S11 does not choose table structure, transaction primitives, lock order,
retry count, timeout, job shape or migration tooling. S13 must choose those
mechanics while preserving the product invariants above, and S14 must attack
the plan independently.

## Unavailable reason contract

Every code that does not return to `available` must have one stable reason
category and human-readable meaning. The downstream design may choose exact
identifiers, but it must distinguish at least:

- external binding confirmed or external use confirmed;
- external outcome unknown or reconciliation unavailable;
- local reservation, application, shipment or other use exists;
- tenant, seller, product or ownership mismatch;
- duplicate, conflicting or invalid code identity;
- explicit manual, defect or policy invalidation;
- concurrent state change or stale recovery evidence;
- recovery failed before an atomic result was committed.

Generic `void`, `error`, `failed` or an empty reason is not sufficient for the
authorized user or for audit. The reason must identify why reuse is unsafe and,
where action is possible, what event or controlled review can make the code
eligible for reconsideration. It must not expose raw marking-code data or
foreign-tenant record existence.

A later change from unavailable to available, or from one unavailable reason
to another, is a new auditable decision. It does not overwrite the reason that
was valid for the earlier decision.

## User and warehouse effect

The operator must see an honest available-code quantity after recovery. A code
proved reusable returns to normal allocation without an extra confirmation step
or a special packing path. A code that remains unavailable must be discoverable
to the authorized user with its understandable reason; the user must not have
to infer the cause from a raw status, database value or support request.

This is not approval for a new warehouse process. Existing packing, marking
and shipment actions keep their current sequence and eligibility rules. The
change corrects code-pool truth and explains protective exclusion. It must not
make the operator choose between "continue" and "risk reusing a code".

The intake explicitly requires the reason to be shown to a user, while the
current impact packet does not declare `ui_change`. S12 and S13 must identify
the existing authorized read surface that can satisfy this requirement. If no
existing surface already presents the reason without a visible change, impact
classification must add `ui_change` before S16 and route the task through S09,
S10, S24 and live Product Browser acceptance. This S11 verdict does not waive
those stages.

## Tenant and authorization safety

- Every lookup, eligibility check, mutation, count and read-back is scoped to
  the authorized tenant. Seller and product ownership are validated separately
  inside that tenant.
- A matching code, product, attempt or external result from another tenant or
  seller is never evidence for recovery and is never changed as a side effect.
- A foreign identifier must not reveal whether the foreign record exists. The
  authorized user receives the same safe denial or unavailable result without
  cross-tenant detail.
- Authorization and ownership are rechecked at the write boundary; a prior
  preview, queued job or client-supplied tenant field is not trusted.
- Batch reconciliation cannot widen tenant, seller or warehouse scope. Per-code
  isolation and read-back must prove that no neighboring tenant or seller was
  read, counted or mutated.

## Audit and evidence contract

For each evaluated code, the durable audit trail must make the decision
reconstructable and retain:

- policy/version, correlation or batch id, time and authorized actor/job;
- tenant, seller and product/pool references;
- stable masked code reference or fingerprint, never a raw CIS/DataMatrix in
  ordinary logs, screenshots, receipts or Git evidence;
- failed binding attempt reference and the observed external outcome class;
- state and reason before evaluation, every mandatory eligibility result, the
  final state and final reason;
- whether the row was recovered, kept unavailable, skipped because evidence
  changed, or failed without commit;
- atomic mutation result and post-write read-back;
- reference to any later decision that supersedes this one.

Audit events are append-only. Available-pool totals must reconcile to the
source population: recovered, unavailable by reason, concurrently changed,
skipped and failed rows cannot disappear from the accounting.

## Existing-data and migration boundaries

S12 and S13 must preserve these constraints for existing `void` rows:

- first build a non-mutating inventory grouped by tenant, seller, product/pool,
  observed binding outcome and current unavailable reason;
- reconcile the full source population before mutation, including rows whose
  outcome is unknown, contradictory or missing;
- auto-recover only rows that satisfy every eligibility rule on current
  evidence; ambiguous historical rows remain unavailable with an explicit
  reason and review path;
- use restartable, idempotent units with stale-evidence checks and post-write
  read-back;
- provide additive compatibility for old readers/writers during rollout and
  prevent them from recreating reasonless `void` rows;
- rehearse restore/rollback honestly. Rollback may stop new recovery or restore
  newly changed rows only when doing so cannot erase later legitimate use or
  audit events; it must not claim that data was reverted when safe reversal is
  impossible.

The dependency on `BLG-F01` means BLG-D17's unavailable reasons, affected
operation and exact unblock condition must integrate with the canonical blocker
and dependency registry when that capability is available. `BLG-F01` is still
at S11, but the controller reports no `blocked_by` edge for BLG-D17. Therefore
this Product contract may pass now; downstream work must keep the reason and
dependency explicit locally and must not treat the unfinished registry as
permission to omit them.

## Required downstream proof

S12 must keep recovery as a vertical outcome: failed binding classification,
eligibility decision, atomic code-state change, available count, user-visible
reason, audit and read-back must not be accepted as unrelated partial cards.

S13 must define the authoritative state machine, transaction and concurrency
boundaries, source of truth for external outcome, migration/backfill plan,
compatibility path, reason taxonomy, locks/resources and restore policy. S14
must independently falsify uncertain external outcome, stale evidence,
cross-tenant access, duplicate execution and unsafe rollback.

S15 must create direct and breaker cases covering at least:

- definitive external failure with no local use returns one code to available;
- timeout, lost response and contradictory external/local evidence remain
  unavailable with distinct reasons;
- confirmed external binding or local reservation/use never returns available;
- manual/defect invalidation remains unavailable for its independent reason;
- same code or matching identifiers in another tenant or seller;
- stale preview followed by concurrent reservation, binding or shipment;
- duplicate request, retry, worker replay, restart and partial batch failure;
- available-pool count, allocation exclusion, read-back and ordinary reload;
- existing reasonless `void` rows and mixed historical batches;
- append-only audit, population reconciliation, migration compatibility,
  integrity proof and restore/rollback rehearsal.

S22 and S23 must prove the negative-authorization and cross-tenant isolation
receipts required by `tenant_sensitive`, and the migration, backfill, integrity
and restore/rollback receipts required by `database_change`. Tests use isolated
fixtures and emulator or controlled evidence only. No live WB/Ozon call,
production code mutation or production marking-code repair is authorized.

## Out of scope and authorization

S11 does not implement code, choose schema, inspect or repair production data,
call a marketplace, redesign packing, create a new manual code-release action,
access secrets, deploy, merge, commit or push. It does not approve reuse of a
code with an uncertain outcome merely to correct a shortage.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: a code enters `available` only after WMS proves
that binding and all other use are absent and commits recovery atomically;
otherwise it remains unavailable with a durable, user-visible reason, complete
audit history and explicit tenant-isolation proof.
