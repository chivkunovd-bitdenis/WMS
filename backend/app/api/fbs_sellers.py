from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access, require_fulfillment_admin
from app.api.fbs_errors import envelope_from_exc, raise_fbs_http
from app.core.settings import settings
from app.db.session import get_db
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.seller import Seller
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services import fbs_seller_warehouse_service as wh_svc
from app.services import fbs_warehouse_binding_service as binding_svc
from app.services.background_job_service import JOB_TYPE_FBS_STOCK_SYNC
from app.services.fbs_autopoll_service import (
    get_binding_stock_sync_status,
    sync_seller_stocks,
)
from app.services.fbs_stock_sync_service import FbsStockSyncError

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
    detail = envelope_from_exc(exc)
    if exc.code in {
        "seller_not_found",
        "warehouse_not_found",
        "binding_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "invalid_wb_warehouse_id":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if exc.code in {"wms_warehouse_already_bound", "active_fbs_reservations"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _raise_from_stock_sync(exc: FbsStockSyncError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code == "binding_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _enqueue_fbs_stock_sync_job(job_id: uuid.UUID) -> None:
    from app.tasks.background_jobs import run_fbs_stock_sync_task

    run_fbs_stock_sync_task.delay(str(job_id))


class FbsStockSyncBody(BaseModel):
    wb_warehouse_id: int | None = None


class FbsStockSyncJobOut(BaseModel):
    id: str
    status: str


class FbsStockSyncResultOut(BaseModel):
    bindings_processed: int
    products_targeted: int
    products_confirmed: int
    products_zeroed: int
    conflicts: int
    errors: int
    binding_errors: int


class FbsStockSyncStatusItemOut(BaseModel):
    chrt_id: int
    product_id: str | None
    target: int | None
    confirmed: int | None
    status: str
    error: str | None
    timestamp: datetime


class FbsStockSyncStatusOut(BaseModel):
    wb_warehouse_id: int
    binding_last_sync_at: datetime | None
    binding_last_sync_status: str | None
    binding_last_error_code: str | None
    items: list[FbsStockSyncStatusItemOut]


@router.get("/{seller_id}/warehouses", response_model=list[FbsSellerWarehouseOut])
async def list_fbs_seller_warehouses(
    seller_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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


@router.post(
    "/{seller_id}/stocks/sync",
    response_model=FbsStockSyncResultOut | FbsStockSyncJobOut,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_202_ACCEPTED: {"model": FbsStockSyncJobOut}},
)
async def start_fbs_stock_sync(
    seller_id: uuid.UUID,
    body: FbsStockSyncBody,
    response: Response,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsStockSyncResultOut | FbsStockSyncJobOut:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != user.tenant_id:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    if body.wb_warehouse_id is not None and body.wb_warehouse_id <= 0:
        raise_fbs_http(status.HTTP_400_BAD_REQUEST, "invalid_wb_warehouse_id")

    if settings.celery_broker_url:
        payload: dict[str, Any] = {"seller_id": str(seller_id)}
        if body.wb_warehouse_id is not None:
            payload["wb_warehouse_id"] = body.wb_warehouse_id
        job = await job_svc.create_pending_job(
            session,
            user.tenant_id,
            job_type=JOB_TYPE_FBS_STOCK_SYNC,
            payload_json=payload,
        )
        _enqueue_fbs_stock_sync_job(job.id)
        response.status_code = status.HTTP_202_ACCEPTED
        return FbsStockSyncJobOut(id=str(job.id), status=job.status)

    async with httpx.AsyncClient() as http_client:
        result = await sync_seller_stocks(
            session,
            user.tenant_id,
            seller_id,
            http_client,
            wb_warehouse_id=body.wb_warehouse_id,
        )
    return FbsStockSyncResultOut(
        bindings_processed=result.bindings_processed,
        products_targeted=result.products_targeted,
        products_confirmed=result.products_confirmed,
        products_zeroed=result.products_zeroed,
        conflicts=result.conflicts,
        errors=result.errors,
        binding_errors=result.binding_errors,
    )


@router.get(
    "/{seller_id}/stocks/sync-status",
    response_model=FbsStockSyncStatusOut,
)
async def get_fbs_stock_sync_status(
    seller_id: uuid.UUID,
    wb_warehouse_id: Annotated[int, Query(gt=0)],
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsStockSyncStatusOut:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != user.tenant_id:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    try:
        binding, items = await get_binding_stock_sync_status(
            session,
            user.tenant_id,
            seller_id,
            wb_warehouse_id,
        )
    except FbsStockSyncError as exc:
        _raise_from_stock_sync(exc)
    return FbsStockSyncStatusOut(
        wb_warehouse_id=binding.wb_warehouse_id,
        binding_last_sync_at=binding.last_sync_at,
        binding_last_sync_status=binding.last_sync_status,
        binding_last_error_code=binding.last_error_code,
        items=[
            FbsStockSyncStatusItemOut(
                chrt_id=item.chrt_id,
                product_id=str(item.product_id) if item.product_id is not None else None,
                target=item.last_target_amount,
                confirmed=item.last_confirmed_amount,
                status=item.status,
                error=item.last_error_code,
                timestamp=item.updated_at,
            )
            for item in items
        ],
    )
