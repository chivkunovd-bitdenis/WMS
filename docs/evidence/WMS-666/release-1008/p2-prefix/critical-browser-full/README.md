# Current P2 critical browser runner

The full runner executed all 43 IDs in `cases.json` against P2 source `1a4b0d687392a91a2dbfde6fbcfe9013b9e09075`: 43 passed, 0 failed. The executed runner bytes are preserved here as `browser.mjs.executed-43.mjs` (SHA-256 `03ad6d55d1a8ec0e2d038a7ae0380689e8aaad82032d1ae1dbbc80092489d12a`). Its case IDs and assertions were unchanged, while its working-tree harness also contained separately reviewed CDP cancellation instrumentation; the committed P2 copy of `browser.mjs` was not the byte-identical executed file. The report includes single and grouped QR scans, manual reprint variants, held receipt, lost accepted acknowledgement, remount recovery, selection/create/retry, and layout cases. The runner's `blocked` and `Runtime.exceptionThrown` arrays are empty in each saved case artifact, and the transport log contains no `event-handler-error` entries.

The runner exercises the real screen in Chromium but fulfills API requests with its synthetic fixture; its print acceptance is an emulated browser capture. It does not replace the S/G runs under `../ordinary-r3/` and `../group-r2/`, which used isolated PostgreSQL and forwarded print jobs to the actual local Direct Handler. Physical paper was not tested.

Command from the release checkout:

```sh
WMS652_EVIDENCE="$PWD/docs/evidence/WMS-666/release-1008/p2-prefix/critical-browser-full" node frontend/tests-e2e/wms652-critical/browser.mjs
```

The Vite dev server was served at `http://127.0.0.1:16686/` from the P2 checkout using `frontend/tests-e2e/wms652-critical/vite.config.ts`.

At shutdown, Vite stdout showed React prop warnings and an ErrorBoundary report naming `FbsPrintPreviewDialog`. The command output was not persisted, so the exact exception text and triggering case are unavailable. Source inspection found that the runner's `/print-assets` fixture used `items/total/errors`, while the frontend's `FbsPrintBatch` contract is `requested/ready/missing/failed/assets/order_errors`; the preview reads `batch.assets`. This was a malformed test fixture, not a product-source change.

The fixture was corrected in the current harness to return the full batch shape. A separate focused preview execution passed as `preview-schema-check/result.json` and `preview-schema-check/preview-valid-fixture.json` using `WMS652_PREVIEW_ONLY=1`; it opened the real preview dialog, loaded the fixture PNG at 126×126 pixels, showed no alert or client error fallback, and recorded the exact batch request/response. Its executed runner is preserved as `browser.mjs.preview-valid-fixture.mjs` (SHA-256 `133dd310726f818cb3b40064d290710e5486e744e86800094ccc98c452ae9787`). After that positive run, the runner was tightened so a caught failing preview case cannot still produce an overall PASS; current `browser.mjs` is SHA-256 `14dcf89d80fba9e98a3e6ad26cb715841adf1e0d82afc2bbdbbdcd81a98aa96c` and passed `node --check`, but that fail-closed reporting-only edit was not rerun. This one-case run does not replace or repeat the 43-case run. Vite also emitted existing React prop and MUI tab-value warnings during the focused run; no general console-clean claim is made.

The full-run error arrays establish only that no captured runtime exception, interception error, or blocked request occurred. No product defect is inferred from the earlier shutdown report.
