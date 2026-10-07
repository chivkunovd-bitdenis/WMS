# WMS-684/586: scope-contract repair evidence

The failed CI shard `37544293789`, case `test_task_sources_and_lane_boundaries_preserved`, compared the whole mixed integration branch with `4b298ef…` and reported 69 foreign paths. Its raw log is `/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/pr393-backend-shard1-c3.log`.

The replacement follows the accepted WMS-653 pattern. Starting at the frozen WMS-684/586 contract `1943e0f18a51e83a45a647f51fb565f2fab6d074`, it walks only the ancestry commits whose subject begins `WMS-684:` or `WMS-586:` (including the combined-task form). It accepts only the task's four product paths, task tests/documents and its dated review-evidence prefix. A foreign commit, even when merged into the integration branch, is not attributed to WMS-684/586. A forbidden path in a commit titled WMS-684/586 fails.

The targeted test created isolated temporary Git repositories for both cases:

1. A WMS-680 migration is committed on a foreign branch, a permitted WMS-684/586 service change is committed on a task branch, then the foreign branch is merged. The scope passes.
2. A WMS-684/586 commit adds `backend/app/models/forbidden.py`. The scope raises `WMS-684/586 changed foreign files`.

The protected waybill, inbound handlers, task-source wording and historical requirements checks remain. Waybill/handler equality is now checked before and after each matching WMS-684/586 commit (and against a merge parent when a merge supplies its own resolution), rather than against unrelated changes that arrive later in integration.

Sequential verification used the existing runtime only:

```text
cd backend && PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m ruff check tests/test_wms684_586_scope_contract.py
cd backend && PYTHONDONTWRITEBYTECODE=1 /Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m pytest -n0 -p no:cacheprovider tests/test_wms684_586_scope_contract.py -q --tb=short
```

Result: Ruff passed; pytest passed **4** tests. The complete output is `wms684586-scope-task-history.log` alongside this file.

The immutable test-only commit is `6da0eb63b143d71d789c25a20ee04e3c49cbf14b`. The same four-test command was rerun on that exact SHA; its output is `wms684586-scope-6da0eb63.log`. No push was made: the integration coordinator batches publication.

For independent review, full immutable before/after blobs of the two task commits that changed `FfInboundRequestView.tsx` are retained alongside this file:

- `wms684586-view-before-371e18f97.tsx` and `wms684586-view-after-371e18f97.tsx`;
- `wms684586-view-before-b5f2a6cfb.tsx` and `wms684586-view-after-b5f2a6cfb.tsx`;
- `wms684586-scope-owned-history.tsv` records every matching task commit examined.

Their SHA-256 values, in this order, are `9438214d609d67fdacb9cf5a64dbbf3f2fd96b3b8c262753a3cdba74e793e9d3`, `20caaf9e37897f2116038534e2d7959df6af0be5889514b784898fb55251dd59`, `20caaf9e37897f2116038534e2d7959df6af0be5889514b784898fb55251dd59`, `e4b3772f3915e40510e98b73552fc087e4d7721b3a998fe556c4baa2b5758c3a`, and `020e2293caad8d9f5a3c31ea6a9735e35e787d1e0b35cf8542e8021bc590de23`.
