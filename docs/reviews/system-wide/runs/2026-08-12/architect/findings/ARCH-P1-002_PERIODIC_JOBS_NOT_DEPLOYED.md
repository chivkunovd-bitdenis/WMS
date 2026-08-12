# ARCH-P1-002 — periodic jobs have no deployed scheduler

## Result

**Severity: P1. Status: CONFIRMED_DEPLOYMENT_GAP.** Staging deploys the API, frontend, and PostgreSQL, but no Celery worker or Celery Beat scheduler. Manual background endpoints can run inline in the API; the five periodic entries cannot start themselves without Beat.

This is a deployment/process defect, not an assumption based only on source: Railway metadata at `2026-08-12T10:20:24Z` listed exactly `WMS`, `web`, and `Postgres`. `backend/Dockerfile.railway:18` starts Uvicorn after migrations and nothing else. Two safe `movements_digest` probes reached `done`, confirming the documented API-inline fallback but not a periodic scheduler.

## Affected work

`backend/app/celery_app.py:17-37` schedules WB warehouse refresh, marking low-stock, FBS new-order polling, FBS status polling, and FBS stock reconciliation. The settings descriptions at `backend/app/core/settings.py:141-172` explicitly identify the FBS intervals as Celery Beat intervals.

Event-driven stock publication has an inline event-loop fallback, but errors are swallowed on the premise that periodic reconciliation is the safety net (`backend/app/services/fbs_stock_publish_service.py:33-47`). With no Beat deployment, that safety net is absent. API restart can also drop an in-process task after the warehouse transaction has already committed.

## Comparison and impact

The relevant worker, schedule, and Docker entrypoint paths have no diff between deployed `44fe72e…` and etalon `a39530c…`; static behavior is the same. Runtime proof remains staging-only.

The practical result is stale WB orders/statuses/stocks and missed low-stock/warehouse refresh work until an operator triggers a manual path or another movement happens to republish. The UI can continue to show healthy pages and `/health` can stay green while periodic work is absent.

## Minimal countermeasure

Deploy one worker and one scheduler from the same server SHA and configuration as the API, expose their liveness/last-success timestamps, and make deployment acceptance check API/worker/beat/schema identities separately. Until then, do not treat the API health endpoint as proof of background processing.
