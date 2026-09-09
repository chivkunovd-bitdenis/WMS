# Astra 6 high independent read-only review — WB cancel-return lane

## Ask
Independently review branch `feat/wms111-wb-cancel-return` at HEAD `f1b879fd` versus base SHA `bc7f760c11b032fbb94376f042bb6d0f2dd7c13b`. Do NOT rewrite. Do NOT rebase. Do NOT run destructive operations. Reply in Russian.

Deliver a verdict with:
1. Semantic correctness of each committed change vs the owner's contract (below).
2. Concrete evidence lines you actually read (path:line — from the diff, not from memory).
3. Material findings that must be fixed before release.
4. Edge cases the tests miss.

## Scope in this diff — 2 commits

- **WMS-111** — after a WB cancellation that arrives AFTER the confirmed transfer to WB, the system creates the existing return-document type EXACTLY ONCE, idempotent on retry. Before-transfer cancels create no return document. Return document creation MUST NOT physically accept goods and MUST NOT change stock. Do not synthesize cancel-time; use WB payload's `cancelled_at` if present, else received-at, marked.
- **WMS-112** — the boundary "before transfer" vs "after transfer" is derived from EXISTING state (not from a new flag). Registry response now exposes `cancelled_at`, `cancelled_at_source`, `cancelled_after_transfer`, `transfer_at`, `return_document_id`.

## Author's key design decision — please validate
Reused existing entity: `InboundIntakeRequest` with `operation_type="return"` and `marketplace="wildberries"` (same document the manual return flow already creates; `RETURN_MARKETPLACES = frozenset({"wildberries", "ozon"})` in `inbound_intake_service.py`). No new table, no new document type, no new status, no new flag on `FbsOrder`. Idempotency key = natural `wb_order_id`. Marker stored in existing `FbsOrder.meta_details_json`. Transfer boundary reuses `confirmed_order_handover_dates()` — the same signal billing WMS-406 uses.

## Files
- ADDED: `backend/app/services/fbs_cancel_return_document_service.py` — helpers `cancel_time_from_row`, `was_transferred`, `ensure_cancel_return_document`, `maybe_create_cancel_return_document`, plus marker/source constants.
- MODIFIED: `backend/app/services/fbs_cancellation_service.py` — hook in `_finish_local_cancellation` (operator cancel path).
- MODIFIED: `backend/app/services/wb_marketplace_orders_service.py` — hook in `_apply_wb_status_to_order` (auto-sync cancel branch); signature gained optional `row` kwarg; two call sites updated.
- MODIFIED: `backend/app/services/fbs_cancelled_after_pack_service.py` — registry response fields added.
- ADDED: `backend/tests/test_wms111_wb_cancel_return.py` — 7 tests.
- MODIFIED: `docs/KANONICHESKIY_BACKLOG.md` — WMS-111/112 status.
- ADDED: `docs/reviews/wms111-wb-cancel-return-2026-09-10.md`.

## Specific questions
1. Idempotency: does `maybe_create_cancel_return_document` truly serialize on the natural `wb_order_id` key, i.e., a second call in the same transaction OR a second call from a retry (different transaction) creates NO duplicate `InboundIntakeRequest`? What lock does it hold?
2. Concurrency: two WB webhook deliveries arriving simultaneously for the same cancel — race condition? Is the check-and-insert atomic under Postgres serializable? Under READ COMMITTED?
3. Boundary correctness: `was_transferred(row)` uses `confirmed_order_handover_dates()`. If billing has ever mis-classified a transfer (WMS-406 open questions), does the same signal here cause a stale classification?
4. Stock invariance: the tests assert zero `InventoryBalance` / `InventoryMovement` rows on cancel-after-transfer. Are there any indirect writes via triggers or async workers reachable from this code path?
5. Cancel time handling: WB payload without `cancelled_at` → fallback to received-at. Is received-at actually the request-arrival time (accurate) or the row-insert time (possibly late)?
6. Registry response fields: could exposing `cancelled_after_transfer` and `return_document_id` inadvertently leak business info to the seller portal for orders the seller shouldn't see?
7. Two call sites in `wb_marketplace_orders_service.py` gained the `row` kwarg — are they consistent, or is one path bypassing the return-doc hook?

## Boundaries
- Do NOT touch inventory_service.py, product_merge_service.py, chat components, mobile/, FBS columns.
- Do NOT propose new tables / flags / journals / statuses.
- Output: 20-100 lines of Russian text; prefer specific path:line citations.
