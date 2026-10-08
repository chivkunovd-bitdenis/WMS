# M26: invalid row KIZ, Escape recovery, and next order selection

This bounded browser run used product/runtime SHA `c1e394325ef62c5b5508786f461cd20c1edd69f9`. The runtime checkout was pinned to that commit and its `backend/app`, `frontend/src`, and `tools/print-agent` trees matched it. The current-P source manifest is in `native/source-identity.json`.

The run used the synthetic PostgreSQL fixture and the actual WMS API handlers. The only printer substitution was the emulated `Printer.submit` sink; the WMS Print Direct HTTP handler, idempotency logic, and receipts remained active. No marketplace request or physical paper was involved. Seed identities and the synthetic sticker barcode-to-PNG hashes are in `seed-public.json`.

The browser read the persisted sticker barcode for order A and selected A. Entering `NOT-A-VALID-CIS-WMS666` in A's row field made one real `/operations/fbs-orders/kiz/validate` request for A; it returned HTTP 400 `not_a_kiz`. The unified packing bar displayed the validation error. Before/after snapshots show unchanged pool codes, markings, and stock, and the print handler accepted zero PNG jobs.

The runner exercised the two documented Escape stages separately. With the row KIZ input focused, the first Escape moved focus from that input to `BODY`, left A selected and the error visible, and sent no cancellation request. A second Escape outside the field released the same A scan, cleared the error and active row, and returned the scanner to product-barcode mode. The frontend issued two identical cancel requests for the same scan ID; both returned 204. The API cancel path is idempotent for the already-released scan, and the subsequent database snapshots show no extra mutation. The persisted sticker barcode for B then selected B with no stale A error or target. Pool, marking, and stock snapshots remained unchanged, and the print handler still had zero receipts.

The first c1 attempt is preserved in sibling `run-c1e394325-m26-error-reset-next/`; it stopped after its Escape wait timed out because it expected the row-focused Escape to cancel the scan. This follow-up records the actual focus boundary, performs the second Escape outside the field, and tests B selection without changing product expectations.

Run command, from the proof checkout:

```sh
WMS666_PRODUCT_SHA=c1e394325ef62c5b5508786f461cd20c1edd69f9 \
WMS666_RUNTIME_SHA=c1e394325ef62c5b5508786f461cd20c1edd69f9 \
WMS666_BACKEND=http://127.0.0.1:16692 \
WMS666_ORIGIN=http://127.0.0.1:16696 \
WMS666_PRINT_ORIGIN=http://127.0.0.1:17843 \
WMS666_CDP_PORT=16697 \
node docs/evidence/WMS-666/native-print-proof-2026-10-08/run_m26_error_reset_next_c1e394325_r2.mjs
```

The runner's exact request log, UI and database snapshots, screenshots, and handler status are retained under `native/`. This run validates only the row-error and Escape/next-order recovery segment; it does not replace the wider WMS-666 acceptance matrix.
