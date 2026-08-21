# S15 independent case audit - BLG-F01

## Binding

- Task: `BLG-F01`
- Wave: `wave-a1b311d18f07`
- Stage audited: `S15 CASE_FACTORY`
- Role: `pipeline-case-auditor`
- Identity: `codex-pipeline-case-auditor-blg-f01-s15`
- Independence: this auditor did not author S13, S14, the S15 case package or
  the case-breaker verdict and did not change their expectations
- S15 package commit: `d19d07845feebdad012ccc1ded1e5a1b26e4fdd9`
- Case-breaker commit: `db2a87eca2075ab8cc0c080955345964ae6173f2`

## Verdict

`CASE_AUDIT_REWORK`

The repaired package has strong deterministic direct and destructive cases,
and the latest independent `CASE_BREAKER_PASSED` verdict is valid for its exact
hashes. The complete S15 acceptance gate still cannot pass because the package
does not make the required coverage chain machine-auditable, omits two
controller-state compatibility boundaries from its cases, and does not assign
an evidence schema to each required case.

This is an S15 case-package finding. It does not reopen the accepted S13/S14
architecture and does not authorize Product S16, Dev, release or deploy.

## Exact audited package

- `S11-PRODUCT-CONTRACT.md`:
  `sha256:715d3d5e02605865136bd60bf8957efc86c87cafddcb0232cd4560e85f9026fa`
- `S12-TASK-CUT.md`:
  `sha256:e05ab9314a57a3b8778a58faaa423d3d72ed522a13a10f7c3fb69ade527c3e66`
- `S13-ARCHITECT-PLAN.md`:
  `sha256:d1ca8d5967ed8527595d7c43969464a023c989496aa3658e6d2f85f13377f167`
- `S14-ARCHITECT-FALSIFICATION.md`:
  `sha256:b8961ff0ef833afd0abe35dbe3cffdf210d7a09761a5696d0a4c656956956ac6`
- `S15-CASE-FACTORY.md`:
  `sha256:fcb7118608d899588aa00bc3aa89524402fb8a0778d0da91ed7176da0f1c6590`
- `S15-CASES.json`:
  `sha256:93f96a3d502e40265e70bee8438f8681bdaa1aff0cc8a8de45157d1f0817354a`
- `S15-CASE-BREAKER.md`:
  `sha256:01922bcff06867a7a2ffbdf7c3d848cf8f045c26191c6e46c0f4ce8651c76bd3`

The factory and JSON hashes match package commit `d19d0784`; the breaker file
matches commit `db2a87e`. The accepted S13/S14 hashes also match the breaker
binding.

## Blocking findings

### CA-F01 - coverage rows do not encode the full mandatory chain

Pipeline v2 requires each applicable row to link `requirement -> capability ->
process transition -> incident/block -> direct case -> breaker cases`. The
eleven JSON rows stop at `process_transition` and then use one untyped `cases`
array. They have no `incident/block`, `direct_cases` or `breaker_cases` fields.
The Markdown matrix separates direct and breaker IDs, but it also omits the
incident/block link and is not the machine coverage contract.

This matters beyond field naming. Most case records have empty
`related_blocks`, all 26 have empty `related_incidents`, and the dynamic hold,
state-projection, failure-route and BLG-D05 rows cannot be traced to an exact
block/incident class from the coverage data. Therefore an empty
`uncovered_applicable_rows` assertion is self-reported rather than derivable.

Minimum closure: make every JSON coverage row identify the applicable
block/incident or an explicit reviewed `N/A`, split existing IDs into non-empty
`direct_cases` and `breaker_cases`, and add a machine check that all references
exist and match each case's `case_role` and related block/incident provenance.

### CA-F02 - state blocker channels and failure/rework routes are uncovered

The package checks packet/state/report parity and stale projections, but no case
distinguishes the controller's orchestration `state.blocker` plus
`resume_condition` from canonical registry dependencies in `blocked_by`. No
case proves their simultaneous projection, precedence, independent closure or
restart behavior.

The typed stage-failure route is described in S13, but the case package never
executes the controller failure/rework mapping. It does not prove that a
`WAITING` route creates only the scoped orchestration blocker, a `REWORK` route
clears that orchestration field without silently resolving `blocked_by`, a
route to a non-required stage fails closed, or invalidation resumes at the
declared owning stage while the dependency map remains intact.

Minimum closure: add direct and independent breaker coverage for
`state.blocker` versus `blocked_by`, including simultaneous conditions,
WAITING/REWORK outcomes, required-stage validation, exact invalidation and
restart/read-back. The cases must retain the business reason, owner role,
minimum evidence, resume condition and dependency path without allowing one
channel to close or overwrite the other.

### CA-F03 - required cases have no planned evidence-schema binding

All 26 GOLD cases have executor type, versioned fixture/reset, timeout, unique
planned S19 reference, deterministic clock/random/event keys and concrete
expected/read-back/reload prose. None names an `evidence_schema` or the
case-specific required evidence fields/artifact hashes. The common fixture
contract is not an evidence contract.

Without this binding, S19 can create a runnable boolean assertion while
omitting the exact authority object, registry/decision hashes, task and
operation scope, lifecycle event, candidate identity or read-back artifact
needed to prove the case. That would satisfy the current planned reference but
not Pipeline v2 evidence requirements.

Minimum closure: bind every required case to `pipeline/evidence.schema.json`
or a stricter versioned schema/profile and enumerate its required trace fields.
At minimum the profile must carry the task/wave, case ID, fixture version,
clock/event key, candidate/code SHA, authority and decision hashes, operation
and scope, lifecycle or denial result, command/timestamps, artifact hashes and
verified redaction status, with explicit N/A only where the oracle permits it.

## Confirmed strengths

- The package contains 26 unique GOLD cases: 13 direct and 13 breaker lanes.
- Every case has a fixture/builder, reset through the common fixture contract,
  executor, timeout, unique `executable_ref`, matching `test_id`,
  `PLANNED_FOR_S19`, oracle, read-back and reload assertion.
- The local fixture pins the clock, random seed and event-key sequence, resets
  per case, forbids external egress and excludes production, credentials,
  deploy and live WB/Ozon access.
- The breaker repairs for typed `ACCESS`, positive exact-scope resume,
  close/supersede/reopen history, targeted invalidation and conservative v1
  compatibility remain present.
- `BLK-PROCESS-001` bootstrap and BLG-D05 post-S25/post-closure capability
  boundaries have both direct and destructive case specifications.

These strengths do not remove the three blocking audit findings above, and
this auditor did not add the missing coverage or accept its own repair.

## Controller boundary and next legal action

The read-only controller snapshot already reports `current_stage: S16` with an
S15 `CASES_READY` receipt even though Pipeline v2 requires both `CASES_READY`
and independent `CASE_AUDIT_PASSED`. That snapshot is ahead of the legal gate;
it is not evidence that S15 acceptance occurred. This auditor did not run
`advance`, `resume`, S16 Product or any state mutation.

Return the exact package to an independent `pipeline-ba` S15 repair for
CA-F01 through CA-F03. After new factory/JSON hashes exist, a distinct
case-breaker must recheck affected attack lanes and a different case-auditor
must perform the complete audit. Only `CASE_AUDIT_PASSED` on those exact hashes
may let the orchestrator reconcile S15 and dispatch Product S16.
