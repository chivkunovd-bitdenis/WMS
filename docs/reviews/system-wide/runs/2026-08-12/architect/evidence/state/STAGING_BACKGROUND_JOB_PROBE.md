# Sanitized staging background-job evidence

Captured 2026-08-12 at 13:20 MSK (`2026-08-12T10:20:24Z`) against staging commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`.

## Deployment inventory

The Railway project inventory still contained exactly three services: `WMS`, `web`, and `Postgres`, with the deployment identifiers recorded in `STAGING_DEPLOYMENT_IDENTITY.md`. There was no Celery worker or beat/scheduler service. The WMS image starts Alembic and Uvicorn only.

## Safe inline probe

In an isolated synthetic tenant, the non-external `movements_digest` background job was started twice. Each independent run returned the normal accepted/pending state and reached `done` on read-back within two seconds; each reported `total=0`. No WB operation, existing tenant, or business record was touched.

This proves the manual API path can execute through FastAPI `BackgroundTasks` inside the Uvicorn process when no broker is configured. It does **not** prove execution of periodic Celery Beat entries, because an inline API background task does not create a scheduler.

## Result boundary

- Manual non-external background job: `PROVED_TWICE_INLINE`.
- Separate durable worker: `ABSENT_FROM_DEPLOYMENT_INVENTORY`.
- Periodic scheduler: `ABSENT_FROM_DEPLOYMENT_INVENTORY`.
- API restart during an inline task: `NOT_RUN_SHARED_STAGING`.
- External WB job: `NOT_RUN_LIVE_WB_FORBIDDEN`.
