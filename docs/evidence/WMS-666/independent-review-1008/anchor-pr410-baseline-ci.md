# WMS-666: PR410 baseline CI classification

Independent bounded review; no main mutation or check bypass.

PR410 head `07de4ce6e67c6e0c64ca9c9c49186f5f7d186281` against main `ac6c92bb5c8bd346a748690d868185c3eab397ed` changes only `scripts/ci/process_bootstrap.json`: source39d becomes S1 e654; basea5 stays unchanged. Application, test and workflow trees are identical to main. This is causal source equivalence, not a separately executed baseline run.

Run `37726946264`, e2e job `113147176264` completed with 131 passed, 7 skipped, 10 failed. Independently read the completed failed-job log with `gh run view 37726946264 --job 113147176264 --log-failed`.

The failures are application/test mismatches in the unchanged main snapshot: two access-denied wording expectations, old product-table column/text expectations, stock-publication status, CHZ icon count, and a report assertion. These do not execute the changed bootstrap pin. Their product correctness is outside this bounded metadata review; they remain failed checks, not accepted or repaired by this classification.

Exact failed case inventory:

```text
1) [chromium] › tests-e2e/auth-dual-portal-sessions.spec.ts:108:1 › FF admin and staff opening /seller/products see human access denied
2) [chromium] › tests-e2e/ff-fbs-stock-sync.spec.ts:26:1 › fbs seller warehouses: row binding, manual sync, status panel
3) [chromium] › tests-e2e/ff-products.spec.ts:10:1 › ff products: catalog separates product fields and hides stock columns
4) [chromium] › tests-e2e/ff-products.spec.ts:143:1 › ff products: marking icon shows count and opens honest sign product card
5) [chromium] › tests-e2e/ff-products.spec.ts:274:1 › ff products: import tz xlsx creates catalog products with packaging
6) [chromium] › tests-e2e/ff-reception-sorting.spec.ts:238:1 › ff verify posts to sorting zone; sorting queue and product columns
7) [chromium] › tests-e2e/ff-reports.spec.ts:14:1 › FF reports: section opens and shows movement summary for a product with intake
8) [chromium] › tests-e2e/ff-staff-users.spec.ts:83:1 › ff staff rights: four compact work blocks pass UI and direct-route gates
9) [chromium] › tests-e2e/seller-available-stock.spec.ts:11:1 › seller products table and next MP picker show current stock after MP plan
10) [chromium] › tests-e2e/seller-stock-directions.spec.ts:11:1 › seller creates, edits and deletes stock directions with compact FBS publication controls
10 failed
7 skipped
131 passed (18.4m)
```

PR-quality also failed because the body lacked the required Product gate section; body correction is owned by release. Backend lint failure and its baseline classification are separately owned by release. No assertion that PR410 CI is green. Anchor merge remains held: new initializer/reopen defects require P2/R2/S2 and an updated exact pin, followed by applicable checks and explicit owner main-merge authorization.
