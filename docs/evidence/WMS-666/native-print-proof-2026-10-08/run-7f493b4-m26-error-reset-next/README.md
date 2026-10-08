# M26 invalid KIZ and next-order recovery on product P 7f493b4

This run used exact product and runtime SHA `7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc`. The UI source came from the detached runtime checkout and its `backend/app`, `frontend/src`, and `tools/print-agent` trees matched that P. The synthetic API service used the runtime checkout's Python modules and the dedicated guarded database `wms_test_666_native_print_final_0c44`; the actual WMS Print Direct handler used the same checkout. Only its `Printer.submit` destination was replaced by the PNG-saving emulator.

The persisted A order-sticker barcode selected A. Entering `NOT-A-VALID-CIS-WMS666` caused exactly one real KIZ validation request to return HTTP 400 with `not_a_kiz`, and the error appeared in the active packing UI. No marking or stock changed and the handler accepted no print job. Escape while the row input had focus only left that field; it kept A selected and the error visible. A second Escape from the shared scan field released the same A selection (HTTP 204, idempotent for the already-released scan) and returned the screen to product-barcode mode. The persisted B sticker then selected B with no stale error and no print dispatch. The full request chronology, database snapshots, screen captures, and zero-receipt handler state are in `native/`.

This evidence covers only the M26 invalid-input/recovery segment. The synthetic test provider does not contact Wildberries; no live marketplace acknowledgement or physical paper is claimed.

Run command, from the proof checkout, with the exact P services active:

```sh
WMS666_PRODUCT_SHA=7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc \
WMS666_RUNTIME_SHA=7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc \
WMS666_BACKEND=http://127.0.0.1:16692 \
WMS666_ORIGIN=http://127.0.0.1:16696 \
WMS666_PRINT_ORIGIN=http://127.0.0.1:17843 \
WMS666_CDP_PORT=16697 \
node docs/evidence/WMS-666/native-print-proof-2026-10-08/run_m26_error_reset_next_7f493b4.mjs
```
