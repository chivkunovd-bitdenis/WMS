# Preserved M26 FIFO failure on pre-fix product P c1e394325

This is the raw pre-fix M26 FIFO reproduction on product/runtime SHA `c1e394325ef62c5b5508786f461cd20c1edd69f9`; it is retained to show why the Escape queue fix was made and is not current acceptance evidence. The runner held the actual successful KIZ validation HTTP 200 before React received it, then sent Escape with focus naturally in the unified scan field. The real API received a cancel request for the same scan while the validation response was held. After releasing the unchanged response, commit returned `scan_selection_cancelled`; no current marking, native receipt, or packing mutation was produced. This is a preserved RED baseline.

The source/runtime identity and all raw focus, held-response, cancellation, API, database and screen evidence are under `native/`. The test ran only on the synthetic audit fixture; no marketplace or physical-printer call was made.
