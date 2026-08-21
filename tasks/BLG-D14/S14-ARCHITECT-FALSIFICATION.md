# S14 ARCHITECT_FALSIFICATION - BLG-D14

## Binding

- Task: `BLG-D14`
- Card: `BLG-D14-C1`
- Stage: `S14 ARCHITECT_FALSIFICATION`
- Role: `pipeline-reviewer`
- Agent: `codex-blg-d14-s14-pipeline-reviewer`
- Reviewed baseline: `69c271678782d7dcfa39df97cd905cbee1678727`
- Reviewed plan: `tasks/BLG-D14/S13-ARCHITECT-PLAN.md`

## Verdict

`BLOCKED` with arbiter decision `REPLAN`.

The S13 plan correctly identifies and removes the observed order-row to seller-
lock inversion, but it does not yet prove the two properties that make the
Product contract safe: ownership of one PostgreSQL advisory lock across the
proposed multi-transaction T1/E1/T2 flow, and exactly-once recovery when the WB
supply-create side effect succeeds but its identifier is not durably recorded.
Those are high-risk architecture conflicts, so `ARCH_REVIEW_PASSED` is not
permitted and development remains prohibited.

## Independent model built before reading S13

The current creator locks selected `fbs_orders` in ascending UUID order and
then waits up to 15 seconds for `wb_seller_lock`. The status poller takes the
same seller lock first and then locks `fbs_orders` while WB status HTTP is in
flight. An overlap can therefore form the exact cycle `creator: orders ->
seller` against `poller: seller -> orders`.

The independent safe model required:

1. one seller-first coordination order for every creator, resume and poller
   apply path, followed by operation, supply, order and dependent rows in a
   deterministic order;
2. no PostgreSQL row lock across WB HTTP;
3. bounded, SQLSTATE-specific retries that always start from a fresh database
   transaction and never reinterpret a business-state change as transient;
4. a durable phase/correlation record that makes a crash or lost response at
   every external boundary recoverable without a second WB supply-create;
5. success only after committed local membership and fresh API read-back; and
6. a PostgreSQL 155-order overlap harness that proves all of those properties,
   including process death immediately after the external create side effect.

S13 independently reached items 1-3 and the read-back half of item 5. The
following unresolved attacks prevent acceptance.

## Blocking findings

### F1 - Advisory-lock ownership is not valid across the proposed commits

Severity: critical. Finding type: `PLAN`.

S13 keeps the existing session-scoped `pg_try_advisory_lock` across T1 commit,
the lock-free E1 database interval and T2. PostgreSQL session locks belong to a
physical backend connection, not to an SQLAlchemy `AsyncSession`. After commit
or rollback, SQLAlchemy may return that connection to the pool; a later query
or `pg_advisory_unlock` is not guaranteed to execute on the same backend. The
plan therefore permits either a leaked seller lock or T2 running on another
connection while the original pooled connection still owns the lock. A
`finally` block on `AsyncSession` does not prove connection identity.

Minimum closure:

- choose and document one connection-ownership design: pin a dedicated
  `AsyncConnection` for the full advisory-lock lifetime, or replace the
  cross-transaction session lock with a transaction/job coordination design;
- define commit, rollback, cancellation, task death and pool-invalidation
  behavior for that design; and
- require evidence of the same PostgreSQL backend identity for acquire and
  release, plus a negative test showing no pooled connection retains the lock
  after success, error, timeout or cancellation.

### F2 - Crash after WB create can still create a second external supply

Severity: critical. Finding type: `PLAN | EXTERNAL`.

T1 persists a local operation and pending supply but has no WB supply ID. E1
then performs `POST /api/v3/supplies`. If WB accepts the create and the process
dies, the response is lost, or the process dies before the ID is written in a
new short transaction, the durable operation is indistinguishable from one
that never called WB. The current client exposes read-back only by known supply
ID; S13 defines neither an officially verified idempotency key for create nor a
deterministic lookup/correlation contract for recovering the unknown ID.

The statement "never replay blindly" is therefore not executable. The
existing local unique constraint prevents a second operation row, but it
cannot prevent a second WB supply created by a retry. The same gap invalidates
the required lost-response assertion immediately after WB create in the
155-order case.

Minimum closure:

- cite a versioned external contract or emulator-faithful primitive that makes
  supply creation idempotent, or define a deterministic, collision-safe lookup
  by a durable correlation value written before the POST;
- specify the exact state transition before and immediately after WB create,
  including crash before response, after response and before local commit;
- if WB offers neither primitive, define a fail-closed reconciliation/manual
  outcome that never performs a second create and reconcile it with the Product
  requirement for a direct safe retry; and
- make the test double reject any invented idempotency or lookup behavior not
  supported by the verified contract.

### F3 - Retry and timeout policy lacks one end-to-end deadline

Severity: high. Finding type: `PLAN`.

The short-transaction retry policy is specific, but its claimed under-seven-
second recovery envelope excludes statements that each receive a ten-second
timeout. It also composes with a 15-second seller-lock wait and up to four
60-second WB request waits for 155 orders. No overall API/workflow deadline,
durable continuation boundary or cancellation ownership is defined. A client
or ingress timeout can therefore occur while the server still owns the seller
lock or continues an external effect, leaving the operator in the exact
uncertain-response state this card must resolve.

Minimum closure:

- state separate hard deadlines for seller-lock acquisition, each database
  transaction, each external call and the complete synchronous request;
- define what commits and what durable state is returned when the outer
  request is cancelled or its deadline expires at every phase; and
- ensure the operator-facing retry/read-back path remains valid when work
  continues asynchronously or stops at the deadline.

## Checks that survived falsification

- The canonical seller -> operation -> supply -> ascending order -> dependent
  row order removes the currently observed creator/poller cycle when every
  path follows it.
- Preview reads before coordination are safe only as non-authoritative reads;
  locked revalidation remains mandatory before mutation.
- PostgreSQL concurrency retries are correctly limited to `40P01`, `40001`
  and `55P03`, require full rollback, fresh ORM state and reacquisition in
  canonical order, and exclude authorization and business conflicts.
- `confirmed` read-back, same-key retries, request-hash mismatch and fresh
  workspace/reload verification are the right local idempotency boundaries
  once F2 is closed.
- Poller non-blocking seller acquisition and busy-skip replay are acceptable,
  provided F1 proves lock ownership and stale fetched statuses are revalidated
  under the canonical short apply transaction.

## Required 155-order closure case

The S13 fixture shape is retained, but it cannot pass until F1-F3 are repaired.
The revised breaker case must use PostgreSQL, exactly 155 orders, fixed inverse
input order, full/subset/no overlap and barriers for creator-first and poller-
first schedules. In addition it must:

- record PostgreSQL backend identity at seller-lock acquire/release and inspect
  the pool for a retained advisory lock after every exit path;
- kill the process after T1, immediately after WB accepts create but before the
  ID is durably stored, after each 100/55 add batch and immediately after T2
  commit;
- assert the external-create call count is at most one without granting the
  emulator an unsupported idempotency behavior;
- exercise the complete request deadline and cancellation at each phase;
- prove at most one local and external supply, exact 155-order membership on
  success, no partial local membership on failure, bounded attempt counts,
  preserved poller updates and stable read-back/reload digests; and
- prove no session remains `idle in transaction`, no advisory lock remains in
  the pool and no traffic reaches live WB/Ozon or production data.

## Scope and safety judgement

This stage reviewed architecture and current code only. It performed no Dev or
implementation, test execution, migration, commit, push, deployment,
production request, secret access or live WB/Ozon action. No unrelated worker
diff was modified.

## Minimum closure artifact and handoff

Return to `S13 ARCHITECT_PLAN`, owned by `solution-architect`. The minimum
closure artifact is a revised `tasks/BLG-D14/S13-ARCHITECT-PLAN.md` that closes
F1-F3 with:

1. a connection-safe advisory-lock lifecycle across all transaction phases;
2. a verified crash-after-WB-create recovery contract that cannot create a
   second external supply;
3. one composable end-to-end retry/timeout/cancellation policy; and
4. an updated 155-order overlap case proving those exact boundaries.

After controller resume and a new S13 receipt, S14 must be dispatched to an
independent reviewer again. S15 and all development stages remain blocked.
