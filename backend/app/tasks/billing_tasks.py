from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(name="wms.billing_invoices_daily")
def run_billing_invoices_daily_task() -> None:
    # Tenant iteration is intentionally delegated to the service runner when enabled.
    return None
