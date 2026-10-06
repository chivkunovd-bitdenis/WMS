# WMS-681 C6: PostgreSQL / independent worker RED

Product code: `de76be359ea4c02a0ee70aa204eae2e853c47b1f`.
Exact checkout during final run: `4c3c53bb1a4057da7e003e024680c842c05abdc1`.
`git diff --stat de76be359 HEAD -- backend frontend` was empty: the later
commits add acceptance/UI/review documents without changing this product code.

## Result

**RED: C6 is not satisfied across independent workers.** One real endpoint
invocation succeeds and the other raises an unhandled PostgreSQL IntegrityError
(normal HTTP server outcome: 500). One external cargo-place create remains
preserved; the failure is concurrent QR-asset persistence after that create.

Final run: **1 failed, 0 skipped, 6 warnings, 12.76 seconds**. The actual JUnit
receipt is [red-junit.xml](red-junit.xml). It contains both worker/connection
identities, the observed PostgreSQL blocking relationship, HTTP results, SQLSTATE
and constraint, and the shared WB request history as test properties.

```sh
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_681_c6_20261007 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 0 \
  backend/tests/test_wms681_postgres_recovery.py --tb=short -o junit_family=legacy \
  --junitxml=docs/evidence/WMS-681/postgres-c6/red-junit.xml
```

```text
first OS PID 97647 / PostgreSQL backend PID 97660
second OS PID 97662 / PostgreSQL backend PID 97665
pg_blocking_pids(97665) = [97660]
WB create amounts = [5]
QR checkpoint = overlap
endpoint results = [200, 500]
SQLSTATE = 23505
constraint = uq_fbs_print_assets_ready_cargo_qr
```

## What the test executes

The original API fixture creates a synthetic seller, supply and two separate
physical groups in a newly created loopback-only database. Group A has five
existing physical boxes and a definitive failed404 journal; group B has one
box with a distinct order assignment. Two separate Python OS processes import
the unchanged product and call the real retry-QR FastAPI endpoint through ASGI.
Each has its own pinned PostgreSQL connection and independent in-process mutex
registry. They share only the actual PostgreSQL database and one loopback WB
HTTP server; recovery services, row locks, commits and asset storage stay real.

The WB create reply is paused while the second worker demonstrably waits on
the first worker's real supply-row lock. The create then completes once with
five IDs. At the first real QR fetch, the first operation has already committed
the confirmed trbx rows and released the row lock. The second worker proceeds,
restores the same physical-to-WB links and requests the same first sticker
before either sticker response is released. Both have observed no cached asset.

After both identical PNG replies, two transactions insert ready QR assets for
the same trbx. PostgreSQL rejects one on the unique ready-asset index. The
exception escapes the endpoint; the test requires both callers to complete
successfully and therefore fails at the final status assertion. Which worker
loses is scheduling-dependent; two runs reproduced the same constraint failure
with opposite losers.

Before that assertion, the real persisted state passed the checks: five trbxes,
five unique packaging owners, five linked boxes in A, five ready assets, one
confirmed cargo operation; B remains unlinked; original physical IDs, numbers,
keys, mode and barcode snapshot is unchanged; one POST create of amount five.
This is not evidence that every unknown-outcome/retry scenario is safe.

The barrier also accepts a future solution that retains the PostgreSQL lock
through QR retrieval: it can release the first reply when it sees the second
worker still blocked. It does not require duplicate QR fetches to pass and does
not prescribe a product implementation. SQLite explicitly skips this test.

## Scope and limits

PostgreSQL 17.10 (Homebrew), localhost:5432, own isolated database
`wms_test_681_c6_20261007`. The existing shared `conftest` rejects non-local or
non-`wms_test` targets, creates metadata schema, and clears fixture rows after
the run. No production copy or separate migration acceptance is claimed.
The fake WB server and both OS workers were stopped by test cleanup. The empty
owned database remains available for a developer rerun. No dependencies were
installed and no existing environment/database/role credentials were changed.

Static test lint passed:
`python -m ruff check backend/tests/test_wms681_postgres_recovery.py`.
The frozen backend/DOM contracts and product files were not edited. Only a
new test link was appended to C6; its requirements and acceptance verdict are
left to the analyst. UI/CUA, physical paper, full CI and deployment are separate
evidence and were not performed in this session.
