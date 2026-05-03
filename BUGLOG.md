# BUGLOG

## BUG-1 — 2026-05-03 — Accepted seller products missing from FF catalog

- Symptom: after FF completed seller inbound acceptance/distribution, products did not appear in the FF products catalog.
- Cause: `/products/ff-catalog` correctly listed products with inventory movements, but `distribution-complete` only locked distribution lines and did not create inventory movements or balances.
- Fix: completing distribution now posts distributed actual quantities into inventory movements/balances and updates inbound `posted_qty`; the catalog can then include those products.
- Verification: `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`; targeted `ruff`/`mypy`.
- Commit: d5a954f
