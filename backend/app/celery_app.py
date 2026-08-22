"""Celery application (broker from settings; worker: `celery -A app.celery_app worker`)."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.settings import settings

_broker = settings.celery_broker_url or "memory://"
celery_app = Celery(
    "wms",
    broker=_broker,
    include=["app.tasks.background_jobs"],
)
celery_app.conf.task_ignore_result = True
celery_app.conf.task_routes = {
    "wms.marking_label_tape": {"queue": "print"},
}
celery_app.conf.beat_schedule = {
    "wb-mp-warehouses-daily": {
        "task": "wms.wb_mp_warehouses_daily_sync",
        "schedule": crontab(hour=3, minute=0),
    },
    "marking-low-stock": {
        "task": "wms.marking_low_stock",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "purge-expired-label-tape-assets": {
        "task": "wms.purge_expired_label_tape_assets",
        "schedule": 3600.0,
    },
    "wb-orders-new": {
        "task": "wms.wb_orders_new_dispatch",
        "schedule": 180.0,
    },
    "wb-orders-reconcile": {
        "task": "wms.wb_orders_reconcile_dispatch",
        "schedule": 3600.0,
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
