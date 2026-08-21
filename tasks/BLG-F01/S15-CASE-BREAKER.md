# S15 CASE BREAKER - BLG-F01

## Binding

- Task: `BLG-F01`
- Wave: `wave-a1b311d18f07`
- Stage under review: `S15 CASE_FACTORY`
- Role: `pipeline-case-breaker`
- Independence: this worker did not author the BA repair, audit the package,
  implement application/controller code, or perform Product, release or deploy work
- Reviewed BA repair commit:
  `f02f1b5ac48517deed06f3fbecdb20330baa9bb5`
- Reviewed `S15-CASE-FACTORY.md` SHA-256:
  `c7034971bb55ce952b7107e285573098ff39adf9c7fee959747db4ec9aa36eaa`
- Reviewed `S15-CASES.json` SHA-256:
  `30183a8120163b7533914009910d9f03fc1ec1cd78dcaad23142f6653c5460eb`

## Verdict

`CASE_BREAKER_PASSED`

The exact repaired package closes `CB-R01` and `CB-R02`. Its direct and breaker
lanes now define executable independent `ENV -> WAITING` and `FIXTURE -> REWORK`
records, a versioned prior persisted snapshot, stale and asymmetric channel
attacks, authority-derived rebuild behavior and two-restart read-back. No
blocking breaker finding remains for the reviewed hashes.

This verdict accepts only the repaired S15 attack-lane specification. It is not
`CASE_AUDIT_PASSED`, does not advance or resume controller state, and does not
authorize S16, Dev, release, deploy, production access or secret access.

## Closed findings

### CB-R01 - independent WAITING and REWORK routes: closed

`F01-C1-14` no longer reclassifies one failure. It creates two separately reset
task variants with different typed source events and named valid records:

- `EVT-F01-C1-14-ENV-WAITING` / `BLK-ROUTE-ENV` creates
  `BLO-F01-C1-14-ENV-WAITING`, disposition `WAITING`, owner
  `environment-owner-v1`, resume stage `S15`, no invalidation and null closure
  evidence.
- `EVT-F01-C1-14-FIXTURE-REWORK` / `BLK-ROUTE-FIXTURE` creates
  `BLO-F01-C1-14-FIXTURE-REWORK`, disposition `REWORK`, owner
  `fixture-owner-v1`, owning required stage `S15`, null closure evidence and
  exactly `[S15, S16]` invalidated receipts.

There is therefore no undocumented WAITING-to-REWORK transition to invent.
Both controls preserve `DEP-F01-C1-14-CANONICAL` independently. `F01-C1-B14`
mutates one field at a time against those named controls, including owner,
evidence, resume target, dependency path, stale orchestration projection and
invalidation set. Rejected variants have no lifecycle transition or stage
movement; the valid REWORK control has exactly one scoped invalidation.

### CB-R02 - prior-snapshot recovery: closed

The package adds fixture `blg-f01-blocker-registry-prior-snapshot-v1` with a
`controller-task-snapshot-v1` baseline. It pins the open ENV orchestration
occurrence, unresolved canonical dependency, separate owner bindings, null
closure-evidence states, `S15` resume stage, exact dependency path and empty
initial invalidation set.

The direct lane requires authority validation, deterministic projection rebuild
and identical authority/decision hashes plus channel fields after first and
second restart. The breaker lane separately attacks a stale orchestration
projection, a resolved dependency with an open orchestration occurrence, the
inverse asymmetric state and wrong-owner cross-channel resolution. Stale state
cannot authorize a transition; legal rebuilds derive both channels from the
authority and cannot normalize one channel from the other.

## Regression checks

### CA-F01 - full machine coverage chain remains closed

All 13 coverage rows retain the complete structured chain from requirement and
capability through transition, incident/block, direct case and breaker case.
The package has 28 unique GOLD IDs, split 14 direct and 14 breaker; every
coverage reference resolves to the declared role, and each row source resolves
through `case_provenance`.

### CA-F03 - planned evidence binding remains closed

All 28 cases retain unique case IDs and matching `test_id`, planned runnable
references, fixture version/builder, timeout, read-back/reload assertions and
`pipeline-case-execution-v1`. The profile still binds all 28 IDs to
`pipeline/evidence.schema.json` and requires the authority, decision, scope,
lifecycle/denial, command, timestamp, artifact-hash and redaction trace fields.

## Scope and next action

Only this breaker artifact was changed. No application code, controller state,
packet, receipt, audit, S16 artifact or external system was changed or invoked.

Next action: a distinct independent `pipeline-case-auditor` must audit the exact
factory/case hashes above. The orchestrator must not treat S15 as accepted or
advance Product S16 until that auditor produces `CASE_AUDIT_PASSED` for the same
package.
