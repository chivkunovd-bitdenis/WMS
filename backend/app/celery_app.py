"""Celery application (broker from settings; worker: `celery -A app.celery_app worker`)."""

from __future__ import annotations

from celery import Celery

from app.core.settings import settings

_broker = settings.celery_broker_url or "memory://"
celery_app = Celery(
    "wms",
    broker=_broker,
    include=["app.tasks.background_jobs"],
)
celery_app.conf.task_ignore_result = True
