# WMS-652: independent review of the first real-screen browser contract

Auditor B, Astra high. Reviewed frozen test commit `63d19f7061508a1c6afaec21fef95a6c5d3015f2`, integrated checkpoint `6521ed451`. Scope: the six files under `frontend/tests-e2e/wms652-critical/`, their imported product paths, README, restored result/requests, and seven recorded mutation outcomes. No product/test edits, no browser or broad CI rerun, no external/printer activity. The later flags × entry forms, lost acknowledgement, remount and held-receipt work is explicitly outside this review.

The contract is a meaningful improvement and genuinely exercises the mounted production screen. It closes the previously demonstrated hole where disconnecting the real scan bar still passed controller-only guards. It is suitable as an additional mandatory browser contract, with the limits below. It does not alone complete the owner's release gate or prove physical output. Two narrow evidence gaps remain: the exact canonical CIS inside printed copies is not asserted, and one mutation's reported business interpretation is stronger than the actual failure phase.

## Real operator path and fixture boundary

`main.tsx:1–16` imports and mounts the real `FfFbsOrdersScreen` under the normal theme, date and browser-router providers. No alias replaces the scan bar, sequential controller, dialogs, label renderer or direct print code. `vite.config.ts:5–17` only maps `/app/ff/fbs` to this test entry. This bypasses application authentication/bootstrap but retains this screen's own URL parsing and child-screen choices.

`browser.mjs:116–123` focuses the real packing input and uses Chrome DevTools `Input.insertText` plus Enter key events. The text is the technical WB sticker form `*DUIkWJJF`, then full GS1 CIS with group separators, then another technical sticker and CIS. This is a keyboard-wedge scanner simulation; it does not decode a physical printed QR with a camera. Unlike the former isolated widget/controller tests, disconnecting `FbsPackingScanBar`'s actual `routePackingScan` call prevents the lookup and fails all three URL forms.

The fixture deliberately returns product-not-found for a scan without explicit order ID (`browser.mjs:89–99`), and its sticker lookup resolves only matching sticker plus supply (`81–87`). The app must therefore perform the real fallback, send the correct sticker/order pair, bind the correct full CIS, call the native print transport, and pack the correct task/line. This is a legitimate API boundary fixture, not a replacement for the UI/controller. It cannot detect a backend lookup/parser regression: the simulated lookup is independent of backend product code. The existing backend parser and PostgreSQL contracts remain necessary.

The first lookup is held while the next three scanner inputs arrive (`147–155`). Assertions require exactly two explicit selections in order, two exact bind bodies including `scan_auto_print_id` and `scan_no_wb_wait`, six print requests with exact keys and dimensions, correct QR image bytes, and two exact pack requests at the right task/line (`158–184`). FIFO evidence is substantive: first pack precedes lookup of the second QR. The three restored traces independently show this sequence, with six print requests, two pack requests and no recorded page errors/external attempts each.

Print HTTP is intercepted at `127.0.0.1:17843/print` after the real product transport constructs the request (`66–69`). Immediate synthetic receipt prevents real printing. This verifies dispatch through the real printing boundary, including duplicate-job count. It does not exercise the native print agent, its durable deduplication store, uncertain outcomes, or paper. Those are deliberately separate contracts. General page network requests are intercepted before sending; browser-internal background traffic is not claimed to be an OS-level network sandbox.

## Six case IDs and meaningful assertions

| Permanent case ID | Real UI action | What the assertions actually protect |
|---|---|---|
| `WMS652.realQr[supply_id=A]` | Input QR/CIS/next QR/CIS in ordinary supply | Correct fallback/objects, full CIS preservation, one QR plus two copy dispatches per order, FIFO and correct pack body/path |
| `WMS652.realQr[supply_ids=A]` | Same sequence in one-supply assembly entry | Same invariants through that URL form |
| `WMS652.realQr[supply_ids=A,B]` | Same sequence crossing two supplies | Same invariants plus correct second supply/task/line |
| `WMS652.selection[single-create]` | Check actual order rows, open selected popup, close it, open creation dialog, submit | Popup includes selected products and excludes unselected products; preflight/create receive exactly selected IDs; one create POST |
| `WMS652.selection[seller-warehouse-group-retry]` | Check three groups, create, retry one definite refusal | Three seller/WB-warehouse groups; first partial success preserved; exactly four create POSTs total, last only failed group; assembly tasks contain each successful subset once |
| `WMS652.selection[add-existing-refusal-retry]` | Check rows, open actual existing-supply select, choose compatible supply, submit, retry refusal | Only compatible WB option; disabled busy submit does not dispatch again; selected checkboxes survive refusal; two requests retain exact selected IDs |

Selection clicks mostly use the actual DOM element's `.click()` (`browser.mjs:232–306`), so React event handlers and disabled-button behavior run. This does not prove pointer hit-testing, absence of overlays, or visual layout. Fixtures include foreign seller/warehouse/marketplace and closed supplies, which makes the compatible-option assertion meaningful. The grouped test uses real grouping and real dialog state; the fixture only refuses one selected group's first API request.

Selection success assertions stop at the HTTP request/response boundary. The fixture returns empty orders for created supplies and does not remove rows from its worklist. Thus these cases do not establish refreshed post-success composition, selection clearing, or operator navigation after success. Similarly QR workspace fixtures do not persist pack state, so correct pack requests are proved, not the final displayed packed status or quantity. These are limits of the case definitions, not evidence of product defects.

## Findings requiring precise treatment

**F1 — canonical contents of printed CIS copies are not protected by this browser assertion (static coverage gap).** `browser.mjs:173–175` checks that the two copies for one order match, that images differ between orders, and that each PNG is 720×960. It never decodes the DataMatrix or compares it to an independently fixed expected symbol. Product `fbsSequentialPacking.ts:816–825` obtains `claim.kiz` and passes it to `renderCzLabelPng`; the synthetic reprint claim returns predetermined CIS values (`browser.mjs:107–108`). A wrong but different valid CIS per order can satisfy the current image inequality/dimension checks. For example, swapping the CIS values in product handling before rendering is a plausible survivor; that exact mutant was **not executed in this review**, so this is not labelled reproduced.

Minimal contract strengthening: decode the emitted PNG's DataMatrix with an independent decoder and compare the full canonical CIS bytes, including separators, to the known expected CIS for each order. Alternatively use a reviewed frozen oracle independent of the product renderer, not an expected PNG generated by calling that same renderer during the test. Add a targeted wrong-CIS/GTIN mutation that fails on decoded content while retaining correct size, copy count and print keys. The existing exact QR-image check is stronger: it proves that the actual supplied QR asset reaches the print boundary unchanged.

**F2 — `repeat-successful-group` is RED, but not from a demonstrated repeated create request (confirmed by saved evidence).** The mutation replaces `pendingGroups` filtering in `FbsSupplyGroupCreateDialog.tsx:159`. The saved result fails at `browser.mjs:271`, waiting for the button label `Повторить (1)`; the mutation changes its pending count. Its `last-requests.json` has only the initial three create requests and first assembly task. No retry click occurred. Further, `fbsSupplyAssembly.ts:459` independently skips already-created groups, so removing the dialog filter alone does not demonstrate the underlying business duplication.

Keep this as a meaningful incorrect-retry-count/UI negative control, but describe it accurately. To claim a demonstrated duplicate-create detector, deliberately cause a second POST for an already-created group during retry while preserving the expected retry-button label; the existing request-count and exact-group assertions at `browser.mjs:278–282` should then reject it. This is a test-proof improvement, not a request to change product behavior or baseline expectations.

**F3 — the fixture is stateless around claims and completion (accepted boundary, not hidden protection).** All print claims succeed, all print-started calls return started, scan IDs derive from order ID and commits return the submitted CIS. This cannot prove server claim ownership, server idempotency, duplicate protection across remount, denied claim behavior or real receipt recovery. The new browser contract does not claim those in its README; later work and the native/backend contracts must provide them. The preferences are seeded into storage, not changed by clicking checkboxes in this checkpoint. No conclusion about the pending flag-matrix work is drawn here.

## Recorded mutation evidence and provenance

Read and parsed `browser-green-restored/result.json`: exactly six PASS IDs. Read and parsed `browser-mutants/mutations.json`: seven nonzero exits. Inspected restored QR request/print/trace records and the grouped-mutant request record.

| Mutation | Evidence interpretation |
|---|---|
| Disconnect scan input | All three QR entries fail because the input never reaches sticker lookup; directly closes previous real-input gap |
| Skip QR dispatch | All three fail on missing QR keys in the exact six-job sequence |
| Add an unwanted QR dispatch | All three fail on extra `:UNWANTED_DUPLICATE` jobs |
| Select wrong next order | All three fail because second order does not complete; logs show wrong bind/pack object |
| Empty selected IDs on create | Fails on exact create request IDs; API fixture does not silently repair them |
| Include successful groups in pending list | Fails at retry-label/count phase; see F2 |
| Empty selected IDs on add | Fails on exact two add request bodies |

`mutations.py` restores original product bytes in `finally` and checks restoration. The reviewer did not rerun these mutations. The saved restored run identifies pre-test-commit HEAD `bcb2f05769fa7c5a1b2f249b3ed72685a70b8beb`, not `63d19f706` or `6521ed451`. Product-source diff from that HEAD to `63d19f706` is empty, and the six test files have no diff between `63d19f706` and `6521ed451`. This is useful precommit execution evidence but does not replace required CI execution of the final integrated SHA.

The browser runner exits nonzero for thrown selection assertions even though failed selection cases are not appended as explicit FAIL entries; earlier PASS entries remain in JSON. Therefore the mandatory registry must require process success, overall `status=PASS`, and the exact six ID/status pairs, not merely accept the present cases or `every(PASS)` on a shorter list. The leading agent owns the frozen runner/registry and anti-removal checks; this review does not certify that infrastructure.

Conclusion: accept the real-screen contract's actual six-case coverage as valuable and correctly bounded. Do not count F1 as proof of exact canonical copy contents, or F2 as a duplicate-create business mutation proof. The all-flags/uncertain-receipt work and final required CI remain separate release conditions. No product regression was reproduced by this source/evidence review.
