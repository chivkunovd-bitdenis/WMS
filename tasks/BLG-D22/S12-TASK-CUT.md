# S12 TASK_CUT - BLG-D22

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

**Card ID:** `BLG-D22-C1`

**Title:** Turn the canonical full backend pytest command into a bounded,
fail-closed and diagnosable release gate.

This is one atomic test-infrastructure card. It must not be split into a
progress-only change, an outer suite timeout, a network mock, or a later
repeat-run check. None of those fragments alone makes a release decision safe:
the canonical command is useful only when it either completes the intended
suite or stops non-zero with the exact active test, phase and reason that
prevented completion.

### Observable result

For a pinned Git SHA and a fresh isolated test environment, the repository has
one declared canonical command for the full backend pytest gate. Its persisted,
sanitized evidence always yields exactly one result class:

- `FULL_GATE_PASSED` only after the intended suite is collected and completed
  within its declared budget with a zero exit status;
- `TEST_FAILED` for an ordinary completed assertion/exception path;
- `TEST_TIMED_OUT` for a named test or fixture phase that exceeds its declared
  boundary timeout;
- `EXTERNAL_CALL_BLOCKED` when a test tries to reach a non-allowed external
  destination and the deny-by-default guard stops it before a live effect;
- `TEST_ENVIRONMENT_FAILED` for collection, fixture, database, queue, worker,
  subprocess or reset infrastructure failure;
- `FLAKY_RESULT` when equivalent fresh runs disagree; or
- `RUN_INTERRUPTED` when termination bypasses the declared result paths.

The evidence contains ordered pytest node IDs and phases. For every non-success
result it preserves the last active node, phase, elapsed time, configured
timeout where applicable, and a sanitized last known waiting boundary. A
targeted green test, empty report, missing exit status, outer-orchestrator
timeout without inner diagnostics, or an unknown full run is never a green
full gate.

### Vertical boundary

`BLG-D22-C1` includes, as one delivery unit:

1. Declaration and invocation of the sole canonical full backend gate through
   the supported repository entrypoint, with explicit collection/completion
   accounting and a finite suite watchdog.
2. Progress and phase instrumentation that attributes setup, call and teardown
   work to a pytest node ID and persists non-interactive CI diagnostics before
   controlled termination.
3. Owning-boundary timeouts for every potentially waiting HTTP, database,
   queue, worker, subprocess and fixture/setup/teardown operation. The suite
   watchdog contains an escaped boundary but is not the diagnostic mechanism.
4. Deny-by-default test networking, named local fakes/emulators/deterministic
   fixtures, and a fail-closed attribution path for attempted external calls.
5. A result classifier and sanitized machine-readable evidence that preserves
   the difference between test failure, hang/timeout, prohibited external call,
   test-environment failure, interruption and nondeterminism.
6. Fresh-state reset identity and repeat-run comparison so that the same pinned
   baseline can be classified as repeatable or `FLAKY_RESULT` rather than
   inferred green from one partial run.

It includes no WMS application business logic, operator screen, API contract,
warehouse data, marketplace behavior, production/sandbox access, credential
access, deploy, release decision or live browser operation. It does not obtain
a pass by deleting tests, broad skips, unconditional quarantine, weakened
assertions, suppressed output or a larger global timeout without a
boundary-specific reason.

### Evidence surface

For every canonical run, the card's evidence format must record the exact Git
SHA, command, isolated-environment/reset identity, start/finish timestamps,
wall-clock duration, exit status, collected/completed/failed/skipped counts,
all active-test progress events, timeout budgets, and final result class.
Timeout, interruption and external-call records additionally name the last
active node ID and phase plus their sanitized waiting/dependency boundary.

The network evidence must show that live destinations are denied by default and
that only declared local test dependencies were used. Repeated equivalent runs
must retain log hashes and their classification. Evidence and logs must be
sanitized: no tokens, cookies, credentials, production URLs, personal data,
order identifiers or marking codes enter Git evidence.

## S15 acceptance and blocker boundary

S15 must turn this card into direct and breaker cases using deterministic local
fixtures and a documented fresh-state reset. At minimum it must cover:

- a complete canonical run with collection/completion accounting;
- an isolated hang in a named test or fixture phase, a controlled local timeout,
  non-zero exit and the persisted node/phase/waiting-boundary evidence;
- an ordinary assertion failure that remains `TEST_FAILED`, not timeout or
  environment failure;
- collection/configuration and fixture/reset failures classified as
  `TEST_ENVIRONMENT_FAILED`;
- an attempted live-style external destination that is stopped before a side
  effect and classified as `EXTERNAL_CALL_BLOCKED` with the responsible test;
- interrupted-process evidence retaining the last active node and phase;
- equivalent fresh repeated runs that agree, and a deliberate disagreement
  detected as `FLAKY_RESULT`; and
- negative checks that a skip, quarantine, missing summary, stale/cached log,
  targeted subset, widened outer timeout or unavailable node identity cannot
  produce `FULL_GATE_PASSED`.

`BLK-TEST-001` remains **open**, owned by `pipeline-reviewer`, with
`resume_stage: S15`. S15 may prepare and refine the cases above, but it must
not return `CASES_READY` or `CASE_AUDIT_PASSED`, and no later stage may use a
claimed full-gate success, until the controller explicitly resolves the
blocker. Its unchanged minimum closure evidence is: an isolated hanging test
ID, a controlled timeout and a successful full-run log. The fuller registry
evidence also requires the exact SHA, canonical command, log, closed external
dependency and an explicit reason for any skip. A fabricated fixture log,
targeted green run, Product approval or an outer timeout without an isolated
node ID is not closure evidence.

## Downstream ownership and dependencies

- **S13 `ARCHITECT_PLAN`:** maps the actual supported full-gate entrypoint,
  pytest/plugin/process boundaries, local dependency topology, evidence storage
  and redaction boundary. It chooses the exact timeout ownership and budgets,
  network-guard integration, process cleanup ownership, result schema,
  repeatability protocol and permitted files. It must preserve the single-card
  outcome and must not select a shortcut that leaves any waiting boundary or
  external dependency unaccounted for.
- **S14 `ARCHITECT_FALSIFICATION`:** attacks the S13 plan for an uninstrumented
  setup/teardown phase, timeout that kills a shared resource, log loss on
  termination, a network bypass, a misclassified failure, stale test state,
  flaky repeat evidence and an apparent pass that did not run the intended
  suite.
- **S15 `CASE_FACTORY`:** owns the runnable direct/breaker cases above, but is
  stopped at `BLK-TEST-001` until the controller's explicit
  `resolve-blocker` result. It may not self-resolve the blocker or pass S15.
- **S18 `DEVELOPMENT`:** may start only after valid blocker resolution and the
  normal S16 Product-before-Dev and S17 workspace gates. Its scope is the
  approved test-infrastructure card only: it must not change WMS application
  behavior, weaken tests, invoke live services or make a development claim
  while the S15 barrier is still open.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
BLG-D22 is a high-risk `pipeline_change`. The architect receives this task cut,
the S11 Product contract, the open `BLK-TEST-001` record and its unchanged S15
resume condition. Any change to the one-card boundary or to the fail-closed
full-gate contract requires S12 rework before later Product-before-Dev
approval.
