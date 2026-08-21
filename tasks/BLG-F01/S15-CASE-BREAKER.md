# S15 CASE BREAKER - BLG-F01

## Binding

- Task: `BLG-F01`
- Wave: `wave-a1b311d18f07`
- Stage under review: `S15 CASE_FACTORY`
- Role: `pipeline-case-breaker`
- Independence: this worker did not author the repaired S15 package, S13 plan,
  S14 verdict, Product contract or application implementation
- Package commit: `d19d07845feebdad012ccc1ded1e5a1b26e4fdd9`
- Reviewed `S15-CASE-FACTORY.md` SHA-256:
  `fcb7118608d899588aa00bc3aa89524402fb8a0778d0da91ed7176da0f1c6590`
- Reviewed `S15-CASES.json` SHA-256:
  `93f96a3d502e40265e70bee8438f8681bdaa1aff0cc8a8de45157d1f0817354a`
- Accepted S13 SHA-256:
  `d1ca8d5967ed8527595d7c43969464a023c989496aa3658e6d2f85f13377f167`
- Accepted S14 SHA-256:
  `b8961ff0ef833afd0abe35dbe3cffdf210d7a09761a5696d0a4c656956956ac6`

## Verdict

`CASE_BREAKER_PASSED`

The repaired package closes `CB-F01` through `CB-F04` from the preceding
independent breaker review without weakening the existing bootstrap,
authority, dynamic-hold or BLG-D05 attack lanes. No uncovered applicable row,
unknown coverage reference, duplicate case ID or duplicate planned executable
binding was found.

This verdict approves the repaired package for an independent `case-auditor`.
It is not `CASE_AUDIT_PASSED`, Product approval, S16 authorization, Dev,
release or deploy evidence. This breaker performed no controller transition,
resume, packet generation, application change, production mutation, secret
access or live WB/Ozon operation.

## Recheck of prior blocker findings

### CB-F01 - typed ACCESS route: closed

`F01-C1-09` parameterizes all five reviewed typed source-event kinds: `ENV`,
`FIXTURE`, `ACCESS`, `ORACLE_CONFLICT` and `BUDGET_HARD_STOP`. The route records
the named definition hash/revision, exact task and operation/stage scope,
creator or reporter binding, evidence contract and resume stage. It does not
use an operator- or agent-authored prose condition as policy.

`F01-C1-B10` includes an active typed `ACCESS` occurrence and checks its
declared and adjacent operations, unrelated-task continuation and rejected
cross-task narrow/close. The machine coverage row and human matrix both name
`ACCESS` explicitly.

### CB-F02 - positive exact-scope resume: closed

`F01-C1-09` now supplies same-revision, same-scope fresh repair/oracle evidence
from the required independent binding for every typed route. It expects one
hash-linked narrow/close event, ordinary gate re-evaluation, resume of only the
declared stage, no synthetic skipped receipts, no unrelated-task mutation and
restart-stable read-back.

The negative boundary remains independent in `F01-C1-B03`, `F01-C1-B07` and
`F01-C1-B10`: self-authored, wrong-role, stale-definition, empty/global and
cross-task attempts fail closed.

### CB-F03 - lifecycle, invalidation and v1 compatibility: closed

- `F01-C1-11` executes a valid close, immutable definition supersession and
  typed reopen, then verifies the predecessor hashes, supersession link,
  closure evidence and reopened scope after restart.
- `F01-C1-12` uses two distinct task paths and changes only one definition or
  closure contract. Its oracle invalidates only receipts linked through the
  changed definition, occurrence scope or dependency path while preserving the
  unrelated path.
- `F01-C1-13` runs a previous-controller reader against the generated additive
  v1 view, proves that empty `affected_task_ids` is not interpreted as global,
  and forbids the compatibility reader from writing authority or lifecycle.

The malformed-history and empty/global attacks remain covered by
`F01-C1-B09` and `F01-C1-B07`.

### CB-F04 - deterministic fixture: closed

The common `blg-f01-blocker-registry-local-v1` fixture pins
`clock_utc = 2026-08-21T00:00:00Z`,
`random_seed = blg-f01-blocker-registry-local-v1` and a deterministic
idempotency/event-key sequence derived from case ID and fixture version. Reset
recreates those values; teardown asserts that case-owned refs, journal events,
projections and publication retries do not leak into the next case.

## Downstream executability check

The package contains 26 unique GOLD cases: 13 direct and 13 breaker lanes. All
26 have a versioned fixture/builder, steps, executor type, unique exact
`executable_ref`, matching `test_id`, `PLANNED_FOR_S19`, timeout, oracle,
read-back and reload assertion. Every case is referenced by the coverage
matrix, every coverage reference resolves, and
`case_audit_handoff.uncovered_applicable_rows` is empty.

The planned references are correctly future S19 bindings rather than claims
that test files already exist. Their assertions are specific enough for S18 to
implement the accepted contract, S19 to create runnable bindings and S22 to
execute deterministic local controller/Git/CI checks without rewriting the
oracle.

## State boundary and next action

Artifact blocker: none for the reviewed S15 hashes.

The current read-only `tasks/BLG-F01/state.json` snapshot already names S16 as
the current stage while this repaired package still requires an independent
case audit. This breaker did not alter that controller-owned state. The
orchestrator must bind this exact breaker verdict to the reviewed hashes,
obtain an independent `CASE_AUDIT_PASSED`, and reconcile the controller gate
before treating S16 or any downstream work as authorized.
