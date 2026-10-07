# WMS-684: durable print harness evidence for f614

This evidence accompanies test-only commit
`0b5cde29ed11b2ae8a71b5c8040fbff0609b9d00`. It changes neither the inbound
screen nor the print utility.

The Linux CI record is
`/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/integration/frontend-f614.log`.
It reported eleven WMS-684 failures: nine DOM-contract failures and two real
PDF-contract failures. The visible symptoms were zero `markCalls`, stale seller
and receipt date in captured HTML, errors not yet rendered, and a missing next
print dialog.

The cause is in the fixture, rather than the screen. Its `print()` method used
two microtasks after clicking confirmation. Production first waits for iframe
`onload`, decodes the barcode images, waits its 100 ms print handoff timer, runs
`beforeTransfer`, resolves the awaited transfer, and only then sends the mark
POSTs. jsdom also does not navigate `iframe.srcdoc` by itself. As a result the
fixture returned before the operation existed.

The dedicated WMS-684 harness now uses the existing platform-only adapter from
`frontend/tests-e2e/wms672-dom.test.tsx`: it writes the utility's own `srcdoc`,
supplies only jsdom's absent image-decode and native-print boundaries, and calls
the production `onload` handler. It does not replace `printBarcodeLabels`, does
not invoke `beforeTransfer` itself, and leaves the utility's decode, delayed
handoff, durable save, and HTTP sequence intact. The fixture now waits for an
actual frame or recovery read and then for the completed transfer plus terminal
refresh/error with the action no longer busy.

The new real handoff also exposed an invalid old fixture token: `contract` could
not be parsed by the existing durable-attempt storage key once `beforeTransfer`
ran. The harness now supplies a synthetic public tenant/user payload, matching
the established WMS-672 setup. No credential is used.

The preserved negative cases now distinguish the two real outcomes. A 503 mark
response remains eligible for one explicit recovery POST. A lost response after
the mock server has committed its mark is reconciled without a second POST or a
second iframe; the next document still prints and marks normally. Thus the tests
retain the no-automatic-reprint guarantee instead of treating a committed mark
as missing.

Targeted sequential verification used the existing dependencies only:

```text
cd frontend && npx eslint src/test-contracts/inbound684586Harness.tsx src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx
cd frontend && npx vitest run --no-cache --maxWorkers=1 --no-file-parallelism src/screens/ff/FfInboundRequestView.wms684.dom.test.tsx
cd frontend && npx vitest run --no-cache --maxWorkers=1 --no-file-parallelism src/screens/ff/FfInboundRequestView.wms684.pdf.test.tsx
```

ESLint passed. The DOM contract passed **11/11**, including HTTP and lost-response
failure paths. The real Chromium PDF contract passed **2/2**: every selected
stock in single and bulk paths retained dimensions, seller/receipt metadata and
the original decoded Code 128 barcode. Full outputs are retained in
`.agent-runs/wms684-dom-harness-green.log` and
`.agent-runs/wms684-pdf-harness-green.log`.
