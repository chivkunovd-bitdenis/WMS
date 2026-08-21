# S15 CASE_FACTORY - BLG-D05

## Scope and verdict

This package translates the approved S11 contract, S12 cards `BLG-D05-C1` and
`BLG-D05-C2`, and S13 architecture plan into deterministic local cases. It
does not authorize implementation, migration, a direct repair, production data
access, or a live Denmarcs/WB/Ozon call.

**BA verdict:** `CASES_READY_PENDING_INDEPENDENT_AUDIT`.

`S15-CASES.json` contains fourteen GOLD cases. Each has a named synthetic
fixture, deterministic reset and a planned S19 runnable binding. The fixtures
use two tenants, two sellers, two warehouses and an isolated local database;
all code values are synthetic masked tokens. External egress is forbidden.

## Fixture and reset contract

Fixture `blg-d05-denmarcs-reconciliation-v1` starts from a versioned local
database snapshot containing `tenant-a/seller-a/warehouse-a` and
`tenant-b/seller-b/warehouse-b`. It has unique, ambiguous, foreign, consumed,
reserved and unlinked synthetic codes, their evidence snapshots, approved and
expired decisions, legacy unclassified rows, and an append-only audit baseline.
The S19 builder restores that snapshot before every case, uses a unique job and
idempotency key per run, drains only the task-local queue, and captures masked
trace/audit/read-back evidence. Reset deletes only the case-local database and
queue namespace, then restores the fixture snapshot; it never targets a shared
or live database.

## Coverage matrix

| Approved requirement / transition | Direct GOLD case | Breaker coverage | Oracle | S19 planned binding |
| --- | --- | --- | --- | --- |
| C1: uniquely evidenced same-tenant/seller code becomes a proposed confirmed link but remains non-allocatable | `D05-C1-01` | `D05-C1-06` | S11 fail-closed rule; C1 AC01 | `backend/tests/integration/test_denmarcs_reconciliation.py::test_c1_unique_confirmed_inventory` |
| C1: missing, multiple, conflicting or unapproved lineage never infers a target | `D05-C1-02` | `D05-C1-05` | C1 AC02; evidence is mandatory | `...::test_c1_ambiguous_and_changed_input_fail_closed` |
| C1: foreign tenant/seller records are neither candidates nor disclosed | `D05-C1-03` | `D05-C2-11` | `tenant_sensitive` negative authorization/isolation | `...::test_c1_foreign_candidate_is_absent` |
| C1: non-available lifecycle is skipped without history loss | `D05-C1-04` | `D05-C2-09` | C1 AC04; lifecycle invariant | `...::test_c1_lifecycle_ineligible_is_non_actionable` |
| C1: replay is stable; evidence change creates a new decision and invalidates the old approval | `D05-C1-05` | `D05-C2-09` | C1 AC05; append-only audit | `...::test_c1_replay_and_changed_evidence` |
| C1: paged/volume inventory reconciles population and masks code data | `D05-C1-06` | `D05-C1-03` | C1 total reconciliation; no raw code leakage | `...::test_c1_paged_population_and_masked_evidence` |
| C2: approved current code applies once, is read back and alone can re-enter existing allocation | `D05-C2-07` | `D05-C2-08`, `D05-C2-10` | C2 AC01; per-code atomicity | `...::test_c2_apply_and_read_back` |
| C2: quarantine is rejected by allocation, FBS scan and replacement selection | `D05-C2-08` | `D05-C2-10` | S11 no-auto-use rule | API/service integration harness + `...::test_c2_quarantine_exclusion` |
| C2: stale preview, changed ownership/lifecycle and concurrent reservation stop only that row | `D05-C2-09` | `D05-C2-10` | C2 AC03; mutation-time recheck | `...::test_c2_stale_and_concurrent_row_stops` |
| C2: mixed batch, crash/retry and duplicate request are atomic per code with reconciled totals | `D05-C2-10` | `D05-C2-09` | C2 AC04; idempotency | task-local worker/API harness `...::test_c2_partial_retry_idempotency` |
| C2: foreign apply has generic denial and changes neither tenant | `D05-C2-11` | `D05-C1-03` | C2 AC05; cross-tenant isolation | `...::test_c2_foreign_apply_is_generic_and_non_mutating` |
| C2: reassignment supersedes history, never overwrites it | `D05-C2-12` | `D05-C2-14` | C2 AC06; append-only history | `...::test_c2_reassignment_is_append_only` |
| Database change: legacy rows stay compatible and integrity reconciliation is exact | `D05-C2-13` | `D05-C2-14` | `database_change` compatibility/integrity | migration integration harness `...::test_d05_legacy_compatibility_and_integrity` |
| Database change: rollback removes only the reconciliation surface; post-use history is preserved | `D05-C2-14` | `D05-C2-12` | C2 AC06; restore/rollback rehearsal | migration restore harness `...::test_d05_restore_safe_and_post_use_skip` |

There are no uncovered applicable rows. No UI, print, mobile or external
marketplace case is applicable: the approved cards explicitly have no UI or
live-external change. The FBS scan and replacement assertions are service/API
negative-authorisation checks, not a new operator screen.

## Case-audit gate

This author is the `pipeline-ba` case writer, not an independent
`case-auditor`. Therefore this artifact does **not** claim
`CASE_AUDIT_PASSED`. S16 must not receive Product approval until a distinct
case-auditor reviews the exact hashes of this Markdown and `S15-CASES.json`,
checks the matrix for zero uncovered applicable rows, and records a separate
`CASE_AUDIT_PASSED` artifact/receipt. This is an audit gate, not an oracle
conflict or an implementation blocker.

## S19 binding plan

S19 must turn each named `PLANNED_FOR_S19` reference into a runnable test
without changing its oracle. It must provision the local fixture/reset contract
above, use transaction/read-back assertions for each mutation, capture generic
foreign-ID output, examine only masked audit fields, simulate lifecycle and
reservation races deterministically, and prove both rollback branches. Any
different fixture shape, a raw-code trace, a live endpoint, or a changed oracle
returns the package to S15/S13 as appropriate.

## Handoff

The case matrix is complete but awaiting independent audit. No controller
`advance` is submitted by this case writer because `CASES_READY` requires
`CASE_AUDIT_PASSED` under the active process. Next action: assign an independent
`case-auditor` to audit this immutable S15 package, then let the controller
record the allowed S15 verdict before S16.
