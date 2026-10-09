from __future__ import annotations

from fastapi import APIRouter

from app.core.settings import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    return {"status": "ok", "app_env": settings.app_env}
