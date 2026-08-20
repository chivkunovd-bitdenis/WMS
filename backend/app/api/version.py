from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/version", tags=["version"])


@router.get("")
async def version() -> dict[str, str]:
    return {
        "git_sha": os.environ.get("WMS_GIT_SHA", "unknown"),
        "artifact_digest": os.environ.get("WMS_ARTIFACT_DIGEST", "unknown"),
    }
