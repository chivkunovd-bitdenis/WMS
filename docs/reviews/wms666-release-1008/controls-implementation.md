# WMS-666: implementation handoff for shared packing actions

Product commit: `10c824576c370a4f29c1c8a850519eab090d6233`.
Branch: `codex/wms666-packing-controls-fix`, pushed to origin.

The shared React toolbar composes the existing per-supply selection and handlers.
It is used in ordinary supply packing and the assembly entry. Selected/all print
scope uses the existing tape order, opens each supply's existing print constructor,
and advances only after its complete-print acknowledgement and close. Partial
failure does not advance; cancel stops the remaining batch. Reload/navigation does
not resume a batch. Selection remains unchanged.

The WB check includes all eligible WB supplies regardless of selected rows. The
named supply menu preserves pack-all/skip scope and that supply's selected
clear/transfer scope. Ozon uses the same accurate selected/all label, without
changing tape order IDs, position data, product labels, or its disabled QR setting.
Printed and packed totals remain separate. Rows, columns, scanning, picking sheets,
stock, and print transport were not changed in this commit.

Dependencies: independent test contract `c3f5986968e7e5f9f9c5c1cd96f2d807210a497b`
(cherry-pick `7ecab5920`); complete-print callback from print developer
`e86a2ed71` (cherry-pick `0bc54cc51`). Integrator should cherry-pick only product
commit above if those dependencies are already present.

## Local checks

- `node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.app.json`: PASS.
- From frontend, `node node_modules/vitest/vitest.mjs run src/screens/v2/FbsScanPrintToggles.dom.test.tsx src/components/MarkingPrintDialog.test.ts src/components/MarkingPrintDialog.confirmOrder.test.ts --maxWorkers=1 --no-file-parallelism`: 21/21 PASS, 6.19 s.
- `git diff --check`: PASS before commit.
- Approved localhost React mockup inspected with CUA before implementation, including
  shared toolbar, existing rows, long names and named supply menu.

The combined full-card DOM run (UnifiedPacking/StickerPrefetch/Toggles), then an
isolated UnifiedPacking single-supply case were interrupted without verdict after
remaining active without a result. Integrator reports the same known full-card
DOM hang on the baseline; this is not counted as PASS or a proved new regression.
Narrow DOM tests above complete. Actual Chrome/Vite + isolated API/PG contracts
for the new product are delegated to the independent integrator.

A production build, independent review, integrated browser acceptance, complete CI,
and deployment are not claimed by this handoff. Reuse of installed dependencies
avoided npm installation. The local worktree excludes committed docs/evidence via
sparse checkout to reduce disk usage; all source evidence remains in Git.
