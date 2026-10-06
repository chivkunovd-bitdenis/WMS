# WMS-681 C6: correction of the PostgreSQL worker protocol fixture

This evidence describes a test-harness correction only. It does not change the
product, the C6 assertions, the PostgreSQL setup, or the shared loopback WB
boundary.

## Observed CI failure

GitHub Actions run `37543827592`, job `112542949834`, failed on candidate
`b439c6ebcca6ab3588fbedeb366286ed4c79a7d9` and merge candidate
`e05083492cc311f36f370fd16f22f0e9cf89f3a8`.
The retained raw log is
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/pr393-backend-checks-initial.log`.

The named CI error was:

```text
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

It happened in the first `launch()` call, at `_line()` / `json.loads(raw)`,
before either worker reached the PostgreSQL lock or WB barriers. The immediately
preceding raw line was the import diagnostic:

```text
warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.
```

Therefore this CI RED did not observe the C6 product race; it observed a
fixture protocol collision.

## Immutable fixture binding

The separate test-only correction commit is
`22944029dc7b34ac838797fb7ace755e01b15fe5`; its parent is
`c52828be87526948c0800fd3da0ce63bea382116`.

The full Git blob for
`backend/tests/test_wms681_postgres_recovery.py` at that parent is
`9c3a3af602eb54ea2609bcc0c03aaed97bcb437a`. The full Git blob in the
test-only commit is `e94e22b697ed4e39cb9754f97153b2aa58f292ce`.

Only the worker stdout protocol changed. In worker mode stdout is redirected
to stderr before application imports, while `_emit_worker_receipt` writes the
two expected JSON-lines receipts through the preserved original stdout handle.
`_line()` now reports a malformed line, EOF, or 30-second timeout explicitly;
it does not skip or reinterpret any of them. A targeted environment-only
startup diagnostic (`WMS681_C6_TEST_STARTUP_DIAGNOSTIC=1`) was used to model
the CI import warning. It is inactive in ordinary runs and no warning filter
or product dependency was changed.

## Local before/after proof

Both commands used the existing isolated localhost PostgreSQL C6 fixture and
ran only the one C6 test with its required two OS subprocess workers.

Before the protocol correction, with the controlled startup diagnostic
enabled, the target failed in 10.21 seconds with the same `JSONDecodeError`.
After the correction, the identical target passed in 15.22 seconds:

```sh
WMS_TEST_DATABASE_URL="$WMS_TEST_DATABASE_URL" \
WMS681_C6_TEST_STARTUP_DIAGNOSTIC=1 \
  /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -q -n 0 \
  backend/tests/test_wms681_postgres_recovery.py::test_wms681_postgres_two_workers_recover_one_group_across_qr_checkpoint \
  --tb=short -o junit_family=legacy
```

The GREEN receipt still proved two OS workers and distinct PostgreSQL backend
connections: OS/PG `70568/70723` and `70762/70883`; `pg_blocking_pids(70883)`
was `[70723]`. The QR boundary was `overlap`, WB create amounts were `[5]`,
and the sticker request history had ten requests (the five physical WB keys
from both workers). The unchanged test assertions also passed for the same
physical keys, one create, five persisted ready assets, and both `200` endpoint
results. Targeted Ruff lint and `git diff --check` passed.

No full suite, installation, product change, production access, or CI rerun is
claimed here. The post-correction green result is a bounded local PostgreSQL
fixture result; the independent fixture reviewer remains responsible for its
review.
