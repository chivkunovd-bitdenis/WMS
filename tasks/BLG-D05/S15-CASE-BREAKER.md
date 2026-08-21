# S15 independent case-breaker review - BLG-D05

## Verdict

`CASE_BREAKER_FAILED`

This review is limited to repaired breaker cases `D05-C2-15` and
`D05-C2-16`. The reviewer is independent from the `pipeline-ba` that wrote the
repair. It does not change controller state, advance or resume S15, authorize
S16/Dev/release, or use live data or external calls.

## Reviewed package

- `S15-CASES.json`: `sha256:2015309f92aecd0a1fc93fd3fde8f58c72017e98a6e57426ff699ac3f4f37ba8`
- `S15-CASE-FACTORY.md`: `sha256:075e459e3abbde0375ab99c2fa61168dfe5f608a59bae405e41e52ede7ce4a61`
- Oracles: approved S11 product contract, S12 C2 AC02/AC04, and S13 architecture plan.

## Breaker findings

### `D05-C2-15` - passed

The case is an independent attack lane for C2 AC02. Unlike direct case
`D05-C2-08`, it bypasses the C2 selection path and injects five eligible-looking
quarantine variants at each allocation, FBS scan and replacement consumer
boundary. It names all required decision states (`REVIEW_REQUIRED`, unknown,
unreadable, expired approval and missing approval), requires zero link,
availability or lifecycle mutation, and proves durable exclusion after reload.
This is a valid fail-closed breaker for the S11 no-auto-use rule.

### `D05-C2-16` - failed

The attack lane is not executable against the approved D05 architecture:

1. S13 explicitly declares no background worker, Celery, Redis or queue and
   chooses a restartable controlled CLI. `D05-C2-16` instead depends on a
   task-local queue, reordered worker delivery, acknowledgement ordering and an
   API/worker recovery harness. Binding that case would introduce an
   unapproved execution surface and potentially a missing `background_worker`
   trait rather than break the approved C2 path.
2. S13 derives the idempotency key from `(run_id, decision_id, operation,
   precondition_hash)`. The case assumes a caller can submit the same key with
   a different body, but the approved CLI contract exposes no such client-keyed
   request. Therefore that conflict does not currently falsify C2 AC04.
3. S13's S15 handoff names crash/retry and concurrent double apply. The new case
   does not express the actual CLI concurrency boundary, so it does not supply
   independent breaker proof for the approved per-code transaction and
   idempotency journal.

## Direct/breaker provenance check

The JSON coverage row for C2 AC02 maps direct `D05-C2-08` to breaker
`D05-C2-15`; the C2 AC04 row maps direct `D05-C2-10` to breaker `D05-C2-16`.
Both rows use separate `direct_cases`, `breaker_cases` and `provenance` fields,
and both new cases have `case_role: breaker` plus an attack-lane provenance
object. The role/provenance schema defect from the prior audit is repaired, but
the invalid D05-C2-16 lane prevents breaker closure.

## Minimum closure artifact and exact next action

Repair only `D05-C2-16` and the matching matrix wording. Replace queue/message
ordering with a deterministic local CLI attack: two concurrent `apply`
invocations for the same run/decision/precondition, a process interruption
after commit but before CLI acknowledgement/output, and a retry using the same
derived idempotency tuple. Assert one projection mutation and one append-only
terminal audit fact per code, durable quarantine for the failed row, reconciled
totals, and identical read-back after retry/reload. If same-key/different-body
is still required, it first needs an S13/S12 contract rework that defines such
an input surface.

Exact next action: `pipeline-ba` repairs `D05-C2-16`; then a distinct
`case-breaker` rechecks that case. Do not dispatch `case-auditor` until
`CASE_BREAKER_PASSED` exists for the repaired exact hashes.
