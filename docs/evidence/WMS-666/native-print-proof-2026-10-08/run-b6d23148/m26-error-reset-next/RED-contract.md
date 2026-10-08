# M26: invalid KIZ error visibility and recovery

This is the frozen pre-fix browser contract for the ordinary unified packing row.
It was exercised against product/runtime commit `b6d23148f1571d08d13d83c6179c385e2f6a1efc`.
The product source checkout was clean at that commit; the browser used the ordinary
React row input and the real isolated WMS API, with the print handler's receipt
endpoint available for the no-print check.

Run with the exact product and runtime pins required by the runner:

```sh
WMS666_PRODUCT_SHA=b6d23148f1571d08d13d83c6179c385e2f6a1efc \
WMS666_RUNTIME_SHA=b6d23148f1571d08d13d83c6179c385e2f6a1efc \
node docs/evidence/WMS-666/native-print-proof-2026-10-08/run_m26_error_reset_next_b6.mjs
```

The isolated services were API `127.0.0.1:16692`, UI `127.0.0.1:16696`, native
handler `127.0.0.1:17843`, and Chrome DevTools `16697`. The synthetic database was
seeded only for this run. The seed tuple is in `seed-public.json`; it contains no
authorization headers.

The first half of the contract was reached on the baseline: scan A's persisted QR
barcode, focus A's ordinary row KIZ input, enter `NOT-A-VALID-CIS-WMS666`, and
press Enter. The browser sent one `POST /operations/fbs-orders/kiz/validate` for
the exact A order and exact value. The API returned HTTP 400, code `not_a_kiz`.
The full request and response are in `native/api-events.json`.

Before the first failure, the row was visibly selected as A. After the real 400,
the same row remained selected, but neither the unified scan bar nor the active
row displayed a visible error. The operator-facing predicate timed out. The
pool codes, markings, and stock, and the handler accepted no new print job. The
captured DOM and exact failure are in `native/failure.json`; the selected-A
screen capture is `native/ui-A-selected.png`.

The executed baseline runner's Git blob was `75f2d4fb1abbf6c62dd39837c583cbb387d748d9`.
The published runner has since been tightened to count and match the one exact
validation request before testing visible-error recovery, and to look only at a
visible active-row or unified-bar message. Reviewer follow-up also corrected the
active-row and neutral product-barcode predicates. The current runner blob is
`ea025652f7831d8f9ac6970970c0a34c7d7188ee`; it was not rerun on the baseline.
The captured API and database records independently satisfy its pre-error
guards. The post-fix run must execute the published runner as-is.

The frozen success contract after the UI fix is: show a visible semantic error
in the active unified scanner or active row; do not commit a KIZ or dispatch a
print; Escape cancels the active selection and releases the same page to its
neutral order-QR scanner; scanning B then selects B with no stale A error or
target and no unintended print. The baseline run stopped at the first failed
visibility assertion, so Escape and B remain post-fix checks, not baseline passes.

The DOM-unit draft did not produce a test result: Vitest failed with `ENOSPC`
before collecting any tests. It is not part of this frozen contract and is not
reported as a RED. This contract is the executed exact-P browser reproduction.
