"""FBS print assets API — binary content and applied confirmation.

Canonical print contract (BACKEND_CONTRACT.md §10):
- POST /operations/fbs-supplies/{id}/print-assets → batch metadata + URLs
- GET /operations/fbs-print-assets/{id}/content → authorized binary
- POST /operations/fbs-print-assets/{id}/applied → applied audit

Legacy POST …/stickers and …/trbx/stickers that expose sticker_file paths are
deprecated compatibility endpoints only (see fbs_supplies.py).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc
from app.db.session import get_db
from app.models.user import User
from app.services.fbs_print_asset_service import (
    FbsPrintAssetError,
    confirm_asset_applied,
    get_asset_binary_content,
    map_print_asset,
)

router = APIRouter(prefix="/operations/fbs-print-assets", tags=["operations"])


class FbsPrintAssetAppliedBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsPrintAssetOut(BaseModel):
    id: str
    kind: str
    status: str
    content_type: str | None
    width_mm: int | None
    height_mm: int | None
    preview_url: str | None
    download_url: str | None
    checksum: str | None
    applied_at: str | None
    error: dict[str, str] | None = None


def _raise_from_print_asset_service(exc: FbsPrintAssetError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code in {
        "asset_not_found",
        "asset_not_ready",
        "supply_not_found",
        "order_not_in_supply",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code in {"invalid_kind", "invalid_order_ids"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=detail,
    )


@router.get("/{asset_id}/content")
async def get_fbs_print_asset_content(
    asset_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        png_bytes, content_type, _asset = await get_asset_binary_content(
            session,
            user.tenant_id,
            asset_id,
            user_id=user.id,
            record_print_opened=True,
        )
    except FbsPrintAssetError as exc:
        _raise_from_print_asset_service(exc)
    await session.commit()
    return Response(content=png_bytes, media_type=content_type)


@router.post("/{asset_id}/applied", response_model=FbsPrintAssetOut)
async def confirm_fbs_print_asset_applied(
    asset_id: uuid.UUID,
    body: FbsPrintAssetAppliedBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintAssetOut:
    try:
        asset = await confirm_asset_applied(
            session,
            user.tenant_id,
            asset_id,
            user_id=user.id,
            idempotency_key=body.idempotency_key,
        )
    except FbsPrintAssetError as exc:
        _raise_from_print_asset_service(exc)
    await session.commit()
    mapped = map_print_asset(asset)
    return FbsPrintAssetOut(**mapped)
