# WMS-652 / WMS-662 F6: correction of PID evidence in the lock fixture

Date: 07.10.2026.

## Observed CI failure

`backend-checks-419.log` from GitHub Actions run `37550233864` recorded one
failure among the four F6 parameter combinations:
`observed_status-normal`. PostgreSQL had already confirmed contention, but the
last mutable PID map was `{cancel: 90, handoff: 90}` and the test failed its
independent-backend assertion. The adjacent diagnosis
`wms662-f6-pid-diagnosis.md` explains the cause: the listener replaces a live
role PID before every relevant query, while the normal handoff may commit and
obtain another pooled connection after cancellation is released.

This is a fixture-observation failure. The old assertion stopped the scenario
before its later stock, reserve, billing and retry assertions, so the failed CI
run is not evidence that those product assertions passed.

## Contract and correction

Commit `fb05f4dc22a1fb6b62ab0d52be2729ae4b449f3c` adds the narrow regression
`test_f6_confirmed_wait_pid_pair_survives_postrelease_pool_reuse`. Before the
fixture correction it was red with `AttributeError` because no immutable
confirmed pair existed. The test models a confirmed query for distinct PIDs,
then overwrites the live handoff PID with the cancellation PID, matching the
post-release pool reuse from CI.

The fixture now snapshots the two exact PIDs used as bind values before awaiting
`pg_blocking_pids`. It assigns that snapshot to `observed_pids` only after
PostgreSQL returns a confirmed block, before releasing cancellation. The live
PID map remains mutable diagnostic data and every observed live PID is retained
in `live_pid_trace`. The four existing parameter cases keep all of their
business assertions; their independent-backend assertion now checks the frozen
confirmed pair instead of later pool state.

## Local verification and limit

The existing backend virtual environment ran Ruff on both narrow test files and
the new regression passed. The regression was red before the fixture correction
for the expected missing-snapshot reason.

The four real PostgreSQL cases were invoked with the project’s isolated F6
target, but this checkout had no PostgreSQL service listening on its dedicated
loopback port (connection refused during fixture setup). They therefore did not
exercise product logic locally and remain required in CI. No production or
staging migration/database was contacted.
