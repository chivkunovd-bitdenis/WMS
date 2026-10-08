# C13 trusted history pin contract

The checker accepts a reviewed history cutoff only from the external `origin/main` Git blob `scripts/ci/process_bootstrap.json`. The pin must be a regular `100644` blob, contain exactly two unique keys (`base_sha`, `source_sha`) with distinct lowercase 40-character SHA values, and satisfy `WMS-666 contract → base → source → HEAD`. With no `origin/main` ref it performs the full legacy history walk; if the ref exists but the blob, schema, or ancestry is invalid, it fails closed. A valid boundary skips only commits through `source`; later committed, staged, unstaged, and untracked changes are still checked.

Focused synthetic checks passed on the current test code:

```text
npx vitest run src/screens/v2/wms666ChangeScope.test.ts -t 'uses only an externally pinned source ancestor|fails closed when origin/main' --maxWorkers=1 --minWorkers=1 --no-file-parallelism --no-cache
Test Files  1 passed (1)
Tests       3 passed | 12 skipped (15)
```

The cases verify a matching ancestry pin still catches a later forbidden backend edit, rejects a valid-looking pin whose source is outside the checked-out lineage, and rejects malformed/duplicate-key JSON.

The focused live-checkout guard remains intentionally red until the external pin is advanced to an independently accepted source on this checkout's ancestry. Current trusted origin values are `base_sha=a5df04f1560de0eaaf855199065936cb22a222b1` and `source_sha=39d1afdc8f37cdfda3c7768804ccccc3c9ad4e6e`; the latter is not an ancestor of current `HEAD=2211542d2dcb1ddf9b49c961e94aa4f5640e48c3`. The run therefore failed closed exactly at the ancestry check:

```text
npx vitest run src/screens/v2/wms666ChangeScope.test.ts -t 'keeps the actual task diff' --maxWorkers=1 --minWorkers=1 --no-file-parallelism --no-cache
1 failed | 14 skipped (15)
Command failed: git merge-base --is-ancestor 39d1afdc8f37cdfda3c7768804ccccc3c9ad4e6e 2211542d2dcb1ddf9b49c961e94aa4f5640e48c3
```

This is a guard-boundary failure, not product acceptance: no fallback to an empty diff occurred. The restored exact-triple fixture is `frontend/tests/fixtures/wms666AcceptedRecoveryHistory.json`, Git blob `3bdf3ca0501a44284fb08cf74662ac4035144c23`, matching the independently trusted 39d tree.
