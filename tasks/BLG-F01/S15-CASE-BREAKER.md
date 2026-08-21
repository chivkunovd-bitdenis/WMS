# S15 CASE BREAKER - BLG-F01

## Binding

- Task: `BLG-F01`
- Stage: `S15 CASE_FACTORY`
- Role: `pipeline-case-breaker`
- Independence: this worker did not author the S15 cases or factory
- Package commit: `1f5f2289e65dba63d2de01d8485f294cf2453053`
- Reviewed `S15-CASES.json` SHA-256:
  `c593026fb41136b2bde8164d34a00abe9cc3763ee506447ca40ffa880cb90779`
- Reviewed `S15-CASE-FACTORY.md` SHA-256:
  `af0af7e23cfe835be535b87af8197ca7aef52ae213720d78375a541ec43c516f`
- Accepted S13 SHA-256:
  `d1ca8d5967ed8527595d7c43969464a023c989496aa3658e6d2f85f13377f167`
- Reviewed accepted S14 SHA-256:
  `b8961ff0ef833afd0abe35dbe3cffdf210d7a09761a5696d0a4c656956956ac6`

## Verdict

`CASE_BREAKER_FAILED`

The package is concrete and substantially adversarial, but it does not yet
encode every mandatory accepted S13/S14 boundary. The omissions below can let
S19 implement a green suite while leaving accepted control-plane behavior
untested. This is an S15 case defect, not implementation discretion.

No controller transition, audit, S16, Dev, release or live operation was
performed by this breaker.

## What survived the break attempt

- The JSON contains 23 unique cases: 10 direct and 13 breaker cases, with 23
  unique planned executable references.
- Every case is local-only, has a named fixture, reset contract, timeout,
  oracle, read-back, reload assertion and `PLANNED_FOR_S19` binding.
- Every case ID is referenced by the coverage matrix; there are no unknown
  coverage IDs.
- `BLK-PROCESS-001` has direct and negative coverage for the non-circular
  S15-S23 path, pre-S25 narrow, post-S25 close, wrong/self/stale authorizers and
  scope broadening.
- The exact Git authority, compare-and-swap, publication, fresh-checkout CI,
  crash replay, projection tampering and entrypoint parity have direct and
  destructive lanes.
- BLG-D05 is kept behind the post-S25/post-closure capability receipt and the
  proposed cases do not let BLG-F01 mutate D05 state or grant D05 Product
  approval.
- The future executable files are correctly marked as S19 plans. Their current
  absence is not treated as an S15 failure.

## Blocking findings

### CB-F01 - mandatory typed `ACCESS` route is absent

Accepted S13 requires direct local proof for `ENV`, `FIXTURE`, `ACCESS`,
`ORACLE_CONFLICT` and `BUDGET_HARD_STOP`. Accepted S14 repeats the same five
reviewed routes. The S15 factory, coverage row, `F01-C1-09` and `F01-C1-B10`
name only four and omit `ACCESS` entirely.

This permits a future implementation to mishandle access holds, broaden them
globally, assign the wrong closure role, or resume the wrong scope while the
declared S15 suite remains green.

Minimum closure:

1. Extend `F01-C1-09` to parameterize all five exact source-event kinds,
   including `ACCESS`, and assert definition hash, creator binding, owner or
   oracle, evidence contract, denied operation/stage, task scope and resume
   stage for each kind.
2. Extend `F01-C1-B10` to include an active `ACCESS` occurrence and prove that
   its adjacent operation, unrelated task and cross-task narrow/close remain
   unaffected or rejected as applicable.
3. Update the S15 coverage row and factory matrix to name `ACCESS` explicitly.

### CB-F02 - no positive exact-scope resume for typed dynamic holds

Accepted S13 requires exact-scope resume to succeed only with the required
repair/oracle binding. `F01-C1-09` stops after occurrence creation and
inspection. `F01-C1-B03` proves invalid closure fails, and `F01-C1-B10` proves
over-blocking/cross-task attempts fail, but no direct case proves a valid
`ENV`, `FIXTURE`, `ACCESS`, `ORACLE_CONFLICT` or `BUDGET_HARD_STOP` repair
actually narrows or closes the same occurrence and resumes only its declared
stage without synthesizing skipped receipts.

Minimum closure:

1. Extend the parameterized direct route case, or add one direct case, that
   supplies the exact definition revision, occurrence scope and required
   repair/oracle identity for every typed route.
2. Assert one hash-linked narrow/close event, exact remaining scope, ordinary
   gate re-evaluation, no unrelated-task mutation and restart-stable result.
3. Retain negative wrong-role, stale-revision, self-authored and cross-task
   variants in the breaker lane.

### CB-F03 - three accepted lifecycle/compatibility proofs are not specified

The accepted S13 proof list additionally requires:

- valid closed, superseded and reopened history to remain hash-linked and
  traceable;
- a registry revision change to invalidate only affected downstream receipts;
- previous-controller rollback to read the additive v2 compatibility view
  without interpreting an empty task scope as global.

The current package rejects malformed or contradictory history in
`F01-C1-B09`, but does not exercise a valid supersede/reopen chain. The obsolete
receipt variant in `F01-C1-B04` is not a registry-revision invalidation test.
The empty-scope worker attack in `F01-C1-B07` is not a previous-controller
compatibility read.

Minimum closure:

1. Add or extend a direct lifecycle case with valid close, definition
   supersede and occurrence reopen events, asserting every prior event/hash is
   still queryable after restart.
2. Add a two-task revision fixture proving only receipts whose blocker
   definition, occurrence scope or dependency path changed are invalidated.
3. Add a previous-controller compatibility fixture proving the additive v1
   view is conservative and an empty task list never becomes a global block.

### CB-F04 - deterministic fixture omits pinned clock and random seed

Pipeline section 22 requires fixed clock and random seed for every run. The
common fixture describes fresh repositories, namespaces and deterministic
journals, but it does not pin time or randomness. These cases compare event
hashes, commit objects, replay and publication, so uncontrolled timestamps or
random IDs can make identical runs produce different authority commits and
decision evidence.

Minimum closure:

1. Add a frozen clock, deterministic random seed and deterministic
   idempotency/event-key sequence to `blg-f01-blocker-registry-local-v1`.
2. Make reset recreate those values and teardown assert no case-owned ref,
   journal entry, projection or publication retry leaks into the next case.

## Non-blocking package correction

The factory introduction says there are nine independent breaker lanes, while
the JSON contains thirteen (`F01-C1-B01` through `F01-C1-B13`). Correct that
count during the required BA repair so the human artifact and machine package
describe the same fixed set.

## Exact minimum closure artifact and next action

Return to `pipeline-ba` S15 repair. The minimum closure is a new hash-bound
revision of both:

- `tasks/BLG-F01/S15-CASES.json`
- `tasks/BLG-F01/S15-CASE-FACTORY.md`

The revision must close CB-F01 through CB-F04 without changing the accepted
S13/S14 oracle or weakening the existing 23 cases. After repair, assign a
different independent `pipeline-case-breaker` to verify the new hashes. Only a
passing breaker result may proceed to an independent `pipeline-case-auditor`.
