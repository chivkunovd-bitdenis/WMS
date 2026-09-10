# WMS-325 — SAFE: concurrent invoice cancellation audit

Bounded P2 correction, authored and tested on 2026-09-10. This is not acceptance of the billing/settings slice, all WMS-325, or a release.

Source commit: **`89a86643fb9e6c2dbcdc236c4642c0d9596e2273`**, parent **`14f36a0dc1c6d62d3c77bad184fd42eb9cf2f12e`**, branch `feat/wms056-audit-trail`. The worktree was clean at entry. The coordinator's full `resumed/review325-settings-billing-final-result.md` finding was read. No coordinator code was imported. Per the owner's task, the earlier billing delta still awaits coordinator integration.

## Correction and transaction boundary

Only `billing_invoice_service.py`, `billing_invoice_v2_service.py`, and the new focused test change production/test behavior. Both cancellation paths now read the tenant-filtered invoice under PostgreSQL `FOR NO KEY UPDATE` before taking the audit snapshot. The lock lasts through the caller's existing commit or rollback. `populate_existing=True` replaces an already cached ORM object with the row returned after any lock wait.

After a first commit, the second caller sees `cancelled`; the existing equal-before/after helper skips a duplicate. After a first rollback, the second sees `issued` and records the sole committed transition under its authenticated actor. The V2 getter's new optional lock is enabled only by cancellation; ordinary reads retain their previous behavior. Missing-invoice errors and tenant predicates remain in place.

Existing invoice-creation paths use Seller locks; this correction acquires only the existing invoice row lock and introduces no Seller lock. No NOWAIT, navigation gate, or history permission gate was added. The existing actor helper, immutable actor snapshot, savepoints, audit fail-soft behavior, API permissions, status assignment, totals, rates, and financial facts were not changed. There is no new commit inside a service, table, entity, calculation, or financial event.

## Executed evidence

All database runs used a newly initialized, isolated PostgreSQL cluster, synthetic database `wms325_cancel_synthetic`, Unix socket only, port 55469, with synthetic tenants/users/invoices. One pytest process ran at a time. During each race exactly two distinct PostgreSQL backend PIDs were used; the lock holder itself queried `pg_blocking_pids` to verify the second connection was waiting. No coordinator fixture or customer data was used.

- **Frozen baseline: 2 passed in 5.56s.** `baseline_probe.py` loads only the cancellation functions (and V2 getter) from Git `14f36a0d` into the unchanged current service dependencies. Two overlapping, uncommitted cancellations on separate PostgreSQL connections produce **two** persisted `issued → cancelled` events with distinct actors, for both legacy and V2. This reproduces the finding without replacing worktree files. It is a frozen-function probe, not a checkout-wide old-version test.
- **Fixed scoped suite: 8 passed in 37.17s.** Six new tests plus two existing invoice audit tests. Four new cases send real authenticated HTTP requests through each cancellation API. With two successful requests both return 200, the invoice is cancelled and exactly one event survives. With the first transaction explicitly flushed and then rolled back, the first request returns the expected synthetic 500 and the second returns 200; the sole event has the second actor's ID and immutable name snapshot. Both the first status update and audit insertion have reached PostgreSQL before that rollback. The second session retains a strong reference to an old `issued` object, verifying the identity-map refresh. The other two new cases check missing invoices do not create history.
- The concurrency tests also assert unchanged invoice amounts, unchanged V2 issuer, and zero ledger entries/operation facts. Existing targeted tests retain sequential create/retry/cancel behavior for both versions.
- **Ruff: passed** on both services, the new test, and the baseline probe.
- **Mypy: passed, 4 source files**, with `--follow-imports=silent`, on those same files.
- **`git diff --check`: passed.** Test warnings: five existing SWIG type deprecation warnings; no test failures or skips in the fixed run.

Reproduction commands, from `backend`, using the project virtualenv and an explicitly supplied isolated `WMS_TEST_DATABASE_URL`:

```sh
pytest -q tests/test_wms325_invoice_cancel_concurrency.py \
  tests/test_wms325_settings_billing_mutations.py::test_invoice_v2_create_retry_and_distinct_cancel_actor_without_manual_text \
  tests/test_wms325_settings_billing_mutations.py::test_legacy_invoice_create_retry_cancel_and_amount_unchanged --tb=short

# PYTHONPATH must include this backend directory for the external evidence probe.
pytest -c pyproject.toml -p tests.conftest -q \
  ../docs/reviews/artifacts/wms325-invoice-cancel-concurrency-20260910/baseline_probe.py --tb=short

mypy --follow-imports=silent app/services/billing_invoice_service.py \
  app/services/billing_invoice_v2_service.py tests/test_wms325_invoice_cancel_concurrency.py \
  ../docs/reviews/artifacts/wms325-invoice-cancel-concurrency-20260910/baseline_probe.py
```

The adjacent `fixed-tests.txt` and `baseline-tests.txt` preserve the actual pytest summaries. The PostgreSQL-only regression explicitly skips non-PostgreSQL environments because another database does not establish row-lock correctness. After the runs, the own PostgreSQL server was stopped successfully and its synthetic cluster moved to Trash.

## Remaining scope

This closes only the reproduced double-cancellation audit gap at the code/test level. Independent acceptance and coordinator cherry-pick remain separate. No full suite, CI, browser, merge, or deployment was performed. Other WMS-325 gaps and prior billing/settings/inbound acceptance remain outside this patch. No frozen inbound/MP/print code or prior reports were changed; no stock, packaging, mobile, WMS-111/112, WMS-418, secret, payment gateway, or customer-data work was performed. No child agents were launched.
