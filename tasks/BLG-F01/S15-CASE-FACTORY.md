# S15 CASE_FACTORY - BLG-F01

## BA verdict

`CASES_READY`

This package makes the approved BLG-F01 control-plane card executable before
implementation. It defines ten direct GOLD cases and nine independent
case-breaker attack lanes against one canonical blocker decision. It covers
only local controller, Git-object, CI-fixture and report/packet/state
projections. It does not authorize Dev, S16 Product approval, release, deploy,
production mutation, secret access, or a live marketplace call.

## Fixture contract and isolation

Every case uses `blg-f01-blocker-registry-local-v1`: a disposable local Git
repository with a bare controller remote, deterministic controller journal and
task projections for BLG-F01, BLG-D05 and one unrelated synthetic task. Each
case creates a fresh authority ref, exact registry objects, receipts and CI
checkout; reset removes only that case namespace and recreates it from the
versioned fixture seed. The fixture intercepts external egress and has no
production data, credentials, deploy target, WB or Ozon access.

The planned S19 harnesses are
`scripts/testing/test_blg_f01_blocker_registry.py`,
`scripts/ci/check_blockers_registry.py`,
`scripts/ci/check_blocker_enforcement_metatests.py`,
`scripts/ci/check_pipeline_replay_metatests.py`, and CLI integration probes
for `scripts/pipeline/run.py` and `scripts/pipeline/dispatch.py`. S19 must bind
each named case to a runnable reference without changing its oracle.

## Coverage matrix

| Requirement / transition | Direct cases | Independent breaker lanes | Oracle |
| --- | --- | --- | --- |
| `BLK-PROCESS-001` lets BLG-F01 complete S15-S23 but denies premature S25, S26 and close | `F01-C1-01`, `F01-C1-02` | `F01-C1-B01`, `F01-C1-B02` | S13 bootstrap and S14 F1 |
| Post-S23 independent authorizer narrows only final acceptance; post-S25 independent authorizer closes it | `F01-C1-03`, `F01-C1-04` | `F01-C1-B03`, `F01-C1-B04` | S13 lifecycle contract and S14 F1 |
| One exact authority Git object drives runtime, CI and packet/state/report projections | `F01-C1-05`, `F01-C1-06` | `F01-C1-B05`, `F01-C1-B06` | S13 authority/ref/CI contract and S14 F2 |
| Definition policy is immutable; typed task-scoped occurrences are idempotent and restart-stable | `F01-C1-07`, `F01-C1-08` | `F01-C1-B07`, `F01-C1-B08`, `F01-C1-B09` | S13 definition/occurrence contract and S14 F3 |
| Typed ENV, FIXTURE, ORACLE_CONFLICT and BUDGET_HARD_STOP events preserve exact scope and independent continuation | `F01-C1-09` | `F01-C1-B10` | S13 dynamic-hold routes and S14 F3 |
| BLG-D05 receives only a post-S25, post-closure capability receipt and still resolves its own blocker | `F01-C1-10` | `F01-C1-B11` | S13 dependency boundary and S14 D05 boundary |
| Registry integrity and entrypoint parity fail closed for malformed/contradictory registry and stale projections | `F01-C1-06`, `F01-C1-08` | `F01-C1-B12`, `F01-C1-B13` | S12 acceptance shape; S13 evaluator/entrypoints |

## Applicable dimensions and exclusions

The card is a critical `pipeline_change`; happy, forbidden, repeat/idempotency,
cancel/resume, concurrency/CAS, read-back/reload, outage/crash replay and
cross-task scope are applicable. UI, tenant-facing API, database migration,
worker queue, print/scanner/device and marketplace-contract cases are not:
this card must add no such behavior. “Reload” means controller restart, fresh
Git checkout and regenerated projections, not a browser refresh.

## Independent breaker and audit gate

I am `pipeline-ba` case writer, not the independent `case-breaker` or
`case-auditor`. Rows marked `case_role: breaker` specify attacks only; they are
not self-executed or self-accepted. A distinct case-breaker must verify the
attack-lane fixture plan. Then a distinct case-auditor must review exact hashes
of this Markdown and `S15-CASES.json`, zero uncovered applicable rows, every
S12 acceptance row, all S14 F1/F2/F3 and D05 boundaries, fixture isolation and
S19 references.

`CASES_READY` makes this fixed package available for that independent review.
It is not `CASE_AUDIT_PASSED`, not Product approval, and not authorization for
S16, Dev, release or deploy.

## Handoff

Next action: assign an independent `case-breaker`, then an independent
`case-auditor`. Minimum closure artifact:
`tasks/BLG-F01/S15-CASE-AUDIT.md` with exact package hashes and
`CASE_AUDIT_PASSED`. Any coverage, oracle, isolation or binding finding returns
the card to S15.
