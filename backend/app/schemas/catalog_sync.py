from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel

from app.models.background_job import BackgroundJob

CatalogSyncState = Literal["queued", "running", "succeeded", "failed"]


class CatalogSyncJobOut(BaseModel):
    id: str
    marketplace: Literal["wildberries", "ozon"]
    state: CatalogSyncState


def catalog_sync_state(status: str) -> CatalogSyncState:
    return cast(
        CatalogSyncState,
        {
            "pending": "queued",
            "running": "running",
            "done": "succeeded",
            "failed": "failed",
        }.get(status, "failed"),
    )


def catalog_sync_job_out(
    job: BackgroundJob, *, marketplace: Literal["wildberries", "ozon"]
) -> CatalogSyncJobOut:
    return CatalogSyncJobOut(
        id=str(job.id),
        marketplace=marketplace,
        state=catalog_sync_state(job.status),
    )
