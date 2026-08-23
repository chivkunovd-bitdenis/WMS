"""Celery application (broker from settings; worker: `celery -A app.celery_app worker`)."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.settings import settings

_broker = settings.celery_broker_url or "memory://"
celery_app = Celery(
    "wms",
    broker=_broker,
    include=["app.tasks.background_jobs", "app.tasks.billing_tasks"],
)
celery_app.conf.task_ignore_result = True
celery_app.conf.timezone = "Europe/Moscow"
celery_app.conf.enable_utc = False
celery_app.conf.beat_schedule = {
    "billing-invoices-daily": {
        "task": "wms.billing_invoices_daily",
        "schedule": crontab(hour=2, minute=30),
    },
    "wb-mp-warehouses-daily": {
        "task": "wms.wb_mp_warehouses_daily_sync",
        "schedule": crontab(hour=3, minute=0),
    },
    "marking-low-stock": {
        "task": "wms.marking_low_stock",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "fbs-orders-autopoll": {
        "task": "wms.fbs_orders_autopoll",
        "schedule": float(settings.fbs_poll_interval_sec),
    },
    "fbs-orders-full-reconcile": {
        "task": "wms.fbs_orders_full_reconcile",
        "schedule": crontab(hour="*/6", minute=30),
    },
    "fbs-order-statuses-autopoll": {
        "task": "wms.fbs_order_statuses_autopoll",
        "schedule": float(settings.fbs_statuses_sync_interval_sec),
    },
    "fbs-stock-reconcile": {
        "task": "wms.fbs_stock_reconcile",
        "schedule": float(settings.fbs_stock_reconcile_interval_sec),
    },
}
