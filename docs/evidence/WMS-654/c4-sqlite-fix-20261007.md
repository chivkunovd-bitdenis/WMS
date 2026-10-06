# WMS-654 · C4 SQLite conflict classification fix

## Scope and cause

The frozen C4 repeat case recorded in
`c4-sqlite-ci-red-20261007.md` reached the database uniqueness constraint for
the already-created address, but SQLite reported it as
`UNIQUE constraint failed: storage_locations.warehouse_id, storage_locations.code`.
`create_location_from_rack` recognized only the PostgreSQL constraint names, so
it re-raised `IntegrityError` instead of returning the existing
`CatalogError("location_code_taken")` contract.

## Product change

Only `backend/app/services/catalog_service.py` changed.  In the existing
`IntegrityError` handler of `create_location_from_rack`, the address-conflict
condition now also recognizes SQLite's exact unique-constraint text for
`storage_locations.warehouse_id, storage_locations.code`.

The handler still rolls back before classification; PostgreSQL constraint-name
recognition is unchanged; barcode collisions still retry; and unrelated
integrity errors still re-raise.  No model, migration, API contract, frozen
test, UI, CI, guard, or requirement was changed.

## Receipts

The final source was checked with:

```text
cd backend && /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check app/services/catalog_service.py
```

Result: `All checks passed!`.

The actual SQLite C4 repeat contract was run sequentially against the isolated
task-local database at `.agent-runs/wms_test_654_fix_sqlite.db` with the frozen
test ID
`backend/tests/test_wms654_cells.py::test_c4_repeat_conflict_does_not_duplicate_new_address`.
Result: **1 passed, 0 skipped**.  The JUnit receipt is ignored at
`.agent-runs/wms654-c4-sqlite-fix-20261007.xml`.

The PostgreSQL race contract was run sequentially against the existing isolated
local WMS-654 tester database, using the exact frozen parameter IDs
`test_c4_postgresql_concurrent_requests_have_one_winner[False]` and
`test_c4_postgresql_concurrent_requests_have_one_winner[True]`.
Result: **2 passed, 0 skipped**.  The JUnit receipt is ignored at
`.agent-runs/wms654-c4-postgresql-fix-20261007.xml`.

Together, the address-targeted C4 receipt is **3 passed, 0 skipped**.  The
PostgreSQL checks prove the existing two race variants; the SQLite run proves
the newly added SQLite message classification.

## Limitations

This is an address-only implementation check.  Full pytest, mypy, frontend
checks, independent review, analyst acceptance, full CI, publication, merge,
and deployment are outside this developer handoff and are not claimed here.
