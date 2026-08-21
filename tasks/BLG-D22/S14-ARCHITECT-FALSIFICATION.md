# S14 ARCHITECT_FALSIFICATION - BLG-D22

## Verdict

`ARCH_REVIEW_REWORK`

S13 is directionally strong but is not safe to hand to S15/S18 yet. Four
unresolved plan findings can still produce either a hidden external side
effect, an unclassified pre-node hang, secret-bearing evidence, or a false
`FULL_GATE_PASSED`. They are architecture findings and therefore return to
S13; they are not grounds to close or pass `BLK-TEST-001`.

This review was performed independently as `pipeline-reviewer`. It was static:
no full pytest run, S15 case work, application-code change, external call,
secret operation, release or deploy was performed.

## Findings

### F1 - REWORK: user-space hooks are evidence, not a fail-closed network boundary

S13 keeps `sitecustomize.py` and the Node preload as the low-level enforcement
and handles an unhooked binary or a child that removes the guard as a later
S15/S20 inventory failure. That detects a design violation but does not prevent
the process from sending a packet first. The current guard demonstrates the
gap: it monkey-patches Python `socket`, while non-Python children remain outside
that control. It also treats all loopback addresses as allowed. A local proxy,
tunnel, shared PostgreSQL/Redis service or unrelated task can therefore be
reached even though it is not owned by the run.

Required S13 correction:

- put the canonical gate behind an outer OS/container network policy that is
  inherited by every child and denies all egress before user code runs;
- default to no socket access for the brokerless/in-process lane;
- allow only exact run-owned endpoint identities and ports for a declared local
  PostgreSQL, Redis, worker or emulator lane, with ownership attestation;
- retain Python/Node denial events and `guard_loaded` as attribution evidence,
  but do not treat them as the sole enforcement boundary;
- add a side-effect-free breaker proving that direct IP, proxy, DNS rebinding,
  an unhooked native/non-Python child and broad loopback cannot transmit.

This requirement is scoped to the canonical backend gate. It does not claim to
close the broader browser/entrypoint blocker `BLK-PIPE-004`.

### F2 - REWORK: the timeout model has no identity before a pytest node exists

The plan records `setup | call | teardown` and requires a suite timeout to carry
the last node and phase. Pytest/plugin import, configuration and collection can
hang before either exists; `pytest-timeout` is itself unavailable until plugin
loading succeeds. In that path the planned classifier cannot satisfy its own
node/phase requirement and falls through to a blank suite timeout or
`RUN_INTERRUPTED`. The signal ownership is also incomplete: the plan assigns a
pytest item signal, two faulthandler snapshots and supervisor termination but
does not reserve concrete signals or define collision behavior.

Required S13 correction:

- model supervisor-owned lifecycle phases before and after item execution,
  including `spawn`, `plugin_load`, `configure`, `collection`, `session_finish`
  and `cleanup`, each with an active operation identity and heartbeat;
- define deterministic classification for a timeout in every lifecycle phase,
  including collection with no node ID;
- provide an explicit signal table for pytest-timeout, faulthandler snapshots,
  operator/CI interruption, TERM and KILL, including unsupported-platform
  behavior and what evidence must already be durable;
- add breaker cases for plugin import/configure/collection deadlock and signal
  collision, not only setup/call/teardown hangs.

### F3 - REWORK: raw diagnostic producers bypass the stated redaction boundary

S13 calls `stdout.log`, `stderr.log`, `stackdump.log` and `junit.xml` sanitized,
then says an allowlisted evidence writer masks values before disk. Pytest JUnit,
faulthandler and child streams are independent producers and may contain an
exception value, URL, token, order ID or marking code before that writer sees
them. Uploading the full run directory on `always()` can therefore publish raw
data even when the final summary later reports redaction failure.

Required S13 correction:

- separate a private, short-lived raw spool from the uploadable evidence tree;
- never upload or commit the raw spool, and remove it through owned cleanup;
- derive JUnit, stack and stream evidence into a strict allowlisted sanitized
  schema before it enters the upload tree;
- make `REDACTION_VERIFIED` cover every uploaded file and fail closed on an
  unknown file, parser failure, truncation or interrupted sanitization;
- add canary breakers for secrets and business identifiers in assertion text,
  captured output, stack locals and JUnit properties.

### F4 - REWORK: the intended full-suite manifest leaves the PostgreSQL lane optional

The canonical command defaults to isolated SQLite while S13 permits exact,
approved skip rows. The current suite has PostgreSQL-only locking, partial-index
and migration tests that skip when `WMS_TEST_DATABASE_URL` is absent. Without a
lane decision, both attempts can match and return `FULL_GATE_PASSED` while the
production-specific database checks never ran. That is repeatable, but it is
not an unambiguous definition of the intended full backend gate.

Required S13 correction:

- define the canonical manifest as explicit required lanes, not only a node-ID
  list collected under whichever database happens to be present;
- decide whether the PostgreSQL lane is mandatory for `FULL_GATE_PASSED`; if it
  is, the public command must provision a run-owned local lane or return
  `TEST_ENVIRONMENT_FAILED`, never approve away its absence as a skip;
- bind each allowed skip/xfail to a lane and prove it is genuinely outside the
  required manifest for this gate;
- compare collection and outcomes per lane across the two fresh attempts.

## Classification requirement

S13 must also separate security cause from repeatability. With the current
precedence, one external denial and one pass become top-level `FLAKY_RESULT`,
while `EXTERNAL_CALL_BLOCKED` is only subordinate. The revised schema must keep
exactly one gate verdict while exposing independent `primary_cause` and
`repeatability_status`, or otherwise guarantee that an external-call attempt is
never hidden by the flaky aggregate. Assertion, environment, timeout,
interruption and egress evidence must remain individually queryable when more
than one occurs.

## Accepted parts of S13

The rework does not reopen the one-card Product boundary. The following parts
remain suitable inputs: one fixed public command; two fresh attempts; fixed
collection accounting; run-owned process groups and cleanup; no
`backend/app/**` escape hatch; boundary-specific finite timeouts; atomic
summaries; strict handling of selectors, skips, xpass and stale evidence; and
the downstream S18-S26 restrictions.

## Downstream route and blocker

The exact owning route is S13 `ARCHITECT_PLAN`; this is `REWORK`, not a new
section-31 blocker. S15 must not receive `CASES_READY` or
`CASE_AUDIT_PASSED`, and S18 must not start.

The controller was asked to record `ARCH_REVIEW_REWORK`, but rejected it with
`unmapped failure verdict: ARCH_REVIEW_REWORK`. No state mutation, receipt or
next-stage packet was produced. The task therefore remains `RUNNING` at S14
until the control plane adds or otherwise executes the canonical S14 -> S13
plan-finding route. Passing S14 to work around that missing route would be a
false architecture verdict.

`BLK-TEST-001` remains open, owned by `pipeline-reviewer`, with
`resume_stage: S15` and unchanged minimum closure evidence: isolated hanging
test ID, controlled timeout and successful full-run log. This S14 review does
not supply or fabricate any of those artifacts and does not claim the full gate
is fixed.
