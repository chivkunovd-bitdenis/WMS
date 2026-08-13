# F09 Dev result: Свободный остаток для FBO

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Atomic Dev Agent.
Статус: `DEV_DONE`.

## Gate input

- Product/UX verdict: `PRODUCT_APPROVED_FOR_DEV` в `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-f10-product-unblock/F09_F10_PRODUCT_UX_VERDICT_RU.md`.
- Scope: только F09, без F10/WB sync/F22 publishing, без Railway/staging/production/секретов.
- Worktree до старта был грязный из-за параллельных фич; чужие изменения не откатывались.

## F08/F09 findings before changes

- F08 уже добавила `quantity_free_fbo` в inventory balance DTO/API.
- `stock_direction_service.distributions_by_product()` уже считает free FBO как физический остаток минус FBS-направления и прочие направления/резервы.
- `marketplace_unload_service.list_available_products()` уже использовал directions при MP/FBO picker availability и вычитал активные outbound/MP reserves.
- Существующий F08 тест `test_directions_drive_fbs_pool_and_mp_free_fbo` уже проверял, что FBS-reservation не вычитает FBO второй раз, когда есть явный FBS-пул.

## Dev changes

- Добавлен отдельный backend shortage reason `insufficient_free_fbo` для MP/FBO валидации, когда товар ограничен free FBO pool.
- Добавлен общий helper availability validation для add/replace/plan/confirm MP unload lines, чтобы эти точки одинаково возвращали FBO-specific shortage.
- Existing picker/modal UI оставлен без новой колонки `Лимит`; доступность подписана коротко как `Доступно FBO` / `доступно для FBO N`.
- Добавлен human-readable frontend message: `Недостаточно свободного FBO остатка. Уменьшите количество или освободите резерв/FBS-пул.`
- Добавлен targeted backend test на пример F09: `1000 total -> 200 FBS + 300 reserve -> 500 free FBO`, другой active MP reserve `100`, доступно к новой FBO отгрузке `400`, `401` блокируется.

## Changed files

- `backend/app/services/marketplace_unload_service.py`
- `backend/app/api/marketplace_unload_requests.py`
- `backend/tests/test_marketplace_unload_availability.py`
- `frontend/src/components/WbProductPickerDialog.tsx`
- `frontend/src/components/SellerMarketplaceUnloadDialog.tsx`
- `frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`
- `frontend/src/utils/readApiErrorMessage.ts`
- `docs/reviews/product-operations-ux/2026-08-12/ITERATION_FEATURE_CARDS_RU.md`
- `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-dev/F09_DEV_RESULT_RU.md`

## Tests run

- `pytest backend/tests/test_marketplace_unload_availability.py -q` -> 2 passed.
- `pytest backend/tests/test_stock_directions.py backend/tests/test_marketplace_unload_availability.py -q` -> 10 passed.
- `cd backend && ruff check app/api/marketplace_unload_requests.py app/services/marketplace_unload_service.py tests/test_marketplace_unload_availability.py` -> passed.
- `cd frontend && npm run build` -> passed.
- `cd frontend && npx playwright test tests-e2e/seller-mp-unload.spec.ts --workers=1` -> 2 passed.
- `cd frontend && npx playwright test tests-e2e/ff-mp-full-flow.spec.ts --workers=1` -> 1 passed.

## Remaining risks

- Browser Product QA gate is not claimed here; this is Atomic Dev result only.
- The worktree still contains many unrelated modified/untracked files from parallel features.
- No push/deploy was done by instruction.
