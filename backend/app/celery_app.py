# ruff: noqa: RUF003
"""Celery application (broker from settings; worker: `celery -A app.celery_app worker`)."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.logging_setup import setup_outbound_http_logging
from app.core.settings import settings

_broker = settings.celery_broker_url or "memory://"
celery_app = Celery(
    "wms",
    broker=_broker,
    include=["app.tasks.background_jobs"],
)
celery_app.conf.task_ignore_result = True

# Автоопрос ходит в WB из воркера, а не из API, — там lifespan не выполняется,
# поэтому лог исходящих включаем и здесь.
setup_outbound_http_logging()
celery_app.conf.beat_schedule = {
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
    "fbs-order-statuses-autopoll": {
        "task": "wms.fbs_order_statuses_autopoll",
        "schedule": float(settings.fbs_statuses_sync_interval_sec),
    },
    "fbs-stock-reconcile": {
        "task": "wms.fbs_stock_reconcile",
        "schedule": float(settings.fbs_stock_reconcile_interval_sec),
    },
}
