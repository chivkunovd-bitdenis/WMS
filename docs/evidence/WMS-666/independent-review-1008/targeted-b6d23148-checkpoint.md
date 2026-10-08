# WMS-666: bounded source checkpoint for b6d23148

Product examined: `b6d23148f1571d08d13d83c6179c385e2f6a1efc`.
Base of this targeted delta: `cedb428b5585b0214e27b390c93ef1a3665dbbbd`.
The remote `codex/wms666-packing-release-1008` resolved to the exact product SHA during this review. Reviewer worktree/branch is `wms666-independent-acceptance-1008` / `codex/wms666-independent-acceptance-1008`.

**Source verdict: no new confirmed technical defect in this delta. Release verdict: NO-GO pending complete current evidence. This document is not an accepting R and does not nominate P as a trusted product ref for activation CI.**

This continues checkpoints c933b1a0 and 89786188. The unchanged original 24-path audit, GS1 preservation, Ozon generation/timestamp ties, rejected exact WB reprint, partial QR recovery and partial manual acknowledgement reviews were not repeated. The deployed baseline 212f19d is not reclassified as having complete functional acceptance.

## Accounting context and code ownership

The manual tape path no longer requires a product line merely because a supply has a task ID. Missing or exhausted line capacity falls back to the existing seller/product pool operation, allocating exactly one code for the real order. Existing current-code reuse and reprint remain before allocation; honest-sign skip remains before the new allocation branch. A missing product still cannot allocate an unidentified product's code.

A nested transaction now encloses allocation, PRINTED event and assignment to the order, on both the accounting-line and fallback paths. The independently frozen conflict test asserts the actual two pool IDs stay AVAILABLE, no PRINTED event is committed, the old accepted marking's value/identity/link remains unchanged, and stock snapshots match. This is the correct failure contract for the previously confirmed partial spend; it does not merely assert an error response.

Copies remain a layout/event attribute: the fallback passes quantity=1, the line path units_to_print=1. Generic catalog defaults (commit=True, catalog source, absent document/line context) are retained. The only generic service addition is optional accounting context used by this FBS caller; no catalog/FBO route or allocation rules changed.

When a line exists, its identity remains on the code and event; ordinary available capacity retains the established line-printing path. Exhausted-line fallback does not invent more packing need or rewrite existing packed/printed counters. Both independently frozen exhausted-counter variants expressly preserve their initial counters. The UI's required/current-code/printed state remains derived from current orders, not a fabricated new task or a reset accounting counter.

## Operator KIZ and rollback

Applying the same current PRINTED/RESERVED CIS can now record APPLIED without an accounting line. New binding and previous-code restoration use optional accounting context, preserving a supply document number where present. Existing line counters are updated only when a line exists. `_recount_line_markings` already accepts None and returns without a fabricated accounting record.

The optional helper catches only `packaging_line_not_found`. The original order lookup, tenant/order status checks, locking, product/seller pool checks and provider confirmation/reconciliation logic are unchanged. It does not grant access to another PRINTED code: the foreign-occupancy path still requires the original line lookup, and a None line cannot compare equal to a None code-line ID. The actual pool claim still enforces its existing occupied-code rules.

The new frozen API cases cover (1) tape → successful validate → same-CIS apply without task creation, (2) direct pool binding without a task, and (3) provider rejection during replacement with restoration of the exact prior CIS. They assert pool/binding identity, APPLIED event source and supply document, unchanged stock, and task remaining NULL. Fixture follow-ups persist the intended document number and verify it from a fresh session; they do not remove the business assertions.

I read the committed RED stdout at `196e46cd4dfa2a4ac85ea11a0ef7513ca38cb5f6:docs/evidence/WMS-666/taskless-kiz-bindings/taskless-kiz-red.txt`: all three fail on the cedb KIZ service blob with `packaging_line_not_found`. The first reaches successful tape and validate before commit fails. This establishes reachability of the old defect; synthetic WB acceptance/rejection is not a claim about live WB.

## Current pool display and preserved adjacent behavior

The entire Workspace source differs from cedb only in `order.marking_available_count ?? line?.marking_available_count ?? 0`. A current explicit zero therefore wins over stale positive task data, while absent current data still falls back to the legacy line. Both frozen DOM directions are preserved: 0→2 replenishment and 2→0 depletion, including the value passed to the manual print dialog.

The existing shared helper serves ordinary and assembly rendering/actions. Product deduplication and seller-scoped workspace data are unchanged. Printed/required/packed controls, row columns, `orderPrintDone`, metadata/provider acceptance semantics and current-code reprint selection are byte-identical apart from the count-expression replacement. A native receipt alone still does not make the provider-accepted printed total advance.

Ozon's actual tape branch continues before WB allocation. `_active_ozon_sgtin_markings`, the shared late binding validator and all of `fbs_marking_service.py` are unchanged from the previous reviewed checkpoint: quantity/timestamp ties and newest-per-exemplar semantics are not replaced by the fallback line capacity. The fallback preserves `order.product_id or line.product_id` for the existing legacy line case. GS1 normalization is unchanged.

The approved renderer fixture maintenance changes only WB's synthetic nonnumeric order ID to a numeric domain value and the two empty-location literals to the existing renderer wording. Geometry, rows, request-order and fresh-context assertions remain. The added comment's phrase “longest realistic value” is not evidence of a normative WB maximum and is not used as an acceptance premise.

## Evidence provenance and remaining work

`targeted-b6d23148-source.json` records independently checked Git blobs and mechanical source-identity/structure checks. `git diff --check cedb428b5 b6d23148` succeeded. The seven current API cases (missing line, two exhausted-line variants, atomic conflict, three taskless KIZ cases) and the two DOM contracts were read; this reviewer did not rerun a competing full test suite.

Developer reports 7 current API, 121 KIZ, 3 Ozon, 1 exact rejected-WB, 2 stale-pool DOM passes and Ruff/mypy/TSC/build success. At the time of this checkpoint I requested the exact persisted stdout/manifest, but had not received it. The available `taskless-manual-kiz-backend-regressions.txt` says 137 passed/7 skipped without exact-P provenance; `taskless-manual-kiz-ui-contract.txt` explicitly belongs to cedb-compatible frontend source. Neither is substituted for the reported current results. Reported counts remain reported until verifiable logs/source linkage arrive.

Final acceptance still needs the complete current ordinary/group process and compatibility mapping M01–M43, real native Handler receipts/decoded payloads/ledgers for the required flags, copies, rapid scans, recovery, clear/reload/returns and before-validation unlink boundaries, provider accepted/rejected emulator readback, and mandatory exact-SHA CI. Native PNG sink proof is not physical paper; synthetic provider proof is not live WB. Earlier contaminated QR-only order-barcode attribution remains rejected. Pre-acceptance recovery is not post-acceptance lost-reply recovery. The sole owner-accepted residual is concurrent unlink after the last successful validation response and before native acceptance.

Product and test files were not changed by the reviewer. No deployment, main merge or accepting R was performed. Future source changes require targeted review; unchanged reviewed code does not require another broad audit.
