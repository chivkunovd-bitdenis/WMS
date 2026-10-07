# WMS-666 — independent checkpoint, 08.10.2026

This is an unfinished review checkpoint, not product acceptance or a trusted product reference.
Reviewed source: `da1d6514b4ff036dc93e114b1f1ac86481c2f31d`, product delta from
`212f19d548496fef7baf75c83204b771e304281b`. The integrator subsequently reported
the syntax-only brace correction `2d2fa218485380529bf7988784b6e81afe162368`.
The reviewer independently inspected that one-brace correction too. All 24
runtime paths in `reviewed-runtime-paths.txt` have been inspected. **Checkpoint
verdict: NO-GO.** Neither source is accepted as the final trusted product P.

The reviewer read current origin/etalon AGENTS.md, the complete owner/failure case
libraries, the complete WMS-666 requirements including R1008.1–7, and the product
delta. Product, frozen tests, runtime and native application were not edited.

## Findings returned to developer and independent tester

1. **Partial manual tape loses its error after QR acknowledgement retry.**
   `MarkingPrintDialog.printFbsTape` normally combines server order_errors and
   client build errors, reports omitted orders and returns false before
   onCompleted. A QR acknowledgement failure jumps out before this block.
   Pending state retains only context and remaining acknowledgements. Its retry
   unconditionally calls onPrinted, onCompleted and onClose, so the supply queue
   advances although omitted orders remain. Preserve the same partial-result
   finalization after both ordinary acknowledgement and ack-only recovery.
   One dispatch and stable acknowledgement keys must remain; this does not
   authorize reprinting the successful portion.

2. **A partial HTTP-200 sticker batch has no same-window recovery.**
   The prefetch effect records every requested order in unifiedStickerAttempts.
   With nonempty batch.order_errors it displays an error but does not offer
   Retry, whereas transport rejection creates Retry. Refresh does not clear the
   attempted set. R1008.6 requires partial failure/retry in the mounted workspace.
   Retry must preserve successful stickers and request the still-missing failed
   orders; preparation remains idempotent. UI errors from a delayed retry also
   require the existing supply/open-generation fence, including writes inside
   the retry closure before run() applies its own fence.

3. **Ozon quantity > 1 is incorrectly collapsed to one current KIZ.**
   `fbs_print_binding_service.print_bindings_current` uses newest marking LIMIT 1
   per Ozon order_product_id. An Ozon position legitimately carries multiple
   current markings: existing `test_exemplar_set_carries_every_code_of_the_posting_not_only_the_last`
   seeds quantity=3 with exemplars 81/82/83; existing current_markings is
   quantity-aware, and `_active_ozon_sgtin_markings` emits every printable code.
   Therefore a valid tape with all three codes fails the new dispatch validator
   on older current rows. Preserve quantity/exemplar identity and reject retired
   generations without importing delivery-readiness or provider-ack gates into
   printing local/pending valid codes.

## Independent preliminary native evidence check

The reviewer independently decoded all six stored 28a799 sink PNGs, compared each
PNG byte-for-byte with every corresponding real HTTP payload, and queried the
SQLite ledger read-only. Six distinct keys and receipts match the sink exactly;
the lost QR acknowledgement produced two identical requests but one receipt.
There are two correct order QR payloads and two copies each of two distinct CIS.
The saved before/after stock snapshots are equal. Machine-readable results are
`native-28a-independent-decode.json` and `native-28a-independent-ledger.json`.

This evidence is explicitly preliminary 28a799, not the final product P. The
current final product has changed preparation and manual recovery. Native receipt
is not physical paper or marketplace acceptance. The UI printed count still
requires its existing sticker/application and WB metadata conditions; this
preliminary synthetic fixture does not establish their positive path.

## Remaining review boundary

All three findings require independent RED evidence, implementation and targeted
re-review. Final P has not been frozen. Exact-candidate M01–M43 evidence, the full
ordinary/group bare preparation path, provider accepted/rejected/readback,
manual/native recovery, picking renderer and the required CI remain outstanding.
No product reference or metadata activation is approved by this checkpoint.
The same reviewer session should resume for targeted changes and final proof;
unchanged runtime paths do not require another full audit without new evidence.
