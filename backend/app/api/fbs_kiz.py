from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc
from app.db.session import get_db
from app.models.user import User
from app.services import fbs_kiz_service as kiz_svc

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)


class FbsKizProductOut(BaseModel):
    name: str
    image_url: str | None
    barcode: str | None
    seller_article: str | None


class FbsKizCurrentOut(BaseModel):
    masked: str
    meta_status: str
    from_pool: bool


class FbsKizLookupOut(BaseModel):
    order_id: str
    wb_order_id: int
    product: FbsKizProductOut
    current_kiz: FbsKizCurrentOut | None
    needs_confirmation: bool
    can_bind: bool
    block_reason: str | None


def _raise_from_service(exc: kiz_svc.FbsKizError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code == "sticker_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "order_frozen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _lookup_out(result: kiz_svc.FbsKizLookup) -> FbsKizLookupOut:
    return FbsKizLookupOut(
        order_id=str(result.order_id),
        wb_order_id=result.wb_order_id,
        product=FbsKizProductOut(
            name=result.product.name,
            image_url=result.product.image_url,
            barcode=result.product.barcode,
            seller_article=result.product.seller_article,
        ),
        current_kiz=(
            FbsKizCurrentOut(
                masked=result.current_kiz.masked,
                meta_status=result.current_kiz.meta_status,
                from_pool=result.current_kiz.from_pool,
            )
            if result.current_kiz is not None
            else None
        ),
        needs_confirmation=result.needs_confirmation,
        can_bind=result.can_bind,
        block_reason=result.block_reason,
    )


@router.get("/kiz/lookup", response_model=FbsKizLookupOut)
async def lookup_fbs_order_by_sticker(
    supply_id: uuid.UUID,
    sticker: Annotated[str, Query(min_length=1, max_length=512)],
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsKizLookupOut:
    try:
        result = await kiz_svc.lookup_order_by_sticker(
            session,
            user.tenant_id,
            supply_id,
            sticker,
        )
    except kiz_svc.FbsKizError as exc:
        _raise_from_service(exc)
    return _lookup_out(result)
