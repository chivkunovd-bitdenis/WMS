# F10 Dev rework: warehouse-scope guard for FBS stock sync

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Atomic Dev Rework Agent.
Input review: `CODE_REVIEW_FAILED` commit `a70460dbd783da7ca0345140049472d3bcb46c75`.
Status: `DEV_DONE` for the rework only; code review and browser QA are still pending.

## Blocker

FBS-пул сейчас хранится как product-level `StockDirection`: `tenant_id + product_id + quantity + is_fbs`, без `warehouse_id`.
`FbsWarehouseBinding` при этом связывает конкретный WB-склад с конкретным WMS-складом.

До rework один и тот же product-level FBS-пул мог быть рассчитан для разных active stock-sync bindings одного seller. Это безопасно для одного binding, но небезопасно для двух WB/WMS warehouse bindings: WB мог получить один и тот же пул как будто это разные складские остатки.

## Rework decision

Выбран минимальный fail-closed путь без redesign и без новой модели warehouse-scoped directions:

- если у seller больше одного active `FbsWarehouseBinding` с `stock_sync_enabled=true`;
- и у товара есть явный FBS-пул (`StockDirection.is_fbs=true`, quantity > 0);
- sync не делает WB PUT для этого товара;
- по каждому binding создаётся safe error state `ambiguous_warehouse_scope`;
- last target/readback не заполняются, старый WB остаток не затирается нулём.

Это сознательно строже, чем пытаться угадать склад по физическим остаткам: текущий `StockDirection` не хранит warehouse scope, поэтому публикация будет снова разрешена только после продуктово утверждённого warehouse-scoped allocation или другой однозначной привязки.

## Changed code

- `backend/app/services/fbs_stock_sync_service.py`
  - Added `ERROR_AMBIGUOUS_WAREHOUSE_SCOPE`.
  - Added seller-scope guard: more than one active stock-sync binding makes product-level FBS pool ambiguous.
  - `_build_publish_plan()` now accepts explicit per-product block reasons and blocks before creating publish targets.

- `backend/tests/test_fbs_stock_sync.py`
  - Added `TC-NEW-F10-002`: one seller, two active WB/WMS bindings, one product-level FBS pool.
  - The test runs sync for both bindings and asserts:
    - `products_targeted == 0`;
    - `products_confirmed == 0`;
    - no PUT calls;
    - no POST readback calls;
    - existing WB/mock value remains unchanged;
    - both binding sync rows are `error` with `ambiguous_warehouse_scope`.

No frontend/UI code, F09 MP/FBO availability, Railway, staging, production, or secrets were changed.

## Tests run

- `pytest tests/test_fbs_stock_sync.py::test_sync_publishes_fbs_pool_minus_fbs_order_reservations_only tests/test_fbs_stock_sync.py::test_sync_blocks_product_level_fbs_pool_with_two_stock_sync_bindings -q` -> 2 passed.
- `ruff check app/services/fbs_stock_sync_service.py tests/test_fbs_stock_sync.py` -> passed.
- `pytest tests/test_fbs_stock_sync.py tests/test_fbs_stock_availability.py -q` -> 31 passed.
- `pytest tests/test_stock_directions.py::test_directions_drive_fbs_pool_and_mp_free_fbo -q` -> 1 passed.

## Remaining risks

- This is a safe block, not a full warehouse-scoped allocation model.
- Sellers with more than one active FBS stock-sync binding cannot publish product-level FBS pools until the product decision introduces an unambiguous warehouse scope.
- Code review must rerun on this rework before F10 can move to Browser Product QA.
