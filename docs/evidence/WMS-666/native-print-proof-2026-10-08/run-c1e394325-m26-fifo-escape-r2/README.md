# M26 FIFO regression: Escape must not overtake an accepted KIZ scan

This run uses product/runtime SHA `c1e394325ef62c5b5508786f461cd20c1edd69f9`. Its source manifest records the exact runtime and source blobs. The test database, orders, and KIZ values are synthetic. The real WMS API processed requests; the browser runner held only the already-completed HTTP 200 response for KIZ validation before delivering that unchanged response to the UI. The WMS Print Direct handler remained active with its emulated PNG sink. No live marketplace request or physical print was involved.

The browser selected order A from its persisted order-sticker barcode, then scanned one available pool KIZ. The real `/operations/fbs-orders/kiz/validate` endpoint returned HTTP 200 for A and the exact CIS stored in `held-validation-response.json`. Before the browser received that response, the operator pressed Escape with the natural unified scan field focused. The application sent `/operations/fbs-supplies/{supply_id}/scan-auto-print/{scan_id}/cancel`; the real API returned 204 while the accepted KIZ scan was still waiting on its validation response.

The runner then released the unchanged HTTP 200 and waited for the actual outcome. The UI attempted to commit the same KIZ against the same scan ID, but the API returned `scan_selection_cancelled` and `newly_bound: false`. The current marking was absent, all four pool codes remained available, order A stayed pending, and the native handler accepted zero print jobs. The UI showed “Не удалось выполнить действие. Обновите данные; если ошибка повторится, обратитесь к администратору.” This demonstrates that Escape canceled an accepted scan before its in-flight validation completed, losing the operator's KIZ input.

The runner freezes the expected recovery path for a fix: while the accepted validation response is held, Escape must not cancel or clear that pending scan; after the same response is released, A's binding, configured QR print, and packing must complete, and the next B sticker must select B without a stale error. The current c1 run fails at the no-early-cancel assertion after saving the post-release API, database, UI, and native-handler state.

The first bounded attempt at the same case is retained in sibling `run-c1e394325-m26-fifo-escape/`. It already showed the held HTTP 200 and the pre-release 204 cancel, but closed the browser immediately after asserting the failure. The `-r2` run adds the response-release outcome and freezes the complete green-path expectations without changing the trigger or product behavior.

Run command, from the proof checkout:

```sh
WMS666_PRODUCT_SHA=c1e394325ef62c5b5508786f461cd20c1edd69f9 \
WMS666_RUNTIME_SHA=c1e394325ef62c5b5508786f461cd20c1edd69f9 \
WMS666_BACKEND=http://127.0.0.1:16692 \
WMS666_ORIGIN=http://127.0.0.1:16696 \
WMS666_PRINT_ORIGIN=http://127.0.0.1:17843 \
WMS666_CDP_PORT=16697 \
node docs/evidence/WMS-666/native-print-proof-2026-10-08/run_m26_fifo_escape_c1e394325.mjs
```

All exact requests and responses, UI/database snapshots, screenshots, receipt counts, and the failed assertion are retained in `native/`. The captured cancellation is a product failure on c1; the post-fix rerun must use the same scan/response/Escape sequence and reach the binding, native receipt, packed order, and subsequent B selection asserted by the runner.
