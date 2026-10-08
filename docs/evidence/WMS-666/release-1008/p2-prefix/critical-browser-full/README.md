# Current P2 critical browser runner

The unchanged full `frontend/tests-e2e/wms652-critical/browser.mjs` ran all 43 IDs in `cases.json` against the P2 source `1a4b0d687392a91a2dbfde6fbcfe9013b9e09075`: 43 passed, 0 failed. The report includes single and grouped QR scans, manual reprint variants, held receipt, lost accepted acknowledgement, remount recovery, selection/create/retry, and layout cases. The runner's `blocked` and `Runtime.exceptionThrown` arrays are empty in each saved case artifact, and the transport log contains no `event-handler-error` entries.

The runner exercises the real screen in Chromium but fulfills API requests with its synthetic fixture; its print acceptance is an emulated browser capture. It does not replace the S/G runs under `../ordinary-r3/` and `../group-r2/`, which used isolated PostgreSQL and forwarded print jobs to the actual local Direct Handler. Physical paper was not tested.

Command from the release checkout:

```sh
WMS652_EVIDENCE="$PWD/docs/evidence/WMS-666/release-1008/p2-prefix/critical-browser-full" node frontend/tests-e2e/wms652-critical/browser.mjs
```

The Vite dev server was served at `http://127.0.0.1:16686/` from the P2 checkout using `frontend/tests-e2e/wms652-critical/vite.config.ts`.

At shutdown, Vite stdout showed React prop warnings and an ErrorBoundary report naming `FbsPrintPreviewDialog`. The command output was not persisted, so the exact exception text and triggering case are unavailable. The runner does not subscribe to `Runtime.consoleAPICalled`; its empty error arrays establish only that no captured runtime exception, interception error, or blocked request occurred. No product defect is inferred from that stdout alone.
