from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.user import User
from app.services import inventory_service as inv_svc

router = APIRouter(
    prefix="/operations/stock-transfers",
    tags=["operations"],
)


class StockTransferCreate(BaseModel):
    from_storage_location_id: uuid.UUID
    to_storage_location_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)


class StockTransferOut(BaseModel):
    ok: bool = True


def _http_from_value_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg == "storage location not found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="location_not_found",
        )
    if msg == "product not found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_not_found",
        )
    if msg == "insufficient stock":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="insufficient_stock",
        )
    if msg == "from and to must differ":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="same_location",
        )
    if msg == "locations must be in the same warehouse":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="different_warehouse",
        )
    if msg == "quantity must be positive":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_qty",
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=msg,
    )


@router.post("", response_model=StockTransferOut, status_code=status.HTTP_200_OK)
async def create_stock_transfer(
    body: StockTransferCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StockTransferOut:
    try:
        await inv_svc.apply_stock_transfer(
            session,
            user.tenant_id,
            from_storage_location_id=body.from_storage_location_id,
            to_storage_location_id=body.to_storage_location_id,
            product_id=body.product_id,
            quantity=body.quantity,
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise _http_from_value_error(exc) from None
    return StockTransferOut()
