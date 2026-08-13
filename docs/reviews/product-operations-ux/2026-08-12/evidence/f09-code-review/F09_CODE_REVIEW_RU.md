# F09 Code Review: Свободный FBO

Дата: 2026-08-13 18:24 MSK.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Code Review Agent.
Статус: `CODE_REVIEW_PASSED`.

## Mandatory checks

- `git rev-parse --show-toplevel` -> `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Прочитан `AGENTS.md`.
- Прочитан `docs/WMS_FEATURE_GATE_PROTOCOL_RU.md`.
- `git status --short --branch` до review показал грязный worktree с параллельными изменениями; code review не откатывал и не правил чужие файлы.
- Секреты, Railway variables, внешние панели, production и staging не открывались и не менялись.

## Reviewed object

- Atomic dev commit: `1689c23261c1b347a3f31c55e9930fcbebca3855` (`Implement F09 free FBO availability`).
- Product/UX verdict: `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-f10-product-unblock/F09_F10_PRODUCT_UX_VERDICT_RU.md`.
- Dev evidence: `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-dev/F09_DEV_RESULT_RU.md`.

## Findings

Blocking findings: none.

The backend availability path now uses free FBO when stock directions exist. In `backend/app/services/marketplace_unload_service.py`, `_available_product_availability_in_warehouse()` computes physical warehouse stock as storage plus sorting, subtracts all stock directions (`FBS` plus non-FBS reserves), then subtracts active outbound and MP/FBO reservations. The add, replace, plan and confirm paths all call the same `_assert_available_for_unload_quantity()` helper, so attempts beyond free FBO fail consistently. When the shortage comes from the free-FBO pool, the API maps it to `422 insufficient_free_fbo`.

The readonly picker endpoint is aligned with the same business number. `list_available_products()` subtracts stock directions when they exist, otherwise preserves the old fallback that subtracts FBS order reservations. It also subtracts active outbound and MP/FBO reservations and clamps visible availability at zero.

The F09 UI remains compact. The seller MP dialog and FF MP picker use short labels `Доступно FBO` / `доступно для FBO N`, the empty state says `Нет свободного FBO остатка для отгрузки.`, and the error shown through `readApiErrorMessage()` is human-readable: `Недостаточно свободного FBO остатка. Уменьшите количество или освободите резерв/FBS-пул.` I did not find `Лимит`, raw formulas, reserve ids, extra chips, extra columns, or a second drawer in the F09 touched UI paths.

No F10/F22 sync boundary regression found in this review. `backend/app/services/fbs_stock_availability_service.py` still publishes FBS availability from explicit FBS direction minus active FBS order reservations only. MP/FBO reservations may still schedule a seller publish job through existing marketplace-unload reservation hooks, but the publish calculation itself does not consume MP/FBO reservations as FBS stock.

## Test coverage review

The new backend test is meaningful for F09: it creates the canonical case `1000 total -> 200 FBS + 300 non-FBS reserve -> 500 free FBO`, adds another active MP reservation of `100`, verifies both inventory summary and MP picker availability as `400`, then checks that `401` fails with `insufficient_free_fbo` and `400` succeeds.

Existing stock-direction tests cover the F08/F09 boundary where FBS order reservations reduce FBS availability but do not double-subtract from free FBO. The FBS sync tests cover the F10/F22 fail-closed publication boundary.

## Tests run

- `cd backend && pytest tests/test_marketplace_unload_availability.py tests/test_stock_directions.py tests/test_fbs_stock_sync.py -q` -> `34 passed in 56.59s`.
- `cd frontend && npm run build` -> passed; Vite reported only the existing large chunk warning.
- `cd frontend && npx playwright test tests-e2e/seller-mp-unload.spec.ts tests-e2e/ff-mp-full-flow.spec.ts --workers=1 --reporter=line` -> `3 passed (1.3m)`.

E2E notes: the Playwright run used local FastAPI sqlite/Vite from `frontend/playwright.config.ts` with WB mocks. The log showed non-fatal MUI warnings about a disabled button inside `Tooltip` and an out-of-range Select value before options loaded; the tests still passed.

## Residual risks

- This is Code Review only. It does not claim `BROWSER_PRODUCT_QA_PASSED`; the separate Browser Product QA gate still must click the real warehouse scenario.
- The worktree remained dirty from parallel feature work throughout review. Two F09-touched frontend files (`frontend/src/screens/ff/FfSuppliesShipmentsPage.tsx`, `frontend/src/utils/readApiErrorMessage.ts`) had later local changes after commit `1689c23`; I checked the current content and the F09 labels/messages were still present.
- Stock directions are product-level in the current F08 model, while MP availability is requested for a WMS warehouse. That is not introduced by F09 and the approved F09 example passes, but a future multi-warehouse allocation rule may need a separate product decision.

## Changed by this review

- `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-code-review/F09_CODE_REVIEW_RU.md`

No matrix update was made in this review to avoid mixing evidence with unrelated dirty iteration changes.
