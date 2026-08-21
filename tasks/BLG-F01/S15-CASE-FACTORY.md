# S15 CASE_FACTORY - BLG-F01

## BA verdict

`CASES_READY`

This repair package makes the approved BLG-F01 control-plane card executable before
implementation. It defines fourteen direct GOLD cases and fourteen independent
case-breaker attack lanes against one canonical blocker decision. It covers
only local controller, Git-object, CI-fixture and report/packet/state
projections. It does not authorize Dev, S16 Product approval, release, deploy,
production mutation, secret access, or a live marketplace call.

## Fixture contract and isolation

Every case uses `blg-f01-blocker-registry-local-v1`: a disposable local Git
repository with a bare controller remote, deterministic controller journal and
task projections for BLG-F01, BLG-D05 and one unrelated synthetic task. Each
case creates a fresh authority ref, exact registry objects, receipts and CI
checkout. The seed pins `clock_utc = 2026-08-21T00:00:00Z`,
`random_seed = blg-f01-blocker-registry-local-v1` and a deterministic
idempotency/event-key sequence derived from the case ID. Reset removes only
that case namespace, recreates those pinned values from the versioned fixture
seed, and teardown asserts that no case-owned ref, journal entry, projection or
publication retry leaks into the next case. The fixture intercepts external
egress and has no production data, credentials, deploy target, WB or Ozon
access.

`F01-C1-14` and `F01-C1-B14` additionally use the versioned
`blg-f01-blocker-registry-prior-snapshot-v1` compatibility fixture. It seeds a
previous-controller `controller-task-snapshot-v1` whose legacy
`state.blocker`/`resume_condition` projection and unresolved canonical
`blocked_by` dependency identify different authority occurrences. The fixture
pins their IDs, owner bindings, closure-evidence state, required resume stage,
dependency path and invalidated-receipt set. The new evaluator must validate
the snapshot against its authority commit, reject a stale projection, or
rebuild it deterministically; a second restart must produce the same channels
and decision hash. This is a local fixture only and is reset with the common
case namespace.

The planned S19 harnesses are
`scripts/testing/test_blg_f01_blocker_registry.py`,
`scripts/ci/check_blockers_registry.py`,
`scripts/ci/check_blocker_enforcement_metatests.py`,
`scripts/ci/check_pipeline_replay_metatests.py`, and CLI integration probes
for `scripts/pipeline/run.py` and `scripts/pipeline/dispatch.py`. S19 must bind
each named case to a runnable reference without changing its oracle.

## Coverage matrix

`S15-CASES.json.coverage` is the machine contract. Every row encodes the full
chain `requirement -> capability -> process transition -> incident/block ->
direct case -> breaker case`; `case_provenance` makes the case-to-source link
auditable, while `coverage_validation_contract` requires each referenced ID and
role to match. A `reviewed_na` source is permitted only when an acceptance
constraint is not a separately triaged incident or an active blocker.

| Requirement / capability / transition | Incident or block | Direct cases | Independent breaker lanes |
| --- | --- | --- | --- |
| Exact operation-scoped bootstrap gate through S15-S23 | `BLK-PROCESS-001` | `F01-C1-01`, `F01-C1-02` | `F01-C1-B01`, `F01-C1-B02` |
| Independent narrow/close transition without skipped gates | `BLK-PROCESS-001` | `F01-C1-03`, `F01-C1-04` | `F01-C1-B03`, `F01-C1-B04` |
| One authority object drives runtime, CI and projections | `INC-BLOCKER-AUTHORITY-PROJECTION-DIVERGENCE` | `F01-C1-05`, `F01-C1-06` | `F01-C1-B05`, `F01-C1-B06`, `F01-C1-B13` |
| Typed occurrence replay, exact scope and independent-card continuation | `INC-BLOCKER-OCCURRENCE-REPLAY-DIVERGENCE` | `F01-C1-07`, `F01-C1-08`, `F01-C1-09` | `F01-C1-B07`, `F01-C1-B08`, `F01-C1-B10` |
| Registry integrity constraint is reviewed but has no separate incident/block | `N/A-S12-INTEGRITY` | `F01-C1-08` | `F01-C1-B09`, `F01-C1-B12` |
| Hash-linked close, supersede and reopen | `INC-BLOCKER-LIFECYCLE-HISTORY-DIVERGENCE` | `F01-C1-11` | `F01-C1-B09` |
| Scoped invalidation and additive v1 compatibility | `INC-BLOCKER-V1-COMPATIBILITY-DIVERGENCE` | `F01-C1-12`, `F01-C1-13` | `F01-C1-B07`, `F01-C1-B09` |
| Post-S25/post-closure BLG-D05 capability boundary | `INC-BLG-D05-PREMATURE-CAPABILITY` | `F01-C1-10` | `F01-C1-B11` |
| Orchestration hold versus canonical dependency compatibility, including a prior persisted projection | `INC-STATE-BLOCKER-DEPENDENCY-CHANNEL-DIVERGENCE` | `F01-C1-14` | `F01-C1-B14` |
| Independent typed `ENV -> WAITING` and `FIXTURE -> REWORK` records, required-stage ownership and exact invalidation | `INC-FAILURE-ROUTE-DEPENDENCY-DIVERGENCE` | `F01-C1-14` | `F01-C1-B14` |

## Planned S19 evidence binding

Every one of the 28 GOLD cases names `pipeline-case-execution-v1` in
`S15-CASES.json`; that profile binds S19 to `pipeline/evidence.schema.json`.
Each runnable evidence manifest must record task/wave/case identity, fixture
version, pinned clock and event key, code SHA, authority and registry/decision
hashes, operation and scope, lifecycle or denial result, commands and
timestamps, artifact hashes, and verified redaction. A field may be `N/A` only
with an oracle-specific reason in the manifest.

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

`CASES_READY` makes this repaired fixed package available for a fresh
independent breaker review.
It is not `CASE_AUDIT_PASSED`, not Product approval, and not authorization for
S16, Dev, release or deploy.

## Handoff

Repair verdict: `REPAIR_SPEC_READY_AWAITING_INDEPENDENT_CASE_BREAKER`.

Next action: assign a different independent `case-breaker`, then an independent
`case-auditor`. Minimum closure artifact:
`tasks/BLG-F01/S15-CASE-AUDIT.md` with exact package hashes and
`CASE_AUDIT_PASSED`. Any coverage, oracle, isolation or binding finding returns
the card to S15.
