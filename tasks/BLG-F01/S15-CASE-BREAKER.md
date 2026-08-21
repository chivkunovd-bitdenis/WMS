# S15 CASE BREAKER - BLG-F01

## Binding

- Task: `BLG-F01`
- Wave: `wave-a1b311d18f07`
- Stage under review: `S15 CASE_FACTORY`
- Role: `pipeline-case-breaker`
- Independence: this worker did not author the BA repair, S13, S14, Product
  contract, application implementation or the preceding case audit
- Reviewed BA repair commit:
  `acf5aedd55b75bbe25049cc1c74e0ac30e902f76`
- Reviewed `S15-CASE-FACTORY.md` SHA-256:
  `b0ade144d55862e06a1f30ee39358b46256a154766071667b0ab50a48f97b545`
- Reviewed `S15-CASES.json` SHA-256:
  `be892cde46d6ea0d9e154e16321d7ff30e4073b1cb60139327126a6d9431a575`
- Accepted S13 SHA-256:
  `d1ca8d5967ed8527595d7c43969464a023c989496aa3658e6d2f85f13377f167`
- Accepted S14 SHA-256:
  `b8961ff0ef833afd0abe35dbe3cffdf210d7a09761a5696d0a4c656956956ac6`

## Verdict

`CASE_BREAKER_FAILED`

The repair closes the structural coverage defect `CA-F01` and the evidence
schema defect `CA-F03`. It does not yet close `CA-F02`: the new direct lane
combines two mutually exclusive failure-route outcomes without defining a
legal transition between them, and neither new lane exercises a prior persisted
task snapshot. That leaves the repaired compatibility oracle ambiguous and
partly impossible to execute without S19 inventing behavior.

This verdict returns only the S15 case package to BA repair. It does not reopen
S13/S14, change controller state, advance or resume the card, authorize S16 or
Dev, or provide release, deploy or production evidence.

## Blocking findings

### CB-R01 - F01-C1-14 has no executable WAITING-to-REWORK route

Severity: blocking. Reopens: `CA-F02` only.

`F01-C1-14` first creates a typed stage failure, routes that failure to
`WAITING`, and then says to route "the same failure" to `REWORK`. The fixture
does not name two different typed findings, two fresh task variants, a second
receipt, a valid resolution event, or any controller command that converts the
first route into the second.

That distinction is mandatory, not editorial. Pipeline failure routing assigns
one deterministic disposition and owning stage to a typed finding. `WAITING`
retains `state.blocker` plus `resume_condition`; `REWORK` clears those fields
and invalidates to the owning required stage. Without a named legal boundary
between the outcomes, an implementation can pass by silently reclassifying the
same event, clearing a blocker without closure evidence, or treating the two
states as unrelated despite the ordered prose.

`F01-C1-B14` repeats the ambiguity by attacking WAITING and REWORK variants but
does not identify the valid route records against which each forged variant is
compared. Its one generic assertion, "malformed routes fail closed", therefore
cannot prove that the valid paths preserve `blocked_by`, clear only the correct
orchestration projection and invalidate exactly once.

Minimum closure: make WAITING and REWORK explicit independent fresh-fixture
variants with named typed findings and expected route records. If an ordered
WAITING-to-REWORK journey is intended, name the intervening owner/oracle
evidence, occurrence lifecycle event, controller command and resulting stage
transition. The breaker variants must mutate one field at a time against those
valid records and assert exact pre/post state.

### CB-R02 - restart is covered, prior-snapshot compatibility is not

Severity: blocking. Reopens: `CA-F02` only.

Both new cases restart states they have just created under the repaired model.
Neither fixture seeds a previously persisted task snapshot containing the
legacy `state.blocker`/`resume_condition` projection alongside an unresolved
`blocked_by` dependency, then loads or rebuilds it under the new evaluator.
Consequently the cases do not decide whether restart preserves both channels,
rejects a stale projection, or deterministically regenerates it from authority;
all three implementations could claim compliance with the current prose.

Minimum closure: add a versioned prior-snapshot fixture and exact expected
result for load/rebuild, including channel identity, owner, closure evidence,
required resume stage, dependency path, invalidated receipts and the second
restart. Add destructive variants for a stale orchestration projection, a
resolved dependency with a still-open orchestration hold, and the inverse.

## Repaired lanes that passed

### CA-F01 - full coverage chain: closed

All thirteen machine coverage rows now contain requirement, capability,
process transition, typed incident/block (or reviewed N/A), non-empty direct
cases and non-empty breaker cases. The package has 28 unique GOLD IDs, every ID
is covered, every reference resolves, direct/breaker roles match, and each row's
incident/block is present in `case_provenance`. The chain is structured and can
be falsified without interpreting the Markdown matrix.

### CA-F03 - planned S19 evidence binding: closed

All 28 GOLD cases have a unique `executable_ref`, matching `test_id`, executor
type, fixture version/builder, common deterministic reset, timeout,
`PLANNED_FOR_S19`, read-back/reload oracle and
`pipeline-case-execution-v1`. That profile binds
`pipeline/evidence.schema.json`, lists all 28 IDs and requires the authority,
decision, scope, lifecycle/denial, command, timestamp, artifact-hash and
redaction trace fields. The explicit N/A rule prevents silent evidence gaps.

## Scope and next action

No application code, controller state, packet, receipt, S16 artifact, release
or external system was changed or invoked by this breaker.

Next action: independent `pipeline-ba` repair of `CB-R01` and `CB-R02` in the
S15 factory/case package. A fresh independent case-breaker must review the new
exact hashes before a different case-auditor can run.
