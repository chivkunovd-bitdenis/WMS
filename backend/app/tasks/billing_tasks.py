from __future__ import annotations

from app.celery_app import celery_app


@celery_app.task(name="wms.billing_invoices_daily")
def run_billing_invoices_daily_task() -> None:
    """Compatibility no-op for messages queued before Wave 4 removed beat."""
    return None


async def _run_billing_invoices_daily() -> None:
    """Compatibility no-op for older application messages."""
    return None
