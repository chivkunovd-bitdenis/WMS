from __future__ import annotations

import asyncio

from app.celery_app import celery_app
from app.services.developer_request_sync import sync_developer_requests


@celery_app.task(name="wms.developer_requests_sync")
def sync_developer_requests_task() -> None:
    asyncio.run(sync_developer_requests())
