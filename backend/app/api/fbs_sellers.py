from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.user import User
from app.services import fbs_seller_warehouse_service as wh_svc

router = APIRouter(prefix="/operations/fbs-sellers", tags=["operations"])


class FbsSellerWarehouseOut(BaseModel):
    id: int | None = None
    name: str | None = None
    address: str | None = None
    officeId: int | None = None
    cargoType: int | None = None
    deliveryType: int | None = None
    isDeleting: bool | None = None
    isProcessing: bool | None = None


class FbsSellerOfficeOut(BaseModel):
    id: int | None = None
    officeId: int | None = None
    name: str | None = None
    city: str | None = None
    address: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    selected: bool | None = None


def _map_warehouse(row: dict[str, Any]) -> FbsSellerWarehouseOut:
    return FbsSellerWarehouseOut(**row)


def _map_office(row: dict[str, Any]) -> FbsSellerOfficeOut:
    return FbsSellerOfficeOut(**row)


def _raise_from_service(exc: wh_svc.FbsSellerWarehouseError) -> None:
    if exc.code == "seller_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.get("/{seller_id}/warehouses", response_model=list[FbsSellerWarehouseOut])
async def list_fbs_seller_warehouses(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsSellerWarehouseOut]:
    async with httpx.AsyncClient() as http_client:
        try:
            rows = await wh_svc.list_seller_warehouses(
                session, user.tenant_id, seller_id, http_client
            )
        except wh_svc.FbsSellerWarehouseError as exc:
            _raise_from_service(exc)
    return [_map_warehouse(row) for row in rows]


@router.get("/{seller_id}/offices", response_model=list[FbsSellerOfficeOut])
async def list_fbs_seller_offices(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsSellerOfficeOut]:
    async with httpx.AsyncClient() as http_client:
        try:
            rows = await wh_svc.list_seller_offices(
                session, user.tenant_id, seller_id, http_client
            )
        except wh_svc.FbsSellerWarehouseError as exc:
            _raise_from_service(exc)
    return [_map_office(row) for row in rows]
