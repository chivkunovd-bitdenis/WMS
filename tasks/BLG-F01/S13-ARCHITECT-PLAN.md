# S13 ARCHITECT_PLAN - BLG-F01

## Verdict

`ARCH_PLAN_READY`

BLG-F01 remains one atomic critical control-plane card. The implementation must
produce one versioned blocker decision for authoring, controller enforcement,
CI proof and audit. A richer `blocks.json` without runtime enforcement, or
controller checks backed by task-local copies, is not an acceptable partial
result.

The plan deliberately changes no warehouse UI, API, database, worker, queue,
print or mobile behavior. It requires no secret, live deployment, production
mutation or live Wildberries/Ozon call.

## Approved inputs and current baseline

- Product contract: `tasks/BLG-F01/S11-PRODUCT-CONTRACT.md`.
- Atomic cut: `tasks/BLG-F01/S12-TASK-CUT.md`.
- Pipeline contract: `pipeline/pipeline.yml`, status `ACTIVE`.
- Current registry: `docs/product/blocks.json`, version 1.
- Human view: `docs/process/BLOCKERS-REGISTRY-RU.md`.
- Current runtime authority: controller state and journal under
  `.pipeline-state/`, projected to `tasks/*/state.json`.

The current implementation is a useful bootstrap, not the required contract:

1. `active_blockers_for_backlog()` binds a filtered copy only at
   `start-wave`; tasks opened by other entrypoints and later registry changes
   do not receive the same decision.
2. `process_guard` and `backlog` records are explicitly skipped, so registry
   type changes can silently change enforcement.
3. Applicability is inferred only from the order of `resume_stage`; there is no
   explicit prohibited operation, trigger, scenario, surface or remaining
   scope for a narrowed blocker.
4. `resolve-blocker` accepts any existing repository path and a free-form
   `--by` string. It does not validate artifact kind, hash, freshness, scope,
   role/oracle authority or self-approval.
5. `blocked_by` and `blocker_resolutions` are detached task snapshots. Manual
   registry edits or stale snapshots can disagree with the active controller
   decision.
6. `check_blockers_registry.py` proves required fields and Markdown ID parity,
   but not dependency integrity, cycles, lifecycle history, decision parity or
   runtime refusal.
7. `resume`, `packet`, `report`, S25 and S26 do not all pass through one
   blocker evaluator.

## Architecture decision

### One logical registry, not two sources of truth

The canonical registry is identified by `registry_version + registry_hash`.
It has three representations with different responsibilities, but only one
decision function:

1. `docs/product/blocks.json` is the machine-readable Git projection and
   reviewed policy seed required by Product. It contains stable definitions,
   current materialized lifecycle, dependency edges and hash-linked history.
2. `.pipeline-state/blockers/state.json` and
   `.pipeline-state/blockers/journal.jsonl` are the controller-owned mutable
   authority. They are runtime data and are never hand-edited or committed.
3. Task `state.json`, packets, reports and receipts contain projections of a
   decision, never an independently editable blocker list.

The controller imports a Git projection only after schema, referential and
hash-chain validation. Every accepted lifecycle event atomically updates the
controller store and regenerates the Git projection. Runtime uses the
controller-owned snapshot; CI and a fresh checkout use the exact Git projection
whose hash is embedded in task decisions and receipts. A hash mismatch is an
invalid projection, not a choice between two answers.

### Additive registry v2 record

Registry v2 keeps the existing v1 fields so the previous controller can still
read a rolled-back artifact. It adds structured fields; no condition is parsed
from free-form text.

Each `BLK-*` record must contain:

- `revision` and a hash-linked `history[]` of open, narrow, close, supersede and
  reopen events;
- `lifecycle.status` in `open | narrowed | closed`, with timestamps and the
  event that produced the current state;
- `prohibition.operations`, using a closed enum such as `classify`, `dispatch`,
  `hold`, `resume`, `advance`, `final_acceptance`, `release_authorization`,
  `close` and `deploy`;
- `trigger`, expressed only through typed task/status/check fields;
- `scope.mode` plus exact arrays for task/backlog IDs, stages, scenarios,
  processes, surfaces, capabilities and checks;
- `remaining_scope` when status is `narrowed`;
- business/warehouse harm, denied-action message, owner role, required oracle,
  enforcing layers and minimum closure contract;
- typed directional dependency edges to blocker, task/backlog, stage,
  capability and check identities;
- evidence provenance, policy/schema version and last verification time.

Empty scope arrays never mean global. A global rule requires explicit
`scope.mode = global` and an explicit prohibited operation. A non-pipeline
resume target such as `activation_gate` is represented as a typed external
gate, not smuggled into a stage string. Pipeline-stage targets must resolve to
an ID in `pipeline.yml`.

`narrowed` is active only for `remaining_scope`; it is not an open broad rule
plus a prose exception. `closed` never blocks but remains in history. A
materially different prohibition gets a new ID and a typed relation to the old
record.

### Pure decision engine

`pipeline/blocker_registry.py` owns parsing, validation and deterministic
evaluation. Its core API is conceptually:

```text
evaluate(registry_snapshot, task_context, operation, stage, check_results)
  -> BlockerDecision
```

`BlockerDecision` contains the registry hash, task/context hash, operation,
stage, ordered applicable IDs, directional dependency paths, `allow | deny`,
human explanation, owner, minimum closure evidence, resume condition and
resume stage. Its stable hash is written to state, packet, report and the next
stage receipt input.

Matching is conjunctive across populated scope dimensions and disjunctive
within one dimension. Transitive blocking is allowed only through typed
directional edges and always returns the complete path. Unknown references,
cycles, contradictory current states or a broken history hash prevent a new
registry version from becoming active. The last valid version remains active;
if no valid version is recoverable, mutating controller entrypoints fail closed
with a registry-integrity hold while read-only reporting remains available.

### Controller entrypoint binding

Every supported entrypoint calls the same evaluator:

| Entrypoint | Evaluation and effect |
| --- | --- |
| `open` / `start-wave` / `classify` | Evaluate the exact classification operation from source/backlog identity; persist the decision hash, not a copied static list. |
| `next` / `packet` / `dispatch.py` | Evaluate `dispatch`; a denial produces a WAITING packet with the complete blocker explanation and dispatch refuses to hand work to an agent. |
| `hold` | Requires a stable registry blocker ID and creates a scoped occurrence; it cannot invent a free-form second blocker truth. |
| `resume` | Requires a valid closure/narrowing event for the same blocker revision and scope, then re-evaluates before changing task status. |
| `advance` | Evaluates `advance`; S25 also evaluates `final_acceptance`, S26 `release_authorization`, and S27 `deploy`. Only the exact denied operation is stopped. |
| `close` | Re-evaluates all close-applicable blockers in addition to existing commit/push/check gates. |
| `validate` | Recomputes decision hashes against the bound registry version and rejects stale or manually edited task projections. |
| `report` | Never hides the report; it projects the same decision, dependency path, owner and minimum closure action used by enforcement. |

`scripts/pipeline/night_runner.py` inherits the gate through controller
`next`/`dispatch`; it must not implement its own blocker logic. Release manifest
creation remains artifact construction, while S26 is the authorization gate.
No deploy path is authorized by this plan.

### Lifecycle commands and evidence authority

Controller commands cover `open`, `narrow`, `close`, `supersede` and `reopen`
for blocker records, plus task occurrence attachment. Every command requires:

- expected registry hash/revision (compare-and-swap);
- controller-issued role binding, not a free-form actor string;
- a unique idempotency/event key;
- a structured evidence receipt path and content hash;
- exact affected and remaining scope;
- the prior lifecycle event hash.

Closure evidence has its own schema. It names artifact kind, producing stage,
role binding, agent identity, source receipt hash, scope, observed checks,
created/verified timestamps and optional expiry. The controller verifies the
declared minimum closure contract, current blocker revision, same scope,
required role/oracle and role incompatibility. The agent that produced the
blocked artifact cannot close or approve its own blocker where the contract
requires an independent role.

Legacy `blocker_resolutions` containing only `path + by` are imported as
`legacy_unverified` and never count as closure until revalidated. Deleting or
editing a Git projection cannot resume a task.

### Atomicity, replay and invalidation

Lifecycle mutation runs under the controller store lock with canonical lock
ordering: registry, blocker ID, then affected task IDs. It writes a hash-linked
intent event with the idempotency key, materializes the new registry snapshot,
updates affected task decisions, writes a commit event and finally regenerates
the Git projections. Replay either completes an accepted intent once or leaves
the previous registry active; it never applies a narrow/close event twice.

When a registry revision changes, the controller re-evaluates only tasks whose
typed scope or dependency path can be affected:

- a newly applicable open blocker moves the task to its declared resume stage
  and invalidates dependent verdicts from that stage;
- narrowing permits only the evidenced safe scope and leaves the remaining
  edge active;
- closure resumes from the declared stage only after all other applicable
  blockers are re-evaluated;
- unrelated tasks retain decisions and continue;
- a changed definition or closure contract invalidates old resolution evidence
  because it is bound to the previous blocker revision.

Old stage receipts remain schema-valid. Receipts produced after registry v2 is
activated include `blocker_registry_hash` and `blocker_decision_hash` in
`input_hashes`; validation requires them for those receipts only. This avoids
silently rewriting the existing receipt chain while preventing new stages from
using stale blocker truth.

## BLG-F01 bootstrap boundary

`BLK-PROCESS-001` describes the exact gap this card repairs. Its current
`resume_stage = S15` is too broad: binding it mechanically would prevent the
case and implementation stages needed to produce its own closure evidence.

The v2 migration must preserve it as `narrowed` and express the remaining
prohibition explicitly: it blocks BLG-F01 final acceptance, release
authorization and closure until the exact candidate has runtime binding,
negative bypass metatests and independent evidence. It does not block S15-S23
from creating that evidence. S25 may narrow or close only the proven scope; it
must not automatically close other domain blockers. This is derived from the
S11 rule that a release-only blocker must not prevent permitted development.

Other v1 records with empty task lists are not treated as accidental globals.
Migration gives each an explicit global/capability scope and operation only
when that scope is strictly derivable from its approved rationale and evidence.
Otherwise migration stops and returns the record to its owning Product/oracle
contract; ambiguity cannot create either a silent bypass or a global stop.

## Resource graph and future S18 write locks

The Atomic Dev workspace must take one exclusive lock over the entire
control-plane write set. Discovery of a required write outside it returns to
S13 before scope expands.

| Resource | Planned responsibility |
| --- | --- |
| `pipeline/blocker-registry.schema.json` | Additive registry v2 definition, lifecycle, scope, dependency and history schema. |
| `pipeline/blocker-evidence.schema.json` | Typed closure/narrowing evidence and role/scope provenance. |
| `pipeline/blocker_registry.py` | Pure load, validate, hash, graph and decision engine. |
| `pipeline/controller.py` | Lifecycle commands, entrypoint gates, atomic state/projection update and decision receipts. |
| `pipeline/task-state.schema.json` | Typed registry binding, decisions, occurrences and resolution projections, backward compatible with existing snapshots. |
| `pipeline/receipt.schema.json` | Optional versioned blocker decision inputs for old receipts; required by controller for post-v2 receipts. |
| `pipeline/replay.py` | Hash-chain and idempotent blocker lifecycle recovery. |
| `docs/product/blocks.json` | Additive v1-to-v2 migration and canonical Git projection. |
| `docs/process/BLOCKERS-REGISTRY-RU.md` | Human explanation generated from or hash-bound to the same IDs; no independent lifecycle truth. |
| `scripts/ci/check_blockers_registry.py` | Full schema, references, cycle, history, projection and evidence-contract validation. |
| `scripts/ci/check_blocker_enforcement_metatests.py` | Deterministic entrypoint, lifecycle, parity, bypass and narrow-scope metatests. |
| `scripts/ci/check_pipeline_metatests.py` | Require the dedicated blocker suite and preserve Pipeline v2 trait/control-plane checks. |
| `scripts/ci/check_pipeline_replay_metatests.py` | Crash boundaries and one-time lifecycle replay proof. |
| `scripts/pipeline/dispatch.py` | Refuse handoff when the controller's dispatch decision denies the operation; render the same explanation. |
| `.github/workflows/ci.yml` | Run the dedicated blocker enforcement suite on the exact candidate. |

`pipeline/pipeline.yml` is a read dependency and already names
`docs/product/blocks.json`. It is intentionally not in the planned write set:
changing it would change `pipeline_hash` and invalidate every in-flight receipt
without adding decision semantics. If S14 proves that a pipeline contract
change is unavoidable, the task returns to S13 with an explicit migration and
invalidation plan before Dev touches it.

Read dependencies, not implementation scope:

- `docs/product/backlog-queue.json` and `tasks/*/state.json` for referential
  checks and affected-task fixtures;
- `scripts/pipeline/night_runner.py`, `scripts/pipeline/run.py`,
  `scripts/deploy/release_manifest.py` and deploy scripts to prove inherited
  boundaries without duplicating evaluator code;
- controller receipts and task journals used by deterministic local fixtures.

No frontend screen, backend route/service/model, database table/migration,
Redis/Celery queue, external contract, print template or mobile consumer is in
the graph. Their architecture result is explicit N/A for this card.

Canonical resource locks for S17/S18 are:

```text
control-plane:pipeline-v2
registry:docs/product/blocks.json
process:blocker-lifecycle
file:pipeline/blocker-registry.schema.json
file:pipeline/blocker-evidence.schema.json
file:pipeline/blocker_registry.py
file:pipeline/controller.py
file:pipeline/task-state.schema.json
file:pipeline/receipt.schema.json
file:pipeline/replay.py
file:docs/product/blocks.json
file:docs/process/BLOCKERS-REGISTRY-RU.md
file:scripts/ci/check_blockers_registry.py
file:scripts/ci/check_blocker_enforcement_metatests.py
file:scripts/ci/check_pipeline_metatests.py
file:scripts/ci/check_pipeline_replay_metatests.py
file:scripts/pipeline/dispatch.py
file:.github/workflows/ci.yml
```

Another task needing any of these resources serializes behind BLG-F01. Reads of
backlog and task snapshots are shared. BLG-F01 never writes another task's
artifact or state directly; only controller-owned, scope-matched projection
updates are permitted during metatest fixtures and are cleaned deterministically.

## Ordered implementation waves inside the atomic card

These waves are implementation order, not separately acceptable cards. No wave
may pass S20/S25 alone.

1. **Schema and pure evaluator.** Add v2 schemas, deterministic migration,
   matching and graph validation with pure fixtures. No entrypoint switches to
   v2 until the migrated registry validates.
2. **Controller authority and recovery.** Add lifecycle commands, CAS,
   journal/replay, evidence validation, scoped invalidation and backward-safe
   task/receipt projections.
3. **Entrypoint parity.** Bind classify, dispatch, hold/resume, advance, S25,
   S26, close, validate and report to the evaluator. `dispatch.py` consumes the
   controller decision; runners do not duplicate it.
4. **Registry migration and control-plane proof.** Migrate the current entries,
   bind BLK-PROCESS-001 at the exact non-circular boundaries, run direct and
   destructive metatests, and generate the human view from the same projection.
5. **Immutable integration and acceptance.** S23 records exact SHA/tree and
   artifacts. S25 independently inspects packet/state/report parity and
   unrelated-card continuation. S26 may reach only the controller-supported
   release result; no production deployment is implied.

## Required S15 and S22 proof

S15 must bind runnable local cases for at least:

- valid open blocker denial at each supported operation with stable ID,
  rationale, owner, exact scope, minimum closure and resume fields;
- an unrelated task and an earlier permitted operation continuing while a
  release-only or stage-specific blocker is open;
- oracle-only, release-only and stage-specific boundaries producing different
  decisions from the same registry;
- narrowed scope allowing only the evidence-proven part while preserving the
  remaining dependency edge;
- same-revision, same-scope, fresh closure evidence from the required
  role/oracle resuming at the declared stage without skipping invalidated gates;
- missing, stale, wrong-kind, wrong-scope, wrong-role, self-authored or manually
  edited evidence failing closed;
- manual edits to `blocks.json`, task snapshot or decision hash failing
  validation and never resuming controller state;
- duplicate IDs, unknown task/stage/check references, dangling edges, cycles,
  contradictory lifecycle state and broken history hashes being rejected
  before activation;
- closed, superseded and reopened history remaining hash-linked and traceable;
- identical decisions across controller classify/dispatch/advance/resume/S25/
  S26/close and packet/state/report projections;
- registry revision changes invalidating only affected downstream receipts;
- controller crash before/after intent, materialization and commit replaying
  once with the same registry and decision hashes;
- previous-controller rollback reading the additive v2 registry without
  treating empty scope as a new global block;
- BLK-PROCESS-001 allowing its remediation stages but refusing premature S25,
  S26 and close;
- no live marketplace host, secret, production state or warehouse operation
  being touched by the suite.

S22 runs the dedicated enforcement suite, registry validator, controller
metatests and replay metatests against the exact candidate. S23 repeats the
applicable control-plane suite after integration and records the candidate SHA
and tree. A green schema/parity check without the negative runtime cases is a
test defect and cannot pass the card.

## S25 internal acceptance surface

This is a pure internal pipeline change. S25 does not use a warehouse browser.
The independent Product Browser role inspects machine evidence on the exact S23
candidate for two synthetic tasks and at least one lifecycle mutation:

1. the blocked task's controller state, packet and report expose the same
   decision hash, blocker ID, reason, owner, minimum evidence and resume stage;
2. the prohibited entrypoint refuses the operation;
3. an independent task advances at the same time;
4. a valid narrow/close event changes only the declared scope;
5. reload/replay reproduces the same active registry and decision;
6. BLK-PROCESS-001 cannot be marked fully closed without the exact candidate's
   independent runtime and metatest evidence.

The typed acceptance result is the declared `pipeline_meta_tests` surface,
normalized by the controller to `FINAL_ACCEPTANCE_APPROVED`. It is independent
of this S13 author and of the future Dev.

## Stop and rollback criteria

Stop and return to the owning stage on any accidental global scope, unknown or
cyclic edge, two different decisions for one context, stale projection being
accepted, closure without exact role/scope evidence, self-unblocking, skipped
gate after resume, unrelated-card blocking, non-idempotent replay, old receipt
chain invalidation, or a need to change warehouse behavior.

Application rollback restores the previous controller code while retaining the
additive v1-compatible registry fields and append-only lifecycle evidence. It
does not delete blocker history, rewrite task receipts or call `resume` to make
the old controller appear green. If the previous controller cannot safely read
the migrated projection, S23 must reject the candidate before S25.

## Boundaries and remaining review

- S13 authorizes no implementation, commit, push, merge, release or deploy.
- Existing domain blocker closures are out of scope. BLG-F01 supplies the
  reusable enforcement mechanism; owning cards and roles supply their own
  evidence.
- The known independent-signing and distributed-store limitations remain
  represented by their existing blockers. This card enforces role and hash
  boundaries in the managed controller; it does not falsely claim a new remote
  cryptographic trust boundary.
- No owner input is required to falsify this plan. S14 must independently attack
  the single-registry authority, bootstrap migration, operation matching,
  stale-snapshot resistance, self-approval rejection, invalidation and replay.

There is no S13 blocker. The plan is ready for independent S14 falsification.
