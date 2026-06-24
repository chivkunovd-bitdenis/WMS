# BUGLOG

## BUG-3 — 2026-06-24 — Дата отгрузки сбрасывается после выбора в календаре

- Symptom: в заявке на отгрузку на МП пользователь выбирает дату в календаре, но поле сразу очищается.
- Cause: `WmsDateField` на `onBlur` вызывал `onChange(null)` при пустом значении секции поля; после закрытия календаря MUI X v9 blur срабатывал на пустой секции и отправлял PATCH с `planned_shipment_date: null`.
- Fix: пустой blur больше не сбрасывает дату; ручной ввод по-прежнему парсится на blur.
- Verification: `npm run build`; e2e `seller-mp-unload.spec.ts` (TC-NEW-DATE-01 blur persistence), `ff-dashboard.spec.ts`.
- Commit: pending

## BUG-2 — 2026-05-03 — FF could add no-stock products to WB shipment

- Symptom: while adding products to a WB marketplace shipment, FF saw catalog products that did not have actual warehouse stock and could add them to the document.
- Cause: the shipment UI used the full product catalog for the picker, and `marketplace-unload` line creation only checked tenant/seller ownership, not available warehouse stock.
- Fix: the FF shipment picker is fed from inventory availability, and backend line creation rejects products/quantities without enough available stock in the shipment warehouse.
- Verification: `pytest tests/test_marketplace_unload_and_discrepancy_acts.py`; targeted `ruff`/`mypy`; `npm run build`; `npm run test:e2e -- ff-dashboard.spec.ts`.
- Commit: pending

## BUG-1 — 2026-05-03 — Accepted seller products missing from FF catalog

- Symptom: after FF completed seller inbound acceptance/distribution, products did not appear in the FF products catalog.
- Cause: `/products/ff-catalog` correctly listed products with inventory movements, but `distribution-complete` only locked distribution lines and did not create inventory movements or balances.
- Fix: completing distribution now posts distributed actual quantities into inventory movements/balances and updates inbound `posted_qty`; the catalog can then include those products.
- Verification: `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`; targeted `ruff`/`mypy`.
- Commit: d5a954f
