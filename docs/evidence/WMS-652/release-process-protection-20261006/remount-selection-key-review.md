# WMS-652: remount selection-key finding closure

Auditor B, Astra high. Reviewed only the requested delta: test source `8e501fcb969ad0ceb482e479f69fd37f726862ca`, evidence `1ee73adb1016ea2f9c9ce843aa4938dbd3722ef6`, integration checkpoint `6a6c5e4f3`. No product/test edits, browser execution or broad CI rerun was performed. This closes the specific finding in `critical-browser-delta-review.md`; it does not certify the independent anchor, scope enforcement or final full CI.

**Finding closed.** The new assertions in `frontend/tests-e2e/wms652-critical/browser.mjs:393–404` check precisely the previously missing upstream identity. They filter explicit selection POSTs for `wb-a-order`, require exactly the initial and restored request, require both `idempotency_key` values to be nonempty strings, compare them for equality, and independently require the same actual endpoint/supply, order ID and technical sticker `*DUIkWJJF`. The preceding product-barcode lookup miss is excluded. Existing print-key and pack assertions remain intact, and the permanent case list remains the same 33 IDs.

The new negative control changes the actual saved-selection product branch from `deps.select(raw, saved.key, saved.preferences, saved.orderId)` to `deps.select(raw, crypto.randomUUID(), saved.preferences, saved.orderId)`. It does not change the native print dispatch. Its script requires the three exact remount IDs to fail on the new selection-key assertion, all other 30 cases to pass, then checks the saved HTTP/print traces. Product bytes are restored in `finally` and checked against the original bytes.

I independently parsed the saved RED and restored GREEN results and all six corresponding remount trace files, rather than relying on the summary flag in `mutation-proof.json`. The checks established:

| Evidence | Verified result |
|---|---|
| RED result | Exact ordered 33 IDs; only the three `remount-after-lost-ack` cases fail; all three fail on `restored explicit selection must reuse initial idempotency key` |
| Each RED remount trace | Exactly two explicit selections for the same supply/order/sticker; both keys nonempty and unequal |
| Each restored GREEN remount trace | Exactly the same two explicit selections; both keys nonempty and equal |
| Print trace in both RED and GREEN | Keys remain `scan-wb-a-order`, `scan-wb-a-order`, `scan-wb-next-order`; accepted unique intents remain first and next order |
| Pack trace in both RED and GREEN | Correct first and next order both packed; the failure is not caused by an unrelated print/pack/setup error |
| Restored result | All exact 33 IDs PASS; source SHA exactly `8e501fcb969ad0ceb482e479f69fd37f726862ca` |
| Mutation result | Source SHA exactly the same `8e501fcb969ad0ceb482e479f69fd37f726862ca` |

Git comparison confirms all ten files under `frontend/tests-e2e/wms652-critical/` are byte-identical from source to evidence commit and from source to integrated checkpoint `6a6c5e4f3`. Product source has no diff between the source and evidence commits. The added tenth file is the evidence-only mutation helper; it does not add a baseline case. Checkpoint5 in the evidence README describes the distinction between selection and print keys accurately.

The synthetic API still returns a stable order-derived scan ID, but it can no longer conceal this specific browser request-key regression: the assertion reads the actual outgoing selection requests before interpreting the synthetic response. This is the intended boundary closure. It does not establish real server ownership/deduplication semantics beyond the separate backend contracts, native-agent durability, physical printing, or recovery under every print-setting combination. The three remount cases remain QR-only across the three existing entry forms.

Conclusion: the narrowly requested assertion and negative control are meaningful and preserve the original business expectations. No new finding in this delta. The remount selection-key review condition is satisfied; whole-release readiness remains blocked by the separate gates reported by the leading agent.
