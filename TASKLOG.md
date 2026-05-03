# TASKLOG

## TASK-1 — 2026-05-03 — FF products catalog

- What changed: added the fulfillment admin products catalog screen with seller filtering, sorting by product name/stock, WB photo/barcode enrichment, and backend/admin API coverage.
- What did NOT change: marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check . && mypy . && pytest` in `backend/`; `npm run build` and `npm run test:e2e` in `frontend/`.
- Commit: 728e894
