# S14 ARCHITECT_FALSIFICATION - BLG-F01

## Binding

- Task: `BLG-F01`
- Stage: `S14 ARCHITECT_FALSIFICATION`
- Role: `pipeline-reviewer`
- Agent: `codex-blg-f01-s14-pipeline-reviewer`
- Reviewed baseline: `69c271678782d7dcfa39df97cd905cbee1678727`
- Reviewed plan: `tasks/BLG-F01/S13-ARCHITECT-PLAN.md`

## Verdict

`BLOCKED` with arbiter decision `REPLAN`.

The S13 plan establishes the right review surface: one typed evaluator,
operation-specific decisions, scoped dependency paths, hash-linked lifecycle
events, role-bound evidence, replay and negative entrypoint tests. It does not
yet prove an executable single blocker authority. Three counterexamples leave
either a deadlock, two current lifecycle truths or an unrepresentable
controller hold. Because this is a critical `pipeline_change`, S14 cannot issue
`ARCH_REVIEW_PASSED`, and S15/development must not start.

## Blocking findings

### F1 - BLK-PROCESS-001 creates a final-acceptance bootstrap deadlock

Severity: critical. Finding type: `PLAN | ROLE_AUTHORITY`.

S13 migrates `BLK-PROCESS-001` as a narrowed blocker that denies
`final_acceptance`, `release_authorization` and `close`. It also states that
S25 may narrow or close the proven scope and that S25 must verify the blocker
cannot be fully closed without the exact candidate's independent runtime and
metatest evidence.

This route has no executable transition. After S23, `advance S25` must evaluate
`final_acceptance` before writing the S25 receipt, so the blocker denies entry.
The only active stage role is then `pipeline-browser-product`, while the current
blocker owner is `pipeline-architect` and S13 requires lifecycle mutations to
use a controller-issued role binding. Letting S25 close the blocker makes the
acceptance role mutate the prerequisite it is meant to inspect; refusing that
self-authorization leaves the card permanently before S25. No independent
controller command, role handoff or receipt between S23 and S25 is allocated
to resolve the cycle.

Minimum closure:

- define the exact pre-S25 lifecycle transition, owning controller-bound role
  and evidence set that can narrow/close only the BLG-F01 occurrence;
- separate evidence production from lifecycle authorization, so S20/S22/S23
  can supply proof without their identities approving their own result;
- make `advance S25` consume the already-authorized lifecycle event and still
  independently test that premature, wrong-role and self-authored closure are
  rejected; and
- add a negative route proving BLG-F01 reaches S25 without bypassing the
  blocker and cannot reach S26/close when the pre-S25 event is absent.

### F2 - Runtime lifecycle and Git lifecycle cannot be one atomic authority

Severity: critical. Finding type: `PLAN | DURABILITY`.

S13 stores current materialized lifecycle in both controller-owned
`.pipeline-state/blockers/state.json` and tracked `docs/product/blocks.json`.
Every accepted runtime event is said to atomically update controller state and
then regenerate the Git projection, while CI in a fresh checkout is said to
evaluate that Git projection. A filesystem regeneration is not a Git commit or
push and cannot be atomic with the controller journal. Therefore a successful
close/narrow event can leave runtime on registry hash B while the reviewed
checkout and CI remain on hash A. Treating the mismatch as invalid detects the
split but supplies no publication or recovery transition; treating A as the
last valid version can evaluate a different lifecycle from runtime.

The planned registry lock and replay journal cover controller files only. They
cannot make a repository commit, branch publication and CI checkout part of
the same compare-and-swap transaction. The plan consequently has two
independently current lifecycle representations despite naming one logical
registry.

Minimum closure:

- choose one durable authority for mutable lifecycle and make every evaluator
  consume a hash-addressed snapshot from that authority;
- redefine the Git file either as an immutable reviewed definition/policy seed
  or specify an explicit controller-owned publication artifact and handoff,
  without claiming an uncommitted worktree rewrite is current Git truth;
- define crash/restart behavior before and after runtime commit, projection
  generation, repository publication and CI verification; and
- prove a fresh checkout can verify the exact decision hash used by runtime
  without accepting stale lifecycle or requiring a worker to hand-edit state.

### F3 - Dynamic Pipeline holds have no registry occurrence model

Severity: critical. Finding type: `PLAN | CONTRACT`.

S13 changes `hold` so it requires a stable registry blocker ID and cannot
create free-form blocker truth. The active controller and Pipeline contract
also require runtime-created typed holds such as `ENV`, `FIXTURE`,
`ORACLE_CONFLICT`, `ACCESS` and `BUDGET_HARD_STOP`. Those events are discovered
during execution and cannot all be pre-authored as task-specific registry
records. S13 mentions a scoped occurrence but does not define its identity,
schema, creation authority, relationship to a reusable blocker definition or
how `resume` validates it.

Implementing the plan literally either rejects mandatory safety holds because
no `BLK-*` exists, creates task-local blocker truth outside the registry, or
allows a worker to author a new blocking policy during its own stage. All
three outcomes contradict the Product contract and the existing budget hard
stop.

Minimum closure:

- define separate typed contracts for an immutable blocker definition and a
  controller-created scoped occurrence, each with stable identity and hashes;
- state which existing failure/hold paths may instantiate an occurrence and
  which changes require Product/oracle approval of a new definition;
- bind automatic budget, environment, fixture, access and oracle holds to that
  model without permitting worker self-unblocking or accidental global scope;
  and
- add direct cases for occurrence creation, duplicate/idempotent creation,
  restart, independent-card continuation, exact-scope resume and stale or
  wrong-role closure rejection.

## Findings that survived falsification

- A single pure decision function with typed operation and scope inputs is the
  correct enforcement boundary.
- Conjunctive matching across scope dimensions, explicit global scope and full
  directional dependency paths prevent accidental broad blocking when fully
  specified.
- Hash-linked lifecycle evidence, compare-and-swap, idempotency keys and
  role-incompatibility checks are necessary and should remain in the replan.
- `next`, packet, dispatch, resume, advance, S25, S26, close, validate and
  report must continue to share the same decision implementation.
- `BLK-PROCESS-001` must allow S15-S23 remediation while denying premature
  acceptance/release/closure; only its executable pre-S25 authorization path
  needs repair.

## Required replan artifact

Return to `S13 ARCHITECT_PLAN`, owned by `solution-architect`. The revised plan
must close F1-F3 with:

1. a non-circular, independently authorized BLG-F01 bootstrap lifecycle;
2. one durable mutable authority and an explicit Git/CI verification model;
3. a typed definition-versus-occurrence contract for dynamic holds; and
4. updated S15/S22/S25 negative cases proving those exact boundaries.

After controller resume and a new S13 receipt, S14 must be dispatched to an
independent reviewer again. S15, Product Before Dev and all implementation
stages remain blocked.

## Scope and safety

This stage reviewed architecture, current registry/controller entrypoints and
task artifacts only. It performed no Product, BA, architecture authoring, Dev,
acceptance, commit, push, merge, deployment, production mutation, secret
access or live WB/Ozon operation. No unrelated diff was modified.
