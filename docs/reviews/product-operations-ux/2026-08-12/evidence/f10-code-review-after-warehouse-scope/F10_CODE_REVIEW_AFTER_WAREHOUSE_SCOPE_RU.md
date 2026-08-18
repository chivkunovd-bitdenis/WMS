# F10 Code Review after warehouse-scope rework

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Code Review Agent.
Reviewed rework commit: `4b611f27b2953e37d6003214ee72577af7321ee6`.
Status: `CODE_REVIEW_PASSED`.

## Mandatory checks

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Прочитан `AGENTS.md`.
- Прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
- `git status --short --branch` перед review: checkout already dirty/ahead; unrelated dirty files were not modified or staged.

## Scope reviewed

- Rework diff: `backend/app/services/fbs_stock_sync_service.py`, `backend/tests/test_fbs_stock_sync.py`, F10 docs/evidence.
- Supporting implementation read: `backend/app/services/fbs_stock_availability_service.py`, `backend/app/services/stock_direction_service.py`, `backend/app/services/fbs_autopoll_service.py`, `backend/app/services/background_job_service.py`, `backend/app/api/fbs_sellers.py`, `backend/app/services/seller_wb_catalog_service.py`, `backend/app/models/fbs_warehouse_binding.py`, `backend/app/models/fbs_stock_sync_item.py`.
- UI/read-model scan: `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `frontend/src/screens/v2/SellerProductsStockScreen.tsx`, `frontend/src/screens/v2/fbsApi.ts`.

## Findings

No blocking findings found for the F10 warehouse-scope rework.

## Evidence

1. Ambiguous multi-warehouse product-level FBS pool cannot be published to multiple WB warehouses.

   `sync_binding_stocks()` checks active stock-sync bindings for the seller through `_seller_has_ambiguous_stock_sync_scope()`. If more than one active `FbsWarehouseBinding` with `stock_sync_enabled=true` exists, every product with explicit FBS direction quantity (`directions.fbs > 0`) gets `ERROR_AMBIGUOUS_WAREHOUSE_SCOPE` before publish targets are created. Those blocked products go to `_mark_blocked_items()`, not `_upsert_pending_items()` / `_publish_batches()`, so there is no WB PUT and no readback POST.

   Line evidence:
   - `backend/app/services/fbs_stock_sync_service.py:262` counts active stock-sync bindings.
   - `backend/app/services/fbs_stock_sync_service.py:614` creates per-product ambiguous block reasons.
   - `backend/app/services/fbs_stock_sync_service.py:641` marks blocked rows before publish.
   - `backend/app/services/fbs_stock_sync_service.py:644` publishes only non-blocked targets.

2. Fail-closed state does not publish zero.

   The ambiguous path never creates a `MarketplaceStockAmount` with amount `0`; it creates error rows with `last_target_amount=None` and binding `last_error_code=ambiguous_warehouse_scope`. The regression test also seeds mock WB stock `20` and asserts it stays `20`, with both `put_calls` and `post_calls` empty.

   Line evidence:
   - `backend/tests/test_fbs_stock_sync.py:587` seeds existing mock WB stock.
   - `backend/tests/test_fbs_stock_sync.py:607` asserts zero targeted/confirmed products.
   - `backend/tests/test_fbs_stock_sync.py:613` asserts no PUT.
   - `backend/tests/test_fbs_stock_sync.py:614` asserts no readback POST.
   - `backend/tests/test_fbs_stock_sync.py:615` asserts the existing WB value is unchanged.
   - `backend/tests/test_fbs_stock_sync.py:629` asserts `ambiguous_warehouse_scope`.
   - `backend/tests/test_fbs_stock_sync.py:630` asserts no target amount.

3. Single warehouse positive path still publishes FBS pool minus FBS reservations.

   The positive F10 test still covers physical stock `1000`, explicit FBS pool `200`, non-FBS direction `300`, active FBS order reservation `7`, and verifies WB receives/readbacks `193`, not total physical stock and not free FBO.

   Line evidence:
   - `backend/tests/test_fbs_stock_sync.py:500` seeds FBS pool `200`.
   - `backend/tests/test_fbs_stock_sync.py:508` seeds non-FBS reserve direction `300`.
   - `backend/tests/test_fbs_stock_sync.py:515` seeds FBS order reservation `7`.
   - `backend/tests/test_fbs_stock_sync.py:540` asserts WB PUT amount `193`.
   - `backend/tests/test_fbs_stock_sync.py:542` asserts not physical total `1000`.
   - `backend/tests/test_fbs_stock_sync.py:543` asserts not free FBO `500`.
   - `backend/tests/test_fbs_stock_sync.py:544` asserts WB readback happened for the positive path.

4. UI compactness / raw-code check.

   Rework did not touch frontend. Seller compact F22 UI still derives a short user-facing state from `fbs_sync_status`: error/conflict shows `Ошибка WB`, confirmed shows `WB: N шт`, and no raw F10 code is introduced in the main seller product table. The FF stock-sync binding row and status header map unknown backend error codes to the generic human text `Синхронизация завершилась с ошибкой`.

   Residual non-blocking note: the existing diagnostic status table still renders `item.error` directly for all stock-sync errors. That behavior predates this rework and is not the main compact UI; a separate UI polish task can map item-level codes if product wants every diagnostic row humanized.

## Tests run

- Initial parallel pytest attempt hit shared sqlite DDL collisions (`database schema has changed`, `table background_jobs already exists`, `no such table: users`). This was caused by running multiple pytest processes against the same `tests/wms_pytest.sqlite`; it was not counted as a product/code failure.
- Removed the ignored generated test DB `backend/tests/wms_pytest.sqlite` and reran sequentially.
- `pytest tests/test_fbs_stock_sync.py tests/test_fbs_stock_availability.py` -> 31 passed in 97.54s.
- `pytest tests/test_stock_directions.py::test_directions_drive_fbs_pool_and_mp_free_fbo` -> 1 passed in 3.07s.
- `ruff check app/services/fbs_stock_sync_service.py tests/test_fbs_stock_sync.py` -> All checks passed.

## Review result

`CODE_REVIEW_PASSED`.

F10 may move to Browser Product QA after this review. Browser QA still must click the real UI; this code review does not replace that gate.
