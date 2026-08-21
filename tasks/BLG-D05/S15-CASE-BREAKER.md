# S15 independent case-breaker recheck - BLG-D05

## Verdict

`CASE_BREAKER_PASSED`

This recheck is limited to repaired breaker case `D05-C2-16`. The reviewer is
independent from the `pipeline-ba` that wrote the repair. `D05-C2-15` and the
full coverage matrix are not reopened or re-audited here. This review does not
change controller state, advance or resume S15, authorize S16/Dev/release, or
use live data or external calls.

## Reviewed package

- `S15-CASES.json`: `sha256:6c758c8d99c5080ae828d4a1a14f3db6c19e42f65fb0c0be93947cc5ab0028e1`
- `S15-CASE-FACTORY.md`: `sha256:5a5de1df4b6b847060fc072f54847678d3ac3b64545f9a6d837b0f3f2724e0c0`
- Oracle: C2 AC04 and the approved S13 controlled-CLI, per-decision locking,
  derived-idempotency and atomic event/projection contract.

## Breaker result for `D05-C2-16`

The repaired attack lane is executable against the approved architecture:

1. It invokes two local controlled CLI `apply` processes for the same approved
   run and frozen decision precondition. It does not introduce an API, Celery,
   Redis, a queue or a background worker.
2. The processes synchronize immediately before the per-decision lock and
   require the S13 `FOR UPDATE` boundary to serialize the competing applies.
   This directly attacks the approved concurrent-double-apply handoff.
3. One process is terminated after the projection and append-only event commit
   but before sanitized CLI output. A fresh retry therefore tests the exact
   crash window where durable state exists but the caller did not observe the
   result.
4. Retry reuses the architecture-derived `(run_id, decision_id, operation,
   precondition_hash)` tuple. The case exposes no caller-supplied external
   idempotency key and asserts that the persisted result is returned without a
   second link, decision, audit fact or lifecycle transition.
5. The changed-precondition row must stop independently while current rows
   remain singly applied or recovered. Two fresh-process `read-back` runs must
   produce identical per-code terminal truth, masked lineage and reconciled
   totals.
6. This breaker does not reuse the direct mixed-batch fixture as decisive
   proof. Its independent failure lane is the concurrent CLI lock race combined
   with the post-commit/pre-output interruption and derived-tuple replay.

No S13 contract rework or additional minimum closure artifact is required for
`D05-C2-16`.

## Exact next action

Dispatch a distinct `case-auditor` to audit the complete S15 package at the two
exact hashes above. The controller must remain `WAITING` at S15 until that
independent audit records `CASE_AUDIT_PASSED`; this case-breaker must not perform
the audit, resume or advance.
