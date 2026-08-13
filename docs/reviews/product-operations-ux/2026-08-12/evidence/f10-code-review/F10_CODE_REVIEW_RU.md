# F10 Code Review: FBS sync publishes only FBS pool

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Code Review Agent.
Reviewed dev commit: `1e85cc7507865a4b5cce961af99b39cbb2860560`.
Status: `CODE_REVIEW_FAILED`.

## Mandatory checks

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Прочитан `AGENTS.md`.
- Прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
- `git status --short --branch` перед review: checkout already dirty/ahead; unrelated dirty files were not modified or staged.

## Scope reviewed

- Product/UX source: `evidence/f09-f10-product-unblock/F09_F10_PRODUCT_UX_VERDICT_RU.md`.
- Dev evidence: `evidence/f10-dev/F10_DEV_EVIDENCE_RU.md`.
- Dev diff: `backend/tests/test_fbs_stock_sync.py`, F10 section in `ITERATION_FEATURE_CARDS_RU.md`, `evidence/f10-dev/F10_DEV_EVIDENCE_RU.md`.
- Implementation inspected: `backend/app/services/fbs_stock_availability_service.py`, `backend/app/services/fbs_stock_sync_service.py`, `backend/app/services/stock_direction_service.py`, `backend/app/models/stock_direction.py`, `backend/app/models/fbs_warehouse_binding.py`.
- UI/read model scan: `frontend/src/screens/v2/SellerProductsStockScreen.tsx`, `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`, `backend/app/services/seller_wb_catalog_service.py`.

## Finding

### P1. FBS pool is not scoped to WMS/WB warehouse binding

F10 product scope requires `publishable_fbs = explicit_fbs_pool - active_fbs_order_reservations`, scoped by seller + WMS warehouse + WB warehouse mapping. The current reservation side is warehouse-scoped, but the FBS pool itself is not.

Evidence:

- `StockDirection` has `tenant_id`, `product_id`, `quantity`, `is_fbs`, but no `warehouse_id`.
- `stock_direction_service.direction_totals_by_product()` groups only by `StockDirection.product_id` for a tenant.
- `fbs_stock_availability_service.fbs_available_qty_by_product()` receives a `warehouse_id`, uses it for `FbsOrderReservation`, then subtracts those reservations from the product-level direction total.
- `fbs_stock_sync_service.sync_binding_stocks()` calls that availability calculation for one `FbsWarehouseBinding.wms_warehouse_id`, but the FBS pool value can still be the same global product-level FBS direction for another seller warehouse binding.
- `FbsWarehouseBinding` explicitly supports separate seller + WB warehouse and seller + WMS warehouse pairs.

Business impact:

If one seller has multiple WB/WMS warehouse bindings for the same product variant, the same product-level FBS pool can be published for more than one warehouse. Example: seller allocates FBS pool `200` for product `A`; binding `WB-1 -> WMS-1` and binding `WB-2 -> WMS-2` both load the same `StockDirection` total. The code can publish `200` to each WB warehouse, minus only reservations in that warehouse. That violates the F10/F22 warehouse scope rule and can overstate sellable FBS stock in WB.

Why the new test does not catch it:

`test_sync_publishes_fbs_pool_minus_fbs_order_reservations_only` is useful for the single-binding formula. It proves physical `1000`, FBS pool `200`, non-FBS directions `300`, active FBS reservation `7` -> WB/readback `193`, not `1000` and not free FBO `500`. But it seeds only one warehouse binding, one storage location, and one FBS pool, so it cannot detect cross-warehouse reuse of the same pool.

Required fix:

Either make the explicit FBS pool warehouse-aware for publication, or add a product-approved invariant that a seller/product can have only one active FBS warehouse binding. The safer WMS fix is to scope FBS directions/availability by the WMS warehouse used by the binding and add a regression test where two bindings exist for the same seller/product and only the intended warehouse pool is published.

## Checks That Passed

- No path found where F10 sync uses physical total stock or free FBO as the publish amount. The publish amount comes from `fbs_available_qty_by_product()`, not `InventoryBalance.quantity` or marketplace/FBO availability.
- Missing/unknown FBS pool remains fail-closed before WB PUT. The existing F22 tests cover no FBS pool keeping WB/emulator value unchanged and no stale zeroing of old sync items.
- Readback is required before confirmed success. On readback mismatch, sync item and binding stay error.
- `fbs_stock_limit` is used only as a cap after availability exists, not as the primary source of quantity. `fbs_stock_limit=0` is blocked as unsafe zero, not published.
- The F10 dev diff introduced no frontend changes. Current seller row status remains compact/human (`Нет FBS`, `Пауза`, `Проверяем WB`, `WB: N шт`, `Ошибка WB`); no F10-specific raw code, `Лимит` column, or bulk UI noise was introduced by the dev commit.

## Tests Run

- `pytest tests/test_fbs_stock_sync.py tests/test_fbs_stock_availability.py` -> 30 passed.
- `pytest tests/test_stock_directions.py::test_directions_drive_fbs_pool_and_mp_free_fbo` -> 1 passed.
- `ruff check tests/test_fbs_stock_sync.py` -> passed.

These were run in the current dirty checkout; the reviewed dev commit is `HEAD`, but unrelated dirty files existed before review.

## Review Result

`CODE_REVIEW_FAILED`.

F10 may proceed back to dev with a narrow fix for warehouse-scoped FBS pool publication and a targeted regression test. Browser Product QA should stay blocked until code review passes.
