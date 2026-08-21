# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D22

## Product decision and business outcome

Product approves a task-specific contract for making the full backend `pytest`
gate a reliable release-safety signal. The user of this result is the engineer,
reviewer or release owner deciding whether a WMS change may proceed. They must
receive one unambiguous answer from the canonical full-suite run: it completed
successfully, or it stopped with the exact test, phase and failure class that
prevented completion.

The warehouse value is indirect but critical. A green targeted test must no
longer be mistaken for proof that unrelated stock, order, packing, marking,
tenant or worker behavior remains safe. No release decision may rely on the
full backend gate while that gate can wait forever or hide the external call or
test that stopped it.

This task changes test and pipeline behavior only. It must not change an
operator screen, warehouse action, API contract, stored business data,
background business process or marketplace behavior.

## Required observable behavior

1. There is one declared canonical command for the full backend test gate. A
   successful result means that this command collected and completed the full
   intended suite and returned a successful exit status. A targeted subset,
   collection-only run or previously cached result cannot substitute for it.
2. During the run, the evidence identifies the currently executing pytest
   node ID and phase closely enough that an interrupted or timed-out run names
   the last active test instead of ending with an unexplained silence.
3. Every operation capable of waiting outside the test body, including HTTP,
   database, queue, worker, subprocess and fixture setup/teardown boundaries,
   has a declared finite timeout at the owning boundary. A suite-level watchdog
   is the final containment boundary, not the only diagnosis mechanism.
4. When a timeout occurs, the run terminates non-zero and records the test node
   ID, phase, configured timeout, elapsed time and sanitized last known waiting
   boundary. The timeout must not be converted into a skip, warning or green
   result.
5. External dependencies are replaced by local fakes, emulators or deterministic
   fixtures for the full gate. An attempted live external call fails closed,
   names the blocked dependency category and test, and cannot wait for a real
   WB, Ozon or other production endpoint.
6. Ordinary assertion failures, collection/configuration failures, fixture or
   environment failures, timeouts and prohibited external calls remain separate
   result classes. The report must not flatten them into a generic "pytest
   failed" outcome.
7. Repeatability is part of the result. On the same pinned baseline and fresh
   isolated test state, repeated full-gate runs must complete within the
   declared suite budget and produce the same pass/fail classification. A run
   that alternates between success, failure and timeout is `FLAKY`, not green.
8. Existing test coverage cannot be made green by deleting tests, broad skips,
   unconditional quarantine, weakening assertions, hiding output or raising
   timeouts without a boundary-specific reason. Any intentional skip or
   quarantine remains visible with an owner, reason and expiry under the
   existing pipeline rules.
9. Diagnostic output must remain useful in non-interactive CI: progress and the
   final classification are persisted even when the test process is terminated
   by a controlled timeout.

## Required result states

- `FULL_GATE_PASSED`: the canonical command collected and completed the intended
  suite within the declared budget, returned zero and produced a complete run
  summary. Only this state may be called a green full backend gate.
- `TEST_FAILED`: pytest completed the failing test path and reports its node ID,
  phase, assertion or exception and non-zero exit status.
- `TEST_TIMED_OUT`: a named test or fixture phase crossed a declared timeout and
  the evidence names the waiting boundary and elapsed time.
- `EXTERNAL_CALL_BLOCKED`: a test attempted a non-allowed external destination;
  the network guard stopped it before a live side effect and attributed the
  attempt to a test.
- `TEST_ENVIRONMENT_FAILED`: collection, fixture, database, queue, worker,
  subprocess or reset infrastructure failed before a valid test verdict; this
  is not a product regression and not a pass.
- `FLAKY_RESULT`: repeated runs on equivalent fresh state disagree. The gate
  remains non-green until the nondeterminism has an owner and remediation.
- `RUN_INTERRUPTED`: the process ended outside a declared result path. This is
  itself a gate failure and must retain the last active node ID and phase for
  diagnosis.

An empty summary, missing exit status, missing active test identity, timeout of
the outer orchestration process without inner diagnostics, or green targeted
subset while the canonical full run is unknown is never `FULL_GATE_PASSED`.

## Evidence and acceptance surfaces

The implementation and later acceptance packet must contain sanitized,
machine-readable evidence tied to the exact Git SHA, command and isolated
environment. At minimum it records:

- canonical full-gate command, start and finish time, wall-clock duration,
  exit status, collected/completed/failed/skipped counts and timeout budgets;
- ordered progress with pytest node IDs and phases, including the last active
  node and waiting boundary for every non-success termination;
- result classification from the state list above and the underlying pytest
  failure or timeout artifact, not only a prose summary;
- proof that test network access is deny-by-default and that external behavior
  used only named local fakes, emulators or fixtures;
- fixture/reset identity for database, Redis, worker/queue and subprocess state
  where applicable, so a second run is genuinely fresh;
- hashes of repeated full-run logs on the same pinned baseline, including a
  successful complete run only when one actually occurred;
- redaction status proving that tokens, cookies, credentials, production URLs,
  personal data, order identifiers and marking codes were not committed.

The declared S25 independent acceptance surface is `pipeline_meta_tests` plus
the canonical full backend gate through supported repository entrypoints. It
must exercise both the successful path and deliberate local failure paths for
an assertion failure, timeout and blocked external call. Code inspection,
calling an internal helper, a targeted pytest command or this Product contract
does not constitute final acceptance.

## Safety and authorization boundaries

All diagnosis, cases and implementation run in isolated local or CI test
resources. Test data must be synthetic or an already approved sanitized
fixture. Network behavior is fail-closed and may reach only explicitly allowed
local test dependencies. This task authorizes no live WB/Ozon request, no
production or sandbox account call, no production data read or mutation, no
secret access or change, no deploy, no release and no live browser operation.

Timeout cleanup may terminate only the owned test process and owned isolated
resources. It must not kill shared services or another task's database, Redis
namespace, queue, worker or subprocess. Logs and evidence follow the repository
allowlist and redaction rules.

## Non-goals

- Changing WMS application business logic to make an existing failing test
  pass.
- Changing operator UX, warehouse workflow or marketplace contracts.
- Making every backend test faster when it already completes deterministically.
- Treating a larger global timeout as the diagnosis.
- Removing, skipping, quarantining or weakening tests to obtain a green count.
- Proving production readiness, authorizing release or deploying any SHA.
- Closing `BLK-TEST-001` from Product judgment or from this S11 artifact.

## Downstream contract and BLK-TEST-001

`BLK-TEST-001` remains open, is owned by `pipeline-reviewer`, and has
`resume_stage: S15`. This S11 verdict approves the desired product outcome; it
does not provide the blocker's minimum closure artifact and must not be cited as
its resolution.

S12 must preserve BLG-D22 as one vertical release-safety result. It may identify
implementation slices, but it must not separate timeout instrumentation,
external-dependency isolation and repeatable full-run proof into independently
claimable successes. The task cut must carry the open blocker, its owner,
resume stage and minimum closure evidence unchanged.

S15 may prepare or refine direct and breaker cases only as the controller
allows, but it must not return `CASES_READY` or `CASE_AUDIT_PASSED` while
`BLK-TEST-001` is open. In particular, a fabricated fixture log, a targeted
green run, a timed-out full run without an isolated node ID, or Product approval
is not closure evidence. Only the controller's explicit `resolve-blocker`
result, based on the registry minimum of an isolated hanging test ID, a
controlled timeout and a successful full-run log, may permit progress past the
S15 barrier.

S18 must not start, receive a development claim or change application code
while the blocker prevents completion of S15 and the subsequent S16/S17 gates.
After a valid controller resolution and normal Product-before-Dev approval,
S18 remains limited to the approved test-infrastructure card. It must not
reinterpret this contract as permission to bypass cases, weaken tests, call
live services or alter WMS runtime behavior.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: BLG-D22 is approved only as a fail-closed,
repeatable full backend pytest gate that always completes with a clear result or
terminates with the exact test and waiting boundary. No operator behavior
changes, and `BLK-TEST-001` remains open at S15 until independently resolved
with its declared evidence.
