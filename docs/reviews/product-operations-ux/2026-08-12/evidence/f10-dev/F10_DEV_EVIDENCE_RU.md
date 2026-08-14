# F10 Dev evidence: FBS sync publishes only FBS pool

Дата: 2026-08-13, Europe/Moscow.
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
Роль: isolated Atomic Dev Agent.

## Gate inputs

- Product/UX verdict: `PRODUCT_APPROVED_FOR_DEV` in `docs/reviews/product-operations-ux/2026-08-12/evidence/f09-f10-product-unblock/F09_F10_PRODUCT_UX_VERDICT_RU.md`.
- F22 readback blocker is removed on current HEAD `646d82c5597b87b30cc10f8426d8b65493b7c19b`.
- Scope is F10 only: WB must receive explicit FBS pool, not total stock and not free FBO.

## Dev result

Current F08/F22 implementation already routes FBS sync through `fbs_available_qty_by_product`, which uses stock directions and subtracts active `FbsOrderReservation` rows for the mapped WMS warehouse.

This pass added a hardening regression test:

- physical stock is 1000;
- explicit FBS pool is 200;
- non-FBS directions/reserves are 300, so free FBO is 500;
- active FBS order reservation is 7;
- WB PUT target is 193;
- test asserts WB does not receive 1000 and does not receive 500;
- readback confirms the same 193 before the sync item becomes confirmed.

No frontend/UI code was changed. The compact F22/F23 UI constraints remain outside this dev diff:

- no visible `Лимит` column;
- no raw sync codes as the main seller UI text;
- no whole-catalog bulk action without selected rows;
- no production/staging/Railway/secret changes.

## Tests run

- `pytest tests/test_fbs_stock_sync.py::test_sync_publishes_fbs_pool_minus_fbs_order_reservations_only` -> passed.
- `pytest tests/test_fbs_stock_sync.py tests/test_fbs_stock_availability.py` -> 30 passed.
- `pytest tests/test_stock_directions.py::test_directions_drive_fbs_pool_and_mp_free_fbo` -> passed.
- `ruff check tests/test_fbs_stock_sync.py` -> passed.

## Remaining gates

- code_review: pending, must be done by isolated Code Review Agent.
- browser_product_qa: pending for F10, must be done by isolated Browser Product QA Agent before acceptance.
- pushed/deployed: no, by instruction.
