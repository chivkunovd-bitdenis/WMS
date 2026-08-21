# S11 PRODUCT_CONTRACT_APPROVAL - BLG-F01

## Product decision

Product approves a single blocker library and dependency map for Pipeline v2.
Its purpose is to make every rule that stops an operator-facing change, a task,
a stage or a release visible before the affected action starts, and to prevent
the pipeline from bypassing that rule by choosing another entrypoint.

The registry is not a list of general risks or wishes. An entry is an active
blocker only when it names a concrete prohibited continuation, the business or
warehouse harm that the prohibition prevents, the affected scope, the owner of
the decision, and the exact evidence that permits work to resume. A warning
without a prohibited action remains a risk or observation and must not stop a
task under a `BLK-*` identity.

`docs/product/blocks.json` is the machine-readable product registry. Human
documentation may explain the same entries, but it must not create a second
set of blocker identities or different lifecycle truth. Pipeline stages and
automated checks consume the same stable blocker IDs and must fail closed when
the applicable registry contract is missing, contradictory or unverifiable.

## Approved operational outcome

Before dispatch, transition, resume, final acceptance or release, Pipeline v2
can determine which open blockers apply to the exact task, stage and operation.
When a blocker applies, the attempted continuation is refused and the packet
names, in operator-readable language:

- the stable blocker ID and prohibited operation;
- why continuation is unsafe and which business or warehouse result is at
  risk;
- the affected task, scenario, surface and stage;
- the role responsible for resolving or deciding the blocker;
- the minimum closure evidence and exact resume condition;
- the stage from which the controller may continue after valid resolution.

The result must be scope-precise. An open blocker stops only the task,
dependency edge, capability or transition explicitly covered by the entry.
Independent cards continue. A blocker on release does not prevent permitted
contract or development work; a blocker on an oracle does prevent downstream
work that would encode an unapproved behavior. A narrowed blocker stops only
the remaining named capability. A closed blocker does not stop work but stays
in history with its closure evidence.

No task becomes unblocked merely because a document, test or implementation
exists. The registry must recognize closure only when the entry's declared
minimum evidence is present, current, attributable to the required role or
oracle, and applicable to the same scope. Resolution returns control to the
declared resume stage; it does not skip invalidated Product, architecture,
case, review, test, acceptance or release stages.

## Blocker record contract

Every blocker must have one stable `BLK-*` identity and enough structured data
to answer all of the following without reading source code or reconstructing
context from chat:

- current lifecycle state: `open`, `narrowed` or `closed`;
- blocker type and severity or enforcement class;
- prohibited operation and the trigger condition that makes the blocker
  applicable;
- business or warehouse rationale, including the harm if the rule is bypassed;
- affected task IDs, scenario or process, surface and pipeline stage;
- enforcing layer or layers, so UI, API, worker, data and controller rules
  cannot silently disagree;
- owner role and, when applicable, the independent oracle or approver;
- what the operator or pipeline worker sees when continuation is denied;
- exact resume condition, resume stage and minimum closure artifact;
- evidence sources, last verification date and policy/schema version;
- dependency edges to tasks, stages, checks and other blockers;
- supersession and closure history, including the reason for every lifecycle
  change.

The implementation may extend the existing schema to represent these approved
meanings, but S11 does not prescribe storage layout, controller APIs or code
boundaries. S13 must choose those mechanisms and S14 must falsify them.

## Lifecycle and dependency rules

1. Creating or importing a blocker with missing scope, owner, rationale,
   resume condition or closure evidence is rejected. It must not become an
   unexplainable global stop.
2. Opening a blocker activates only its declared dependency edges. The
   controller records the exact `BLK-*` ID in the affected task state or
   receipt and routes the task to the lifecycle state allowed by Pipeline v2.
3. Narrowing a blocker requires evidence of the part already made safe and an
   explicit remaining scope. It cannot leave the old broad stop active while
   also claiming that the blocker is narrowed.
4. Closing a blocker requires the declared closure artifact and role/oracle
   evidence. A text edit, a green check on another layer, elapsed time or an
   agent's assertion cannot close it.
5. A closed or superseded entry is retained for audit. Reusing its ID for a
   different prohibition, deleting it to make a task pass, or silently
   rewriting its prior scope is forbidden.
6. Reopening uses the same identity when the same prohibition recurs and links
   the new evidence to the earlier closure. A materially different rule gets a
   new identity and an explicit relation to the old one.
7. Dependency edges are directional and explain why one task, stage or check
   depends on the blocker. Transitive blocking must be traceable; unrelated
   work must not be captured merely because it shares a product area.
8. Cycles, unknown task IDs, unknown stages, dangling blocker references and
   contradictory active states are invalid registry data and must stop only
   the affected control-plane transition pending repair.
9. Manual edits to a Git snapshot or human Markdown cannot on their own resume
   controller state. Resume and advance remain controller-owned actions with
   auditable evidence.

## Consistency across layers

The same business prohibition must have the same meaning wherever it is
enforced. A screen must not promise that an action is available while the API
or controller rejects it for an undisclosed rule; an agent instruction must
not invent a stricter blocker absent from the registry or a higher-priority
oracle. When several layers enforce one rule, they refer to the same blocker
identity and preserve the same resolution condition.

BLG-F01 does not itself redesign warehouse screens or change warehouse
operations. Existing operator-facing blockers may be inventoried and linked,
but any new visible message, action or workflow requires its own correctly
classified card, behavior contract and, when visible, UX/Product Browser
stages. This pipeline change must not add operator clicks, relax stock,
marking, tenant, authorization or marketplace invariants, or reinterpret an
underlying business oracle.

## Relationship to current registry and dependent backlog

The existing `docs/product/blocks.json` and
`docs/process/BLOCKERS-REGISTRY-RU.md` are the starting inventory, not proof
that runtime binding is complete. In particular, `BLK-PROCESS-001` correctly
records that schema/parity checks alone do not prevent an affected task from
advancing or a blocker from being closed without exact evidence.

Completion of BLG-F01 must provide the reusable registry and enforcement
contract needed by dependent cards such as BLG-D05, BLG-F1A and BLG-G01. It
must not automatically close their domain-specific blockers or mark those
cards ready for Dev. Each dependent card still resumes only through its own
declared controller stage and evidence.

## Required downstream proof

S12 must cut vertical cards whose observable outcomes preserve one registry
truth from authoring through controller enforcement and audit. It must not cut
the work into a documentation-only card that can pass while runtime ignores
the registry.

S13 must map every registry consumer and mutation boundary, including task
classification, dispatch, hold/resume, stage advance, final acceptance,
release authorization, CI and reports. It must define authority, versioning,
dependency evaluation, atomic lifecycle changes and recovery without granting
workers permission to accept or unblock their own work. S14 must independently
challenge bypasses, stale snapshots, inconsistent entrypoints and over-broad
blocking.

S15 must bind runnable direct and destructive cases for at least:

- a valid open blocker refusing the exact affected transition with complete
  explanation and resume data;
- an unrelated task continuing while another card is blocked;
- release-only, oracle-only and stage-specific blockers stopping at the
  correct boundaries;
- a narrowed blocker allowing the proven-safe scope while retaining the
  remaining stop;
- valid closure evidence resuming from the declared stage without skipping
  invalidated gates;
- missing or wrong-role closure evidence, manual registry edits and stale task
  snapshots failing closed;
- missing mandatory fields, duplicate IDs, unknown tasks or stages, dangling
  edges, cycles and contradictory states being rejected;
- closed, superseded and reopened history remaining traceable;
- every supported entrypoint producing the same decision for the same blocker
  and task state;
- worker self-unblocking and self-approval being rejected;
- controller restart preserving active blocker and dependency truth.

S20 must be an independent control-plane review. S22 and S23 must run the
blocker registry checks and the applicable Pipeline v2 metatests against the
exact candidate, including negative bypass cases. S25 acceptance for this
declared internal surface must inspect machine evidence that the same blocker
decision is visible in controller packet/state/report outputs and that an
independent card is not stopped. S26 may authorize only the immutable reviewed
candidate and does not imply production deployment.

## Acceptance criteria

The product result is acceptable only when:

- every enforced blocker is discoverable by stable ID before the affected
  action and has the approved record semantics;
- the dependency map gives one deterministic answer about what is blocked,
  why, by whom, until what evidence and from which stage work resumes;
- all supported pipeline entrypoints enforce that answer consistently;
- closure, narrowing, supersession and reopening preserve audit history and
  cannot be achieved by deleting or rewriting evidence;
- unrelated cards demonstrably continue;
- no operator-facing warehouse process or safety invariant changes as a side
  effect of this control-plane task;
- downstream Product, architecture, cases, independent review, tests and final
  acceptance remain separate controller receipts.

## Out of scope

S11 does not choose the registry storage or controller implementation, write
BA cases or architecture, adjudicate and close existing domain blockers,
change warehouse UI/API/business behavior, start dependent cards, implement
code, review implementation, accept the final result, commit, push, merge,
deploy, access secrets, mutate production data or call live WB/Ozon systems.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: Pipeline v2 must use one stable, auditable blocker
registry and dependency map that refuses only the exact unsafe continuation,
states the business reason and route to resolution, preserves history, keeps
independent work moving and does not change the warehouse user process.
