# M26 serialized Escape during valid KIZ validation on product P 7f493b4

This run used exact product and runtime SHA `7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc`. The immutable runtime checkout supplied React, real API handlers, and WMS Print Direct; all product paths were verified equal to P in `native/source-identity.json`. The API used a dedicated synthetic PostgreSQL database. The actual Print Direct HTTP handler and its idempotency ledger remained enabled; only `Printer.submit` was replaced by an emulator that stores PNG bytes and returns receipts. No external marketplace call or physical printer was involved.

The runner selected order A by its persisted sticker barcode, scanned A's exact available full CIS, and held the real HTTP 200 validation response before delivering it to React. Focus stayed naturally in the unified KIZ scan field. A single Escape while the response was held generated no cancellation request. After the unchanged response was released, the application committed the exact A/CIS binding, submitted one QR request through the real handler, and packed A. It then accepted B's persisted order-sticker barcode as the next selection with no visible error. The handler receipt delta was one (one QR); the receipt, original fixture PNG, and request payload decode to `*WMS666-FINAL-ORDER-A` and have the same SHA256. The database shows A's marking/code association and A packed, with stock unchanged; the consumed A pool code is applied and the other three remain available. The commit response was `wb_pending_confirmation` because this synthetic path intentionally did not wait for or call Wildberries; the UI still completed packing and the bound marking is status `unknown`. This is not evidence of a live WB acknowledgement.

The first runner attempt in sibling `../run-7f493b4-m26-fifo-escape/` reached the native receipt, then failed its local assertion because it searched snapshot key `markings[].value` (the API schema uses `cis`) and stopped waiting on the first receipt before packing and UI quiescence. A read-only post-run snapshot proved A's exact current marking and packed state. That raw attempt is preserved as a harness failure, not a product failure. Rerun `r2` fixes only the field lookup and waits for the exact binding, packed state, expected receipt delta, neutral row, no UI error, and API idle before it asserts. The business expectations are unchanged.

`native/result.json`, `after-response-release.json`, `api-events.json`, and `native-output-join.json` retain the assertions and raw boundary evidence. The join links the physical scan ID to the handler request key and receipt, and independently decodes the source sticker image, request PNG, and saved sink PNG.

Run command, from the proof checkout, with the exact P services active:

```sh
WMS666_PRODUCT_SHA=7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc \
WMS666_RUNTIME_SHA=7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc \
WMS666_BACKEND=http://127.0.0.1:16692 \
WMS666_ORIGIN=http://127.0.0.1:16696 \
WMS666_PRINT_ORIGIN=http://127.0.0.1:17843 \
WMS666_CDP_PORT=16697 \
node docs/evidence/WMS-666/native-print-proof-2026-10-08/run_m26_fifo_escape_7f493b4_r2.mjs
```
