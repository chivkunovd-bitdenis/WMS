# S13 ARCHITECT_PLAN - BLG-D22

## Verdict

`ARCH_PLAN_READY`

BLG-D22 remains one atomic high-risk test-infrastructure card. The future
implementation has one outcome: the supported full backend test command either
completes the intended pytest suite twice on fresh equivalent state and emits
`FULL_GATE_PASSED`, or exits non-zero with a persisted, sanitized and
machine-readable reason tied to the exact active node, phase and waiting
boundary.

The plan does not authorize application changes, a targeted-test substitute, a
larger unexplained outer timeout, a live external call, blocker closure, Dev,
release or deploy. `BLK-TEST-001` remains open under `pipeline-reviewer`
ownership with `resume_stage: S15`.

## Bound inputs and observed baseline

- Product contract: `tasks/BLG-D22/S11-PRODUCT-CONTRACT.md`, SHA-256
  `18417dba3fec7f722ecf5cf3c48468d21fc18c1a520d98ae29b30871115ae7da`.
- Atomic task cut: `tasks/BLG-D22/S12-TASK-CUT.md`, SHA-256
  `cd09df0af45daf7753f7529da998194dbe17b7f643a7281d94031108321a0253`.
- Controller baseline: `69c271678782d7dcfa39df97cd905cbee1678727`.
- S13 observation checkout: `18e5f207a60bb33a830bee568c436d4006862b84`
  on `codex/wms-pipeline-unified-v2-20260820`.
- Declared S25 acceptance surface: `pipeline_meta_tests` plus the canonical
  full backend gate through its supported repository entrypoint.
- Static inventory at S13 contains 127 `backend/tests/test_*.py` modules and
  641 top-level `test_*` functions. These are orientation counts, not a
  collected-suite receipt; parametrized node IDs and skips must come from a
  real collection manifest.

The current repository has the following task-specific gaps:

1. `.github/workflows/ci.yml` invokes
   `test_egress_guard.py -- bash -lc 'cd backend && pytest'`. It has no
   canonical full-gate supervisor, per-node timeout, suite watchdog, progress
   journal, result schema, repeated fresh run or uploaded diagnostic bundle.
2. `CLAUDE.md` and `scripts/hooks/rules_card.py` still describe raw `pytest` as
   the backend check. Therefore CI, local users and agents do not share one
   command surface.
3. `backend/pyproject.toml` has pytest and pytest-asyncio, but no timeout or
   structured-report dependency and no strict full-gate options.
4. `backend/tests/conftest.py` uses the shared paths
   `backend/tests/wms_pytest.sqlite` and `backend/tests/wms_pytest_data`, and
   drops/recreates all tables around each `async_client` fixture. It does not
   bind the database, files, settings or cleanup receipt to a unique gate run.
5. The current egress wrapper sets `WMS_TEST_EGRESS=deny`, but permits inherited
   `WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES=1`, allows broad host patterns, and
   returns only the child exit code. `sitecustomize.py` raises a plain
   `PermissionError` without a durable event, node ID or phase, so application
   error handling can flatten a blocked network attempt into an ordinary test
   failure.
6. Current socket interception covers Python and a Node preload hook, but the
   canonical backend command is launched through a shell and does not prove
   that the guard loaded in every Python child. There is no fail-closed startup
   attestation or subprocess inventory.
7. WB HTTP clients generally have a 60-second request timeout, while pytest has
   no node timeout. The suite can therefore be silent, and DB locks, fixture
   teardown, in-process ASGI requests or unowned subprocesses have no common
   diagnostic boundary.
8. Background-job tests currently use in-process FastAPI `BackgroundTasks` and
   bounded polling loops such as 30 x 0.15 seconds or 40 x 0.12 seconds. A
   caller environment can still inject a Celery broker or other settings loaded
   from `.env`, and the polling boundary is duplicated rather than reported by
   one gate-aware helper.

These are read-only observations. No full pytest run was started at S13, so
this plan does not claim an isolated hanging node or a successful full-run log.

## Architectural invariants

1. **One command, fixed suite.** The canonical command is
   `python3 scripts/testing/full_backend_gate.py` from the repository root. It
   accepts diagnostic verbosity and an evidence destination, but rejects node
   selectors, `-k`, changed test roots, collection-only mode, arbitrary
   `PYTEST_ADDOPTS` and a single-attempt pass.
2. **Two fresh attempts.** A green command always runs two attempts against
   separate DB, file, cache and process state. The collected node-ID manifests
   and normalized outcome fingerprints must match. A disagreement is
   `FLAKY_RESULT`, even if one attempt passed.
3. **Inner diagnosis before outer containment.** The pytest plugin records the
   active node and `setup | call | teardown` phase before invoking it. Boundary
   helpers record HTTP, DB, worker/poll, emulator and subprocess waits. The
   suite watchdog is the final owner when an inner boundary fails to report.
4. **Every wait is finite.** A test item, fixture reset, HTTP operation, DB
   lock/statement, worker poll/drain and owned subprocess has an explicit
   timeout. An override requires a stable reason, owner and expiry in the
   versioned timeout policy; an environment variable cannot silently widen it.
5. **External access fails before effect.** The canonical gate strips live
   opt-ins and sensitive connection settings, permits only run-declared local
   dependencies, verifies the guard loaded, records a denial side channel and
   gives `EXTERNAL_CALL_BLOCKED` priority over a later assertion failure.
6. **No secret-bearing environment inheritance.** The child receives an
   allowlisted test environment, fixed test settings and a run-specific working
   directory without a `.env`. Proxy, cloud credential, production URL and
   marketplace live-opt-in variables are removed rather than logged.
7. **Owned cleanup only.** The supervisor starts pytest in a new process group,
   records its PID/run ID, and may signal only that group. It never uses
   `pkill`, `killall`, a shared Celery worker, a shared DB/schema or another
   task's files.
8. **Classification is deterministic.** Exactly one top-level result is
   produced from typed events using the precedence below. Missing terminal
   evidence is never inferred green from exit code zero.
9. **No coverage weakening.** A pass requires the fixed full-suite path, zero
   deselected nodes, matching collection manifests, completed accounting and
   only versioned approved skips/quarantines. Deleted tests, a new broad skip,
   stale output or a targeted subset cannot satisfy the gate.
10. **Evidence survives controlled death.** Progress is append-only JSONL and
    flushed after every boundary transition. The final summary is written
    atomically. CI uploads the run directory even when pytest is terminated.
11. **No application-code escape hatch.** The planned write set excludes
    `backend/app/**`, migrations, API contracts and business behavior. If a
    wait cannot be bounded from the test harness without changing runtime
    behavior, the card returns to S13/S12 instead of expanding scope silently.

## Resource graph

```text
supported entrypoints
  CLAUDE.md / rules_card.py / CI backend job
                |
                v
scripts/testing/full_backend_gate.py
  fixed argv + allowlisted env + run identity + process-group owner
                |
       +--------+---------+
       |                  |
       v                  v
test egress policy     evidence directory
sitecustomize.py       run.json / events.jsonl / summary.json
Python + Node hooks    stdout.log / stderr.log / stackdump.log
       |               collection.json / junit.xml / reset.json
       +--------+---------+
                v
python -m pytest -c backend/pyproject.toml backend/tests
  explicit pytest-asyncio + pytest-timeout + gate plugin
                |
       +--------+----------------+------------------+
       |                         |                  |
       v                         v                  v
backend/tests/conftest.py   gate boundary API   current test nodes
unique DB/data/reset       progress/phase       direct + emulator
       |                         |                  |
       v                         v                  v
SQLite or approved local   HTTP / DB / poll     in-process WMS ASGI
PostgreSQL lane            worker / subprocess  in-process WB emulator
       |                         |                  |
       +-------------------------+------------------+
                                 v
                     deterministic classifier
                                 |
                                 v
 FULL_GATE_PASSED | TEST_FAILED | TEST_TIMED_OUT
 EXTERNAL_CALL_BLOCKED | TEST_ENVIRONMENT_FAILED
 FLAKY_RESULT | RUN_INTERRUPTED
```

### Resource ownership

| Resource | Current behavior | Future owner and boundary |
| --- | --- | --- |
| Full-suite argv | Raw shell `pytest` in CI | Supervisor constructs fixed argv without a shell and records it verbatim. |
| Collection | Implicit `testpaths = ["tests"]` | Gate plugin persists ordered node IDs; both attempts require the same non-empty hash and zero deselection. |
| Pytest progress | Console output only | Plugin journals session, collection, node and phase start/finish events before/after each hook. |
| SQLite/data files | Shared paths under `backend/tests` | Per-attempt paths under the owned run root; teardown proves removal or records `TEST_ENVIRONMENT_FAILED`. |
| PostgreSQL lane | Optional `WMS_TEST_DATABASE_URL`, tests may skip | Only an explicitly declared local URL with a run-unique database/schema; connect, lock and statement budgets are enforced. |
| HTTP | In-process ASGI plus mocked/emulated WB clients | In-process transport gets a 15-second operation boundary; socket egress is denied except explicit loopback dependencies. |
| Worker behavior | FastAPI BackgroundTasks in current backend suite | Force brokerless in-process mode; use a six-second poll deadline and a ten-second drain/ack boundary. A real Celery lane requires its own run-unique queue and worker process. |
| Emulator | In-process ASGI WB emulator and temp SQLite | Run-local emulator DB/namespace; no socket allowlist entry is required for ASGI transport. |
| Subprocess | No collected backend test currently declares a network subprocess | All future subprocesses use the gate helper with 60-second timeout and owned process group; unknown launch paths fail the inventory meta-test. |
| Network policy | Broad socket guard with live opt-in | Canonical gate rejects live opt-in, records denial events and requires guard-loaded attestations from parent and Python children. |
| Logs | Ephemeral terminal stream | Run-local structured events plus sanitized stdout/stderr, stack dump, JUnit and atomic summary, uploaded on `always()`. |

## Canonical invocation and environment

The supervisor launches each attempt without `bash -lc`:

```text
<current-python> -m pytest
  -c <repo>/backend/pyproject.toml
  <repo>/backend/tests
  -p pytest_asyncio.plugin
  -p pytest_timeout
  -p scripts.testing.pytest_gate_plugin
  -vv -ra --tb=short --strict-config --strict-markers
  --timeout=150 --timeout-method=signal
  --junitxml=<attempt>/junit.xml
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` makes plugin loading deterministic. The
supervisor clears `PYTEST_ADDOPTS`; any selector, deselection or collection-only
request is rejected before pytest starts. The process working directory is the
run-specific attempt directory, not `backend`, so Pydantic cannot discover the
repository's `.env`. Backend import paths and pytest configuration are passed
explicitly.

The child environment is built from an allowlist, not a copy with a few
deletions. It sets a fixed test `APP_ENV`, JWT test value, absolute run-local
`DATABASE_URL`, `WMS_DATA_DIR`, cache/temp directories, `WMS_TEST_EGRESS=deny`,
`PYTHONNOUSERSITE=1`, the Python guard path and a run ID. It does not carry
proxy, AWS/S3 credential, external base URL, production database, Redis/Celery,
live marketplace opt-in or arbitrary plugin variables. Test base URLs are
fixed to in-process `.test` names, but socket DNS to those names remains
blocked; only an explicit ASGI/mock transport may consume them.

The default backend full gate uses brokerless FastAPI BackgroundTasks. A future
real-worker case is not silently folded into this command: it must declare a
local broker, queue `blg-d22-<run-id>`, worker PID and drain/ack receipt, and it
must pass through the same supervisor and network policy.

## Timeout policy

Initial budgets are deliberately finite and versioned in
`scripts/testing/full_backend_gate_policy.json`:

| Boundary | Budget | Diagnostic and termination behavior |
| --- | ---: | --- |
| Fixture DB/data reset | 30 s | Record `fixture_reset`; fail `TEST_ENVIRONMENT_FAILED`. |
| In-process ASGI HTTP operation | 15 s | Record route category and boundary; do not record body, auth or raw identifiers. |
| External HTTP connect/read/write/pool | 2/10/10/5 s | Socket guard should deny first; a permitted local dependency timeout is `TEST_TIMED_OUT`. |
| SQLite busy wait | 5 s | Record `db_lock:sqlite`; no indefinite retry. |
| PostgreSQL connect/lock/statement | 5/5/20 s | Applied only to approved local run-unique DB/schema. |
| Background poll | 6 s total, 0.1 s interval | Record last job state; timeout remains named to the current node. |
| Worker drain/ack | 10 s | Applies to an explicitly started run-owned worker only. |
| Owned subprocess | 60 s | Stack/status capture, TERM for 5 s, then KILL for 5 s to its own group. |
| Pytest item fallback | 150 s total | `pytest-timeout`; last phase/boundary from the journal identifies the hang. |
| Silent-item stack snapshots | 30 s and 90 s | Send a diagnostic-only faulthandler signal; do not classify or kill yet. |
| One full-suite attempt | 2700 s | Supervisor emits a suite timeout with last node/phase/boundary. |
| Two-attempt canonical command | 5550 s | Two 2700 s attempts plus 150 s reset/compare allowance. |
| CI backend job | 100 min | Leaves time for cleanup and artifact upload after supervisor containment. |

The item fallback covers setup, call and teardown, while the plugin's active
phase event names which phase consumed it. Potentially blocking operations
inside that item use the smaller owning-boundary budgets above. A timeout
override cannot come from an environment variable or raw pytest marker. It
must be a policy row keyed by exact node ID, with a measured reason, owner,
maximum value and expiry; expiry or unmatched node fails the gate.

The supervisor does not widen a budget after a red run. S15/S22 may revise a
budget only from preserved timing evidence and a new reviewed policy hash.

## Test isolation and fresh-state protocol

Each command creates
`.artifacts/pytest-gate/<git-sha>/<run-id>/attempt-01` and `attempt-02`. The
directory is ignored by Git and is the only writable evidence/runtime root for
the gate. Each attempt gets:

- a distinct SQLite file or approved local PostgreSQL database/schema;
- a distinct `WMS_DATA_DIR`, temp directory, cache directory and emulator DB;
- fixed clock/seed metadata where tests expose those controls;
- brokerless background execution by default, or a distinct declared Celery
  queue and owned worker PID when a worker lane is explicitly enabled;
- an environment hash computed only from allowlisted non-secret names and
  normalized values;
- reset-start and reset-finish events plus cleanup status after normal exit,
  timeout, interrupt and crash.

`backend/tests/conftest.py` must derive all mutable paths from
`WMS_TEST_RUN_ROOT` and refuse the canonical mode when it is absent. The
`async_client` fixture wraps schema reset and ASGI transport operations with
the gate boundary helper. Existing test modules do not receive a parallel
filesystem or DB mode until the collection manifest and isolated full run prove
that the new fixture path is compatible.

The normalized comparison fingerprint contains collection hash; per-node
setup/call/teardown outcome; approved skip/xfail reason; top-level result class;
and completed/failed/skipped counts. Timestamps, durations, PIDs and run paths
are excluded from equality but retained in evidence. Any node outcome or
classification difference yields `FLAKY_RESULT` and preserves both constituent
results.

## Fail-closed external egress

The existing `test_egress_guard.py` remains the shared low-level policy module,
but the canonical supervisor invokes it in a strict backend-gate mode:

1. Reject `WMS_TEST_EGRESS_ALLOW_LIVE_MARKETPLACES=1` instead of honoring it.
2. Build an exact per-run allowlist. The default backend gate allows loopback
   sockets only. `*.test`, `wb-emulator`, `db` and `redis` are not socket
   allowlist defaults for this command.
3. Require a `guard_loaded` event from the parent and every Python child before
   accepting its test evidence. The Node preload remains available only for a
   declared Node child.
4. On denied DNS/connect, append a sanitized `external_call_blocked` event
   before raising a dedicated exception. The event contains run ID,
   `PYTEST_CURRENT_TEST`, phase, dependency category, port class and a stable
   host hash; it does not store the raw URL, headers or body.
5. The result classifier checks denial events independently of pytest's
   exception report. Thus code that catches the exception cannot turn a live
   attempt into `TEST_FAILED` or pass.
6. A subprocess may be launched only through the gate helper, which supplies
   the guard environment. Discovery of `curl`, an unhooked binary protocol or a
   child that removes the guard is a failed S15/S20 inventory, not an allowed
   bypass.

This card does not claim to close `BLK-PIPE-004`, whose minimum closure includes
every test entrypoint and the browser path. BLG-D22 owns the canonical backend
pytest surface only. It must not edit `docs/product/blocks.json` or resolve that
separate registry item.

## Progress journal and evidence schema

The gate writes the following under each run directory:

- `run.json`: exact SHA, fixed command, policy hash, sanitized environment
  identity, start time and attempt IDs;
- `attempt-N/events.jsonl`: fsync'd collection, node, phase, boundary, timeout,
  egress, signal and cleanup events with a monotonic sequence number;
- `attempt-N/collection.json`: ordered node IDs, collection hash, deselected
  count and approved skip-policy hash;
- `attempt-N/stdout.log` and `stderr.log`: sanitized child streams;
- `attempt-N/stackdump.log`: faulthandler output captured before controlled
  termination;
- `attempt-N/junit.xml`: pytest report supporting assertion/error details;
- `attempt-N/reset.json`: DB/data/emulator/queue identities and teardown result;
- `attempt-N/summary.json`: atomic typed attempt result and counts;
- `summary.json`: comparison fingerprint, both log hashes and the sole final
  result class.

The schema records at least: `task_id`, `run_id`, `attempt_id`, exact Git SHA,
command hash, policy hash, fixture/reset identity, start/finish monotonic and
UTC times, exit/signal, collected/completed/failed/skipped/deselected counts,
last node, phase, boundary, configured timeout, elapsed time, result class and
redaction status.

CI stores the full sanitized run directory as an artifact on `always()`. Only
the later accepted BLG-D22 evidence subset and hashes may enter
`docs/evidence/BLG-D22/`; raw streams are never committed automatically. The
evidence writer uses allowlisted fields and masks tokens, cookies, credentials,
production URLs, personal data, order IDs, barcodes and marking codes before
disk. Missing `REDACTION_VERIFIED` makes the gate non-green.

## Result classification

The classifier applies this order and retains subordinate causes:

1. `FLAKY_RESULT` when equivalent fresh attempts disagree in collection,
   node outcomes or top-level classification.
2. `EXTERNAL_CALL_BLOCKED` when either attempt contains a denied DNS/connect
   event, regardless of a later caught exception or assertion.
3. `TEST_TIMED_OUT` when a named boundary, item or suite budget expires. It
   requires last node and phase; a suite timeout additionally records the last
   known boundary and stack artifact.
4. `TEST_ENVIRONMENT_FAILED` for collection/configuration/internal pytest
   errors, fixture setup/teardown/reset, DB/queue/worker bootstrap or cleanup
   failure before a valid test-call verdict.
5. `TEST_FAILED` for a completed call-phase assertion or exception with a
   valid node report.
6. `RUN_INTERRUPTED` for an unrecognized signal, missing terminal event,
   missing/invalid summary, supervisor crash or child exit that matches none of
   the typed paths.
7. `FULL_GATE_PASSED` only when both attempts return zero; collect the same
   non-empty intended manifest; have zero deselected, unexpected skipped,
   expired quarantine and strict-xpass nodes; account for every collected
   node; complete cleanup; match normalized fingerprints; and pass redaction
   plus egress attestations.

An approved skip/xfail exists only in a versioned policy row with exact node
ID, oracle/reason, owner and unexpired date. Raw `pytest.skip`, an unknown
marker, broad path pattern or unconditional quarantine is an unexpected skip
and prevents `FULL_GATE_PASSED`. This preserves legitimate environment lanes
without letting a new skip manufacture green.

## Future implementation write set

S18 is one atomic implementation over the following planned files. It must not
be split into independently claimable timeout, logging or network changes.

| Planned file | Responsibility |
| --- | --- |
| `scripts/testing/full_backend_gate.py` | Fixed invocation, environment construction, two attempts, process ownership, watchdog, classification and exit mapping. |
| `scripts/testing/full_backend_gate_policy.json` | Versioned timeout, allowed dependency, skip/quarantine and evidence policy. |
| `scripts/testing/full_backend_gate.schema.json` | Strict run/event/attempt/final summary schema. |
| `scripts/testing/pytest_gate_plugin.py` | Collection, node/phase progress, boundary context and atomic pytest lifecycle evidence. |
| `scripts/testing/test_egress_guard.py` | Strict canonical mode, allowlisted environment and denial-event adapter. |
| `scripts/testing/sitecustomize.py` | Python child startup attestation plus sanitized deny event before exception. |
| `scripts/testing/test_egress_node.cjs` | Declared Node-child parity only; no broad default allowlist. |
| `scripts/testing/full_gate_fixtures/**` | Deliberate pass, assertion, timeout, fixture error, egress, interrupt and flaky mini-suites; never part of the WMS full-suite collection. |
| `backend/tests/conftest.py` | Run-local DB/data/emulator paths, brokerless test settings and boundary-wrapped fixture reset/ASGI transport. |
| `backend/pyproject.toml` / `backend/uv.lock` | Pinned pytest-timeout/report support and strict pytest options. |
| `backend/tests/full_gate_inventory.json` | Collected baseline from real blocker-closure evidence; exact node IDs and approved skip/xfail rows. |
| `scripts/ci/check_full_backend_gate.py` | Fast deterministic public-entrypoint meta-tests and schema/policy/inventory checks. |
| `scripts/ci/check_pipeline_metatests.py` | Enforce the canonical backend entrypoint and reject raw CI pytest bypasses. |
| `.github/workflows/ci.yml` | Canonical command, 100-minute job limit and always-upload evidence. |
| `CLAUDE.md` / `scripts/hooks/rules_card.py` | Replace raw backend pytest guidance with the one supported command. |
| `.gitignore` | Ignore `.artifacts/pytest-gate/` runtime directories. |
| `docs/process/FULL-PYTEST-GATE-RU.md` | S21 operator/reviewer runbook, result meanings and evidence location. |

The initial plan permits targeted test-harness updates only in the currently
observed bounded-poll owners:

- `backend/tests/test_background_jobs.py`;
- `backend/tests/test_wildberries_cards_sync_job.py`;
- `backend/tests/test_wildberries_supplies_sync_job.py`;
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`;
- `backend/tests/test_fbs_orders_intake.py`;
- `backend/tests/test_products_wb_catalog.py`;
- `backend/tests/test_wildberries_product_link_api.py`.

Those files may only replace duplicated sleeps/polls with the gate-aware
bounded helper; assertions and business expectations remain unchanged. The
isolated node named by the future `BLK-TEST-001` closure evidence may be added
to the write set only through an S13 scope revision if it is not listed above.
There is no wildcard permission to edit all tests, delete tests or touch
`backend/app/**`.

Read-only dependencies include `pipeline/pipeline.yml`,
`pipeline/model-policy.yml`, `docs/product/blocks.json`, the S11/S12 inputs,
current WB clients and current test modules. Runtime state and receipts remain
controller-owned.

## Locks and ordering

The future S17 workspace must acquire locks in this canonical order:

1. `control-plane:test-gate-policy`;
2. `test-entrypoint:backend-full-pytest`;
3. `test-egress:python-node-hooks`;
4. `test-fixture:backend-conftest`;
5. `dependency:backend-dev-lock`;
6. `ci:backend-pytest-job`;
7. each exact file in the accepted S18 write set.

The shared egress files overlap the broader open `BLK-PIPE-004` area. Any card
implementing that broader surface must serialize behind BLG-D22 or rebase onto
its accepted candidate; parallel edits to the guard, CI backend job or pipeline
metatests are forbidden. The blocker registry itself is not locked for writes
because BLG-D22 does not own it.

At runtime, every attempt uses a separate run directory, DB/schema, optional
queue, port set and process group, so two canonical commands cannot share
writable test state. Lock acquisition is for code integration; run IDs provide
execution isolation.

## Stage implications

### S14 ARCHITECT_FALSIFICATION

An independent reviewer must attack at least:

- setup or teardown hangs before the plugin records a phase;
- pytest timeout/plugin failure, signal conflict and log loss on forced death;
- caught egress exceptions, direct IP, DNS rebinding, proxy, inherited live
  opt-in, child process and non-Python client bypasses;
- `.env`, Celery broker, S3 or production DB inheritance;
- a timeout that kills another task or shared worker;
- collection-only, `-k`, deselection, stale/cached log, deleted test, broad
  skip, xpass and single-attempt false passes;
- assertion, fixture error, timeout, external denial and interrupt
  misclassification, including multiple simultaneous events;
- shared SQLite/data paths, attempt-order dependence and stale worker/emulator
  state;
- evidence containing a token, URL, order/barcode/marking identifier or a
  missing redaction attestation;
- resource-lock overlap with the broader egress work.

### S15 CASE_FACTORY and BLK-TEST-001

S15 must preserve every S12 direct and breaker case and add public-entrypoint
cases for fixed argv, two-attempt collection equality, guard startup
attestation, process-group cleanup, timeout-policy expiry, unexpected skips,
environment scrubbing and result-precedence collisions. Deliberate hangs and
external destinations live only in `full_gate_fixtures/**` and must be local,
deterministic and side-effect free.

`BLK-TEST-001` remains open. S13 and S14 may complete, but S15 must not emit
`CASES_READY` or `CASE_AUDIT_PASSED` until the controller records the
pipeline-reviewer's valid `resolve-blocker` evidence: isolated hanging node ID,
controlled timeout and successful full-run log, together with the exact SHA,
canonical command, closed external dependency and skip reasons required by the
registry packet. S13 does not fabricate that evidence and does not run the
full suite.

If the reviewer proves that blocker closure is impossible before implementing
this gate, that is a controller-stage deadlock, not permission to enter Dev.
The controller/owner must explicitly revise the blocker contract or resume
stage in its owning pipeline card; BLG-D22 cannot self-resolve or hand-edit the
registry.

### S18 DEVELOPMENT

S18 starts only after controller resolution of `BLK-TEST-001`, accepted S14,
`CASES_READY`, S16 Product approval over exact hashes and S17 locks. It delivers
the complete supervisor/plugin/isolation/egress/classifier vertical card. It
does not modify application behavior, weaken tests, call a live service or use
a targeted pass as full-gate proof.

### S19 TEST_AUTOMATION_BINDING

Every S15 case binds to one of:

- a deterministic mini-suite invocation through
  `scripts/testing/full_backend_gate.py` test-fixture mode;
- the canonical no-argument full backend command;
- `scripts/ci/check_full_backend_gate.py` for schema/policy/bypass checks.

Bindings record the exact policy hash, fixture/reset builder, timeout, expected
events, expected exit code and evidence paths. Calling the classifier or plugin
function directly is component evidence and cannot satisfy S25.

### S20 CODE_REVIEW

Review must prove the fixed command cannot be narrowed; every kill is scoped to
the owned process group; environment construction cannot load secrets or live
connections; denial events cannot be swallowed; result precedence is stable;
no test/assertion was weakened or deleted; policy overrides are reviewed and
expiring; all claimed subprocess/network surfaces are inventoried; and
controller/CI/manual guidance point to the same entrypoint.

A finding in timeout ownership, resource graph, egress or classification is
`PLAN` and returns to S13. A missing runnable fixture is `AUTOMATION` and
returns to S19. A changed test expectation returns to S15/S08, not S18.

### S22 and S23

S22 executes all deliberate local pass/failure fixtures, then the canonical
two-attempt full gate on a fresh isolated stack. A red attempt is rerun only
according to Pipeline v2 triage; disagreement is `FLAKY_RESULT`, not a green
retry. Evidence must include the isolated node and controlled timeout needed by
the contract, plus a real successful complete log if one occurred.

S23 runs the same fixed command on the pinned integration SHA with the exact
dependency lock and policy hashes. It rejects any different collection
manifest, rebuilt tree, missing CI artifact, changed gate policy, unreviewed
skip or stale run. The integration receipt binds Git SHA, collection hash,
both attempt summaries and evidence hashes. It proves no production or live
marketplace state.

### S25 and S26

Independent S25 acceptance runs the supported public command against the exact
S23 candidate and exercises deliberate assertion, timeout and blocked-egress
fixtures. It verifies the successful full-suite path, all seven result classes,
fresh-state comparison and evidence survival after controlled termination.
Source inspection, a targeted pytest node or a hand-written summary is not
acceptance.

Without separate release authority S26 may report only the controller's honest
pre-release result such as `READY_FOR_RELEASE`. BLG-D22 authorizes no S27/S28,
deploy, production test or secret operation.

## Required S15/S22 cases

In addition to S12, the accepted case set must include:

- fixed command collects the full intended backend tree twice with identical
  ordered node IDs and zero deselection;
- a call-phase assertion is `TEST_FAILED`, while setup/teardown/reset and
  collection failures are `TEST_ENVIRONMENT_FAILED`;
- hangs in setup, call and teardown each preserve node, active phase, elapsed
  time, configured timeout, boundary and stack dump;
- the suite watchdog synthesizes `TEST_TIMED_OUT`, never a blank outer timeout,
  when the item plugin itself is disabled or deadlocked;
- a denied hostname, direct IP, proxy route, inherited live opt-in and caught
  denial all become `EXTERNAL_CALL_BLOCKED` before any side effect;
- a child that lacks `guard_loaded` cannot contribute a green result;
- SIGTERM, SIGKILL and supervisor interruption retain the last active node and
  produce the expected timeout or `RUN_INTERRUPTED` path;
- two fresh passes agree; pass/fail, pass/timeout, different collection and
  different skip outcomes all become `FLAKY_RESULT`;
- targeted selection, collection-only, stale summary, empty log, missing exit,
  zero collected nodes, deselection, unknown skip, expired quarantine and
  strict xpass cannot produce `FULL_GATE_PASSED`;
- inherited production DB, Redis/Celery, proxy, S3/cloud credential or `.env`
  values are absent from the child and absent from evidence;
- two simultaneous gate runs use different DB/data/emulator/process roots and
  cleanup cannot cross run IDs;
- all committed evidence passes redaction and contains no raw token, cookie,
  URL, order ID, barcode or marking code.

## Stop conditions and minimum closure

Return to S13 or hold the owning stage if any of these remains unresolved:

- CI, local guidance or an agent can claim the full gate through a different
  command or selector;
- any setup/call/teardown, DB, HTTP, poll, worker or subprocess wait has no
  finite owner and diagnostic event;
- a live opt-in, inherited `.env`, proxy, direct IP or child process bypasses
  the egress decision;
- a timeout can terminate shared resources or another run;
- a non-success path can lose node/phase/boundary evidence;
- classification can flatten egress, timeout or fixture failure into an
  ordinary assertion or pass;
- the second attempt reuses mutable state or a disagreement is accepted green;
- a skip, deletion, stale log, missing summary or incomplete collection can
  produce `FULL_GATE_PASSED`;
- Dev requires `backend/app/**` or a file outside the accepted write set;
- `BLK-TEST-001` is still open when S15 attempts a pass verdict.

Minimum architecture-to-Dev closure is: accepted S14; controller-resolved
`BLK-TEST-001` with its real evidence; complete audited cases; one fixed public
command; strict versioned timeout/result/evidence policy; two fresh attempts;
fail-closed egress with child attestation; owned process cleanup; exact write
locks; and S16 approval over all bound hashes.

There is no S13 blocker. The next allowed stage is independent S14
falsification; the existing blocker still stops S15 and all later Dev gates
until controller resolution.
