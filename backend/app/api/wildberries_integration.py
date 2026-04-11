from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_fulfillment_admin
from app.core.settings import settings
from app.models.user import User

router = APIRouter(prefix="/integrations/wildberries", tags=["integrations"])


class WildberriesStatusOut(BaseModel):
    content_api_base: str
    supplies_api_base: str
    import_only: bool = True


@router.get("/status", response_model=WildberriesStatusOut)
async def wildberries_status(
    _: Annotated[User, Depends(require_fulfillment_admin)],
) -> WildberriesStatusOut:
    """Публичная конфигурация (без токенов): базы URL для импорта WB."""
    return WildberriesStatusOut(
        content_api_base=settings.wildberries_content_api_base,
        supplies_api_base=settings.wildberries_supplies_api_base,
    )
