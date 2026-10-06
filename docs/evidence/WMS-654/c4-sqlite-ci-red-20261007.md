# WMS-654 · C4 SQLite CI RED

## Scope

This is a tester evidence record only.  It preserves the frozen C4 contract
from `d841e1445cf5867002e9341b35741ecaf90ca3a2`; it changes no product code,
test expectation, guard, CI configuration, or requirement.

- Candidate checked: `c6ffee0e91ace6c7bd638a1d81a7ded0842da5bf` (`WMS-654: независимый Astra high PASS коррекции C8`).
- Test ID: `backend/tests/test_wms654_cells.py::test_c4_repeat_conflict_does_not_duplicate_new_address`.
- Frozen observable expectation: the first new-mode create returns 200; its repeat returns HTTP 409 with `location_code_taken`; a distinct tier creates a second, distinct address.  The test also verifies there are exactly two non-sorting rows and two barcodes.

## Reproduction — RED

The test was run once, sequentially (`-n0`), with the existing root backend
virtual environment and a test-only SQLite file below this worktree's ignored
`.agent-runs/` directory:

```text
cd backend
WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////Users/deniscivkunov/Projects/WMS/.worktrees/wms654-product-20261006/.agent-runs/wms_test_654_ci_sqlite.db \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n0 -q \
  -o asyncio_default_fixture_loop_scope=session \
  -o asyncio_default_test_loop_scope=session \
  --tb=short \
  --junitxml=../.agent-runs/wms654-c4-sqlite-ci-red.xml \
  tests/test_wms654_cells.py::test_c4_repeat_conflict_does_not_duplicate_new_address
```

Result: **1 failed in 2.02s**.  This is a meaningful product failure, not a
fixture or import error: the first request created `А 2.3.4`; the repeat reached
the database insert and raised `sqlite3.IntegrityError: UNIQUE constraint failed:
storage_locations.warehouse_id, storage_locations.code` before an HTTP response
could be asserted.

Ignored receipts retained for the developer handoff:

- `.agent-runs/wms654-c4-sqlite-ci-red.log` — SHA-256 `9ce697138682be994856e50730839bc903ec65fa337b5306e1d892f501b5462c`
- `.agent-runs/wms654-c4-sqlite-ci-red.xml` (JUnit) — SHA-256 `1b8f49213f8075c563c48aaa4cfa29c243fb66d94a486f931d0a0f9116ad1457`

The test configuration accepts the supplied SQLite URL without a special
prefix check; the explicit absolute filename above is nevertheless inside this
task's ignored `.agent-runs/` directory, so no shared or production database was
used.

## Confirmed cause

`create_location_from_rack` catches the database `IntegrityError`, rolls back,
then classifies an address conflict only if the normalized message contains the
PostgreSQL constraint spelling `uq_storage_locations_wh_code` or
`storage_locations_wh_code`.  SQLite's actual message names the columns instead:
`storage_locations.warehouse_id, storage_locations.code`.  It therefore reaches
the bare re-raise rather than `CatalogError("location_code_taken")`.

The route already maps that `CatalogError` to HTTP 409 and the required detail,
so the missing piece is SQLite-aware classification in the existing service
path; this report does not implement it.

This independently confirms the full-CI 392 failure on the same candidate:
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/pr392-backend-failure.log`
shows the same C4 SQLite `UNIQUE` error.  The local receipt above rules out an
inference based solely on that historic log.

## WMS-653 scope boundary (read-only)

The obsolete PR-392 guard compared the whole candidate to `origin/etalon`, which
incorrectly attributed WMS-654's model and migration to WMS-653.  The files are
introduced by `9ecf0a916d012de97948c49ee367aeccbb7d0229`, whose subject is
`WMS-654: стороны и ярусы рабочих ячеек`:

- `backend/app/models/storage_location.py`
- `backend/alembic/versions/20261007_2302_wms654_location_tier.py`

The current common-integration WMS-653 scope contract is task-scoped instead:
it walks from immutable contract `9f131c42bec5266b90abb499c56060c0f3bd4b70`
and admits commits only when their subject matches
`^WMS-653(?:\\s+WMS-\\d+)*:`.  The WMS-654 source commit does not match that
filter, so its model and migration are outside the WMS-653 delta and must not be
reported by the normal guard.

One read-only execution of that common-integration test file produced 33 passing
tests and one existing scope failure caused only by untracked WMS-652 evidence
and review files in that other checkout.  Its failure list contains no WMS-654
model or migration path.  The separate trusted corrected-scope lane is owned by
root; no common checkout, session, model, or guard was modified here.

## Handoff

Status for C4 on SQLite at the stated SHA is **RED**.  Preserve the frozen
expectations and change only the product implementation needed to convert this
specific address uniqueness violation into the existing 409 contract.  Re-run
this exact test against the same isolated SQLite URL after the implementation
change.
