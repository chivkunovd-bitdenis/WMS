from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.user import User
from app.services import fbs_seller_warehouse_service as wh_svc
from app.services import fbs_warehouse_binding_service as binding_svc

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


class FbsWarehouseBindingOut(BaseModel):
    id: str
    wb_warehouse_id: int
    wms_warehouse_id: str
    is_active: bool
    stock_sync_enabled: bool
    last_sync_status: str | None = None
    last_sync_at: datetime | None = None
    last_error_code: str | None = None


class FbsWarehouseBindingUpsert(BaseModel):
    wms_warehouse_id: uuid.UUID
    stock_sync_enabled: bool = True


def _binding_out(row: FbsWarehouseBinding) -> FbsWarehouseBindingOut:
    return FbsWarehouseBindingOut(
        id=str(row.id),
        wb_warehouse_id=row.wb_warehouse_id,
        wms_warehouse_id=str(row.wms_warehouse_id),
        is_active=row.is_active,
        stock_sync_enabled=row.stock_sync_enabled,
        last_sync_status=row.last_sync_status,
        last_sync_at=row.last_sync_at,
        last_error_code=row.last_error_code,
    )


def _raise_from_binding_service(exc: binding_svc.FbsWarehouseBindingError) -> None:
    if exc.code in {
        "seller_not_found",
        "warehouse_not_found",
        "binding_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "invalid_wb_warehouse_id":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    if exc.code in {"wms_warehouse_already_bound", "active_fbs_reservations"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
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


@router.get(
    "/{seller_id}/warehouse-bindings",
    response_model=list[FbsWarehouseBindingOut],
)
async def list_fbs_warehouse_bindings(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsWarehouseBindingOut]:
    try:
        rows = await binding_svc.list_bindings(session, user.tenant_id, seller_id)
    except binding_svc.FbsWarehouseBindingError as exc:
        _raise_from_binding_service(exc)
    return [_binding_out(row) for row in rows]


@router.put(
    "/{seller_id}/warehouse-bindings/{wb_warehouse_id}",
    response_model=FbsWarehouseBindingOut,
)
async def upsert_fbs_warehouse_binding(
    seller_id: uuid.UUID,
    wb_warehouse_id: Annotated[int, Path(gt=0)],
    body: FbsWarehouseBindingUpsert,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWarehouseBindingOut:
    try:
        row = await binding_svc.upsert_binding(
            session,
            user.tenant_id,
            seller_id,
            wb_warehouse_id,
            wms_warehouse_id=body.wms_warehouse_id,
            stock_sync_enabled=body.stock_sync_enabled,
        )
    except binding_svc.FbsWarehouseBindingError as exc:
        _raise_from_binding_service(exc)
    return _binding_out(row)


@router.delete(
    "/{seller_id}/warehouse-bindings/{wb_warehouse_id}",
    response_model=FbsWarehouseBindingOut,
)
async def disable_fbs_warehouse_binding(
    seller_id: uuid.UUID,
    wb_warehouse_id: Annotated[int, Path(gt=0)],
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWarehouseBindingOut:
    try:
        row = await binding_svc.disable_binding(
            session, user.tenant_id, seller_id, wb_warehouse_id
        )
    except binding_svc.FbsWarehouseBindingError as exc:
        _raise_from_binding_service(exc)
    return _binding_out(row)
