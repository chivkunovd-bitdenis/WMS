# Sanitized staging deployment identity evidence

Captured: 2026-08-12 12:57:05 MSK (`2026-08-12T09:57:05Z`). No environment variables, token values, database URLs or credential values were read or recorded.

## Read-only commands and endpoints

1. `railway status --json`
   - Uses the already linked Railway project in read-only status mode.
   - Project ID: `c28e681d-4535-4c96-ac97-c7b600a7f8e4`.
   - Environment: `production`, environment ID `58a08b66-1290-45a2-8737-e3d7408389e5` (this is the project's staging test environment despite Railway's internal environment label).
2. `curl -D - -o /dev/null https://web-production-9e7c1.up.railway.app/`
   - HTTP 200 at `2026-08-12T09:57:05Z`.
   - `Last-Modified: Sun, 09 Aug 2026 14:10:41 GMT`.
3. `curl -D - https://wms-production-780c.up.railway.app/health`
   - HTTP 200 with body `{"status":"ok"}` at `2026-08-12T09:57:06Z`.
4. `railway logs --service WMS --deployment --lines 80 --since 2026-08-09T17:56:00Z --until 2026-08-09T18:05:00Z --json`
   - Deployment startup records `PostgresqlImpl`, transactional DDL, successful Uvicorn startup and `/health` 200.
5. Git object-only comparisons:
   - `git log --reverse 44fe72e…a39530c`;
   - `git diff --name-status 44fe72e…a39530c`;
   - `git ls-tree -r --name-only <sha> backend/alembic/versions`.

## Sanitized Railway metadata

| Service | Service ID | Deployment ID | Image digest | Commit | Status / runtime instance |
|---|---|---|---|---|---|
| `web` | `f2ad51a8-009d-488c-9d64-7054072ccac6` | `9960b498-ebe5-4115-b7d8-37fc2e2a769f` | `sha256:d0975289ca8df6ca1c2a117547cb89d4bc8bc9d3c1e4aac67db77f529ef25535` | `44fe72e3525332bb01fd76ba420f9cecbdaac6ba` | `SUCCESS`; instance `11279334-2211-42c0-a945-6ebdc77cb0b1` `RUNNING` |
| `WMS` | `e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc` | `e0a55a42-8159-4cc6-a976-1331cf98dd07` | `sha256:3d5bd164d886126eb9f0ffb2723e91d8e4b5f878e9fd11c88da75aff66dc5781` | `44fe72e3525332bb01fd76ba420f9cecbdaac6ba` | `SUCCESS`; instance `7ca012ad-d705-4a30-acc4-6c1ff3dc949e` `RUNNING` |
| `Postgres` | `7ba030a6-5608-406f-838f-22cd19b44a11` | `c7211876-b05a-4a89-96de-1aa3941f249e` | Railway Postgres image, not a WMS Git commit | N/A | `SUCCESS`; instance `593b7021-c691-4460-8390-0ce8830c21fd` `RUNNING` |

The Railway service inventory contains exactly `WMS`, `web` and `Postgres`. There is no service whose manifest or start command runs Celery worker/beat. `backend/Dockerfile.railway:18` runs only `alembic upgrade head` followed by Uvicorn. This proves absence of a separately deployed worker in this project inventory; it does not prove that no background work could ever execute inline inside the API.

## Commit delta to requested etalon runtime baseline

Ordered commits after deployed `44fe72e…` up to requested baseline `a39530c…`:

1. `c03fd76e347ae7d30288e8171b4869b53a3684c2` — `fix(fbs): один переключатель вместо двух — привязка склада включена сразу`.
2. `a39530c5137deb31e189c2136b613d01093af87b` — `fix(fbs): читать реальное поле WB для признака ПВЗ`.

Changed runtime paths:

- added `backend/alembic/versions/20260809_0076_enable_stock_sync_on_bindings.py`;
- modified `backend/app/services/wb_marketplace_orders_service.py`;
- test-only `backend/tests/test_fbs_orders_intake.py`;
- emulator-only `wb_emulator/seed/bootstrap.py`.

## Why schema is inferred as 0075

- The exact deployed Git tree `44fe72e…` contains migration `20260809_0075_product_fbs_stock_sync_flag.py` and does not contain `20260809_0076_enable_stock_sync_on_bindings.py`.
- Its `backend/Dockerfile.railway` always runs `alembic upgrade head` before starting Uvicorn.
- The deployment log records Alembic initializing PostgreSQL without an error, then Uvicorn starting and the health check returning 200.
- Therefore the strongest available inference is schema head `20260809_0075`.
- It is not direct proof: there is no schema/version API endpoint, and direct PostgreSQL access would require retrieving a database credential, which was outside this review's authorization. The manifest therefore labels this `INFERRED_0075_NOT_DIRECTLY_PROVED`.
