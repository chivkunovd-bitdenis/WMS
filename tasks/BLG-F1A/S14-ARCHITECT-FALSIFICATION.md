# S14 ARCHITECT_FALSIFICATION - BLG-F1A

## Binding

- Task: `BLG-F1A`
- Stage: `S14 ARCHITECT_FALSIFICATION`
- Role: `pipeline-reviewer`
- Agent: `codex-blg-f1a-s14-pipeline-reviewer`
- Branch: `codex/wms-pipeline-unified-v2-20260820`
- Reviewed checkout: `a6a2a40ce02530a919d4ea979e4f3322591a6a49`
- Reviewed Product contract SHA-256:
  `ccffae1e18b69d17c71a14c7d02561f62eeeba293c5dc660872c5c445e8bc4c0`
- Reviewed task cut SHA-256:
  `0d4ce399b81b94578b8e84e009640762eda99f246374d1e2502eefd16531139c`
- Reviewed S13 plan SHA-256:
  `2fc0fe5cd38bb5bce1a5fbd252b64e84434877c22d34caab6b964e6ec51327d5`
- Dependency plan inspected:
  `tasks/BLG-F01/S13-ARCHITECT-PLAN.md`, SHA-256
  `afbeec716dcdd60f95f43e994f2b36e410427d9e0e1c0fc0f41b5356d5b59223`

## Verdict

`BLOCKED` with arbiter decision `REPLAN`.

`ARCH_REVIEW_PASSED` is not permitted. The evidence-level model, artifact
obligation union, fail-closed result, public-entrypoint parity and exact
identity requirements are directionally sound, but the canonical BLG-F01
registry boundary is neither accepted nor unambiguous. The plan also leaves a
path-containment race unresolved. These are critical control-plane conflicts,
so S15 and development must not start.

## Falsification model

The safe composition has two authorities with disjoint responsibilities:

1. BLG-F1A evaluates artifact bytes and returns only an immutable evidence
   assessment: exact claim identity, required obligations, resolved artifact
   hashes, `PROVEN | NOT_PROVEN | CONTRADICTED` and evidence reason codes.
2. BLG-F01 is the sole authority that decides whether an operation is blocked,
   which stable blocker/dependency identity applies, who owns closure, what
   evidence closes it, and from which stage work resumes.
3. A claim-bearing controller mutation binds both policy hashes and both
   decision hashes in one controller transaction. It cannot publish a pass
   receipt between evidence evaluation and blocker evaluation.
4. BLG-F01's accepted adapter and shared controller/schema migration land
   before BLG-F1A integrates. Overlapping control-plane files are serialized
   under one lock order and one migration baseline.

The reviewed plan does not yet prove these properties.

## Blocking findings

### F1 - The canonical dependency boundary has no accepted S14 proof

Severity: critical. Finding type: `DEPENDENCY | PLAN`.

BLG-F01 currently reports `RUNNING` at `S14`. Its S13 plan exists, but
`tasks/BLG-F01/S14-ARCHITECT-FALSIFICATION.md` and
`docs/evidence/BLG-F01/S14-ARCH_REVIEW_PASSED.receipt.json` do not exist.
Therefore BLG-F01 has not yet supplied the independently accepted schema,
authority and lifecycle API that BLG-F1A names as a required integration
input.

BLG-F1A S13 instead treats this as a later S16/S17 implementation hold and
allows S14 to pass first. That is incompatible with the explicit S14 dispatch
condition: this review must not pass while the canonical registry boundary is
unproved.

Minimum closure:

- BLG-F01 reaches `ARCH_REVIEW_PASSED` through its controller-owned S14;
- the exact accepted BLG-F01 S13 plan hash, S14 artifact hash and S14 receipt
  hash are bound as BLG-F1A architecture inputs; and
- BLG-F1A S13 is revised against that accepted interface before a fresh,
  independent S14 review.

### F2 - Evidence policy duplicates canonical blocker routing truth

Severity: critical. Finding type: `AUTHORITY | PLAN`.

BLG-F01 S13 makes its registry decision the sole source for owner, minimum
closure evidence, resume condition and resume stage. BLG-F1A S13 also places
failure reason to owner/resume-stage mappings in `evidence-policy.yml`, returns
owner/resume/minimum-closure fields from `EvidenceDecision`, and includes the
same fields in `EvidenceFailure` before calling the future adapter.

Those fields are not merely artifact-validation facts. They decide who may
unblock work and where the pipeline resumes, so keeping them in the evidence
policy creates a second registry that can drift from BLG-F01. An adapter that
receives an already chosen owner, resume stage and closure artifact cannot be
the canonical decision authority.

Minimum closure:

- the BLG-F1A policy owns evidence levels, surfaces, artifact obligations and
  evidence-only reason codes;
- owner, blocker/dependency identity, closure contract and resume routing are
  removed from BLG-F1A policy and producer-controlled failure payloads;
- the accepted BLG-F01 evaluator derives those fields from its versioned
  registry using immutable evidence assessment inputs; and
- packet, state, report and receipt project the same canonical blocker
  decision hash, never a locally synthesized fallback.

### F3 - Overlapping controller migrations have no serialized integration plan

Severity: critical. Finding type: `RESOURCE_GRAPH | CONCURRENCY`.

Both BLG-F01 and BLG-F1A claim writes to `pipeline/controller.py`,
`pipeline/task-state.schema.json`, `pipeline/receipt.schema.json`,
`scripts/ci/check_pipeline_metatests.py` and `.github/workflows/ci.yml`.
BLG-F01 takes `control-plane:pipeline-v2`; BLG-F1A declares separate evidence
locks and a future adapter lock, but does not serialize behind the accepted
BLG-F01 candidate or define one migration/rebase and lock order.

Parallel implementation could overwrite schema assumptions, publish a receipt
with only one of the two decision hashes, or evaluate evidence against a stale
blocker snapshot. File-level conflict detection after implementation is not an
atomic controller contract.

Minimum closure:

- make BLG-F01 acceptance and candidate identity a hard predecessor for the
  overlapping integration write set;
- define canonical lock order and one atomic journal/state/receipt publication
  sequence for registry and evidence decisions;
- bind `blocker_registry_hash`, `blocker_decision_hash`,
  `evidence_policy_hash`, `evidence_manifest_hash` and
  `evidence_decision_hash` in the same claim-bearing receipt inputs/outputs;
- require re-evaluation when either policy input changes; and
- state whether BLG-F1A rebases onto BLG-F01 or a separately reviewed combined
  migration owns the shared files. Independent parallel edits are forbidden.

### F4 - Lexical/physical checks before open do not close the path-switch race

Severity: high. Finding type: `SECURITY | FILESYSTEM`.

S13 proposes lexical and physical containment checks, rejection of symlinks,
then opening and hashing one file descriptor. Hashing the opened bytes prevents
content substitution after open, but it does not prove that the opened file
remained beneath the allowed root if a parent directory or path component is
swapped between the pre-open containment check and `open`.

Minimum closure:

- define descriptor-relative traversal from a trusted evidence-root directory
  descriptor with no-follow/beneath semantics for every path component;
- verify the opened descriptor is a non-zero regular file and bind its
  device/inode, size and hash to the decision;
- fail closed where the runtime cannot provide the required containment
  primitive; and
- add a deterministic breaker that swaps a parent/path component during
  validation and proves that no outside-root bytes can be admitted.

## Checks that survived falsification

- Evidence obligations are a set union across all applicable surfaces; no
  numeric level or convenient artifact waives another required boundary.
- A pass receipt is an index of validated proof, not the proof itself, and must
  be written only after opened bytes are validated and hashed.
- Missing, empty, wrong-type, foreign, stale, changed, unsanitized or
  contradictory artifacts fail closed.
- Component tests cannot prove API, integrated, browser or production claims.
- E4 remains independent acceptance on the exact candidate, and E5 remains a
  separately authorized exact-production trace.
- Controller and CI should share one evidence resolver and stable evidence
  reason codes.
- Historical unbound receipts are not retroactively relabelled as proven.
- No live WB/Ozon, production, secret or deploy action belongs to this card.

These surviving points may be preserved in the revised plan, but they do not
offset F1-F4.

## Required replan artifact

Return to `S13 ARCHITECT_PLAN`, owned by `solution-architect`. The revised
`tasks/BLG-F1A/S13-ARCHITECT-PLAN.md` must:

1. bind the independently accepted BLG-F01 architecture and S14 receipt;
2. make the evidence assessment and canonical blocker decision schemas
   disjoint, with routing and closure owned only by BLG-F01;
3. specify one serialized shared-file migration, lock order, atomic decision
   publication and dual-policy invalidation contract; and
4. close the descriptor-relative path-containment race with runnable S15/S22
   attack cases.

After controller-directed return, a new S13 receipt and a fresh independent S14
dispatch are required. Until then the next stage remains S14 blocked on replan;
S15 and all development stages are prohibited.

## Scope and safety judgement

This stage performed architecture review and read-only inspection only. It did
not implement code, run product tests, modify controller state by hand, commit,
push, merge, deploy, access secrets, call production, or contact live WB/Ozon.
