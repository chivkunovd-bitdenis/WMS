# TASKLOG

## TASK-5 — 2026-05-03 — Production Docker Compose HTTPS via Caddy

- What changed: production `docker-compose.prod.yml` now publishes `80/443` for Caddy, persists ACME state in Docker volumes, and passes `WMS_PUBLIC_DOMAIN` into the `web` container; production Caddy site blocks use the public domain for automatic HTTPS; added `deploy/env.prod.example` and updated README production instructions for DNS + HTTPS.
- What did NOT change: application code, database schema/migrations, Celery task definitions, and dev `docker-compose.yml` behavior were not changed in this task.
- Verification: `WMS_PUBLIC_DOMAIN=example.com POSTGRES_PASSWORD=postgres JWT_SECRET_KEY=dev-secret WMS_SECRETS_FERNET_KEY=dev-fernet DATABASE_URL='postgresql+psycopg_async://postgres:postgres@db:5432/wms' docker compose -f docker-compose.prod.yml config --quiet`; `ruff check . && mypy . && pytest` in `backend/`; `npm run build` in `frontend/`.
- Commit: 4c836c0

## TASK-3 — 2026-05-03 — Post accepted seller inbound distribution into FF stock

- What changed: completing FF inbound distribution now creates inventory movements and balances from distributed actual quantities, so accepted seller products appear in the FF warehouse catalog.
- What did NOT change: seller private WB catalog import, marketplace shipment flows, billing, migrations, and Docker infrastructure were not changed in this task.
- Verification: `ruff check app/services/inbound_intake_service.py tests/test_inbound_distribution.py && mypy app/services/inbound_intake_service.py`; `pytest tests/test_inbound_distribution.py tests/test_products_wb_catalog.py`.
- Commit: d5a954f

## TASK-2 — 2026-05-03 — Split seller and FF product catalogs

- What changed: renamed the FF products endpoint to `/products/ff-catalog` and changed FF catalog visibility to products with warehouse movements only; seller `/products/wb-catalog` remains private to the seller role.
- What did NOT change: seller WB import mechanics, marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check app/api/products.py app/services/seller_wb_catalog_service.py tests/test_products_wb_catalog.py && mypy app/api/products.py app/services/seller_wb_catalog_service.py`; `pytest tests/test_products_wb_catalog.py`; `npm run build`; `npm run test:e2e -- ff-products.spec.ts`.
- Commit: 4089d7e

## TASK-1 — 2026-05-03 — FF products catalog

- What changed: added the fulfillment admin products catalog screen with seller filtering, sorting by product name/stock, WB photo/barcode enrichment, and backend/admin API coverage.
- What did NOT change: marketplace shipment stock movements, adjustment acts, billing, and docker-compose infrastructure were not changed in this task.
- Verification: `ruff check . && mypy . && pytest` in `backend/`; `npm run build` and `npm run test:e2e` in `frontend/`.
- Commit: 728e894
