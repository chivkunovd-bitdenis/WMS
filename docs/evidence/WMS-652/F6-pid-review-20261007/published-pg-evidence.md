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

## Local verification

The existing backend virtual environment ran Ruff on both narrow test files and
the new regression passed. The regression was red before the fixture correction
for the expected missing-snapshot reason.

The first attempt could not reach the dedicated F6 PostgreSQL port because no
local service was listening. It was not treated as a product result. A separate
throwaway PostgreSQL 17 cluster was then initialized under the ignored
`.agent-runs/night-20261006-01a112a8/f6-local-pg` directory, listening only on
`127.0.0.1:55467`. It used the test-only `wms_test_662_f6` database and did not
connect to the existing server on port 5432.

With the existing backend virtual environment and `-n 0`, the real PostgreSQL
F6 command completed all four cases: `local-normal`, `local-observed`,
`observed_status-normal`, and `observed_status-observed`. JUnit reports 4 tests,
0 failures, 0 errors, in 3.389 seconds. The narrow PID-pool-reuse regression
also passed: 1 test, 0 failures, 0 errors, in 0.040 seconds.

Raw, ignored artifacts are retained at:

- `f6-local-pg/f6-four-cases.xml` — SHA-256
  `2b461fbff0568a1fb8b67fc809d727407a909a1d7cf44a79771f71bfd23d68a3`;
- `f6-local-pg/f6-four-cases.log` — SHA-256
  `d04381cda74c44380fbbe59ac75590dfafe2516430ce90889f64c5f16df8cffa`;
- `f6-local-pg/f6-pid-regression.xml` — SHA-256
  `3524cc49ccf48c27b6b71b0da717d30783c475731c5b4184bc37dccb92985b40`;
- `f6-local-pg/f6-pid-regression.log` — SHA-256
  `2c44d003d32fa097d8bdcbe88a039d7914d326edebe881dd2a3d76df980d76bb`.

After the runs, `pg_ctl` stopped this owned cluster and port 55467 was confirmed
free. No production or staging database, migration, Docker daemon, dependency
installation, or product code was used in this verification. This targeted run
does not replace the required independent review or CI of the integrated SHA.
