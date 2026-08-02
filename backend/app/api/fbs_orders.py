from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_effective_seller_id, require_fulfillment_admin
from app.core.settings import settings
from app.db.session import get_db
from app.models.fbs_order import FbsOrder
from app.models.seller import Seller
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC
from app.services.fbs_cancellation_service import (
    FbsCancellationError,
    cancel_order,
    sync_seller_order_statuses,
)
from app.services.wb_marketplace_orders_service import list_orders

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)


class FbsOrderSyncBody(BaseModel):
    seller_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None


class FbsOrderSyncStatusesBody(BaseModel):
    seller_id: uuid.UUID


class FbsOrderSyncStatusesOut(BaseModel):
    statuses_updated: int


class FbsOrderSyncOut(BaseModel):
    id: str
    status: str


class FbsOrderOut(BaseModel):
    id: str
    seller_id: str
    warehouse_id: str | None
    product_id: str | None
    wb_order_id: int
    wb_rid: str | None
    wb_nm_id: int | None
    wb_chrt_id: int | None
    wb_article: str | None
    wb_barcode: str | None
    price: int | None
    is_legal: bool
    cargo_type: str | None
    wb_office_id: int | None
    wb_warehouse_id: int | None
    can_pvz: bool
    supply_id: str | None
    trbx_id: str | None
    status: str
    wb_status: str | None
    created_at_wb: str
    deadline_at: str
    mapping_status: str
    reserve_status: str
    created_at: str
    updated_at: str


def _order_out(order: FbsOrder) -> FbsOrderOut:
    return FbsOrderOut(
        id=str(order.id),
        seller_id=str(order.seller_id),
        warehouse_id=str(order.warehouse_id) if order.warehouse_id is not None else None,
        product_id=str(order.product_id) if order.product_id is not None else None,
        wb_order_id=order.wb_order_id,
        wb_rid=order.wb_rid,
        wb_nm_id=order.wb_nm_id,
        wb_chrt_id=order.wb_chrt_id,
        wb_article=order.wb_article,
        wb_barcode=order.wb_barcode,
        price=order.price,
        is_legal=order.is_legal,
        cargo_type=order.cargo_type,
        wb_office_id=order.wb_office_id,
        wb_warehouse_id=order.wb_warehouse_id,
        can_pvz=order.can_pvz,
        supply_id=str(order.supply_id) if order.supply_id is not None else None,
        trbx_id=str(order.trbx_id) if order.trbx_id is not None else None,
        status=order.status,
        wb_status=order.wb_status,
        created_at_wb=order.created_at_wb.isoformat(),
        deadline_at=order.deadline_at.isoformat(),
        mapping_status=order.mapping_status,
        reserve_status=order.reserve_status,
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
    )


@router.post(
    "/sync",
    response_model=FbsOrderSyncOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_fbs_orders_sync(
    body: FbsOrderSyncBody,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderSyncOut:
    seller = await session.get(Seller, body.seller_id)
    if seller is None or seller.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="seller_not_found",
        )
    payload: dict[str, Any] = {"seller_id": str(body.seller_id)}
    job = await job_svc.create_pending_job(
        session,
        user.tenant_id,
        job_type=JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC,
        payload_json=payload,
    )
    if settings.celery_broker_url:
        from app.tasks.background_jobs import run_wildberries_marketplace_orders_sync_task

        run_wildberries_marketplace_orders_sync_task.delay(str(job.id))
    else:
        background_tasks.add_task(
            job_svc.run_wildberries_marketplace_orders_sync_job, job.id
        )
    return FbsOrderSyncOut(id=str(job.id), status=job.status)


@router.get("", response_model=list[FbsOrderOut])
async def get_fbs_orders(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FbsOrderOut]:
    filter_seller = seller_id if seller_id is not None else effective_seller_id
    if filter_seller is not None:
        seller = await session.get(Seller, filter_seller)
        if seller is None or seller.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            )
    rows = await list_orders(
        session,
        user.tenant_id,
        seller_id=filter_seller,
        limit=limit,
        offset=offset,
    )
    return [_order_out(row) for row in rows]


def _raise_cancellation_http(exc: FbsCancellationError) -> None:
    if exc.code == "order_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "order_not_cancellable":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code in ("seller_not_found", "missing_marketplace_token"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.patch("/{order_id}/cancel", response_model=FbsOrderOut)
async def cancel_fbs_order(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderOut:
    async with httpx.AsyncClient() as http_client:
        try:
            order = await cancel_order(session, user.tenant_id, order_id, http_client)
        except FbsCancellationError as exc:
            _raise_cancellation_http(exc)
    await session.commit()
    await session.refresh(order)
    return _order_out(order)


@router.post("/sync-statuses", response_model=FbsOrderSyncStatusesOut)
async def sync_fbs_order_statuses(
    body: FbsOrderSyncStatusesBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderSyncStatusesOut:
    seller = await session.get(Seller, body.seller_id)
    if seller is None or seller.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="seller_not_found",
        )
    async with httpx.AsyncClient() as http_client:
        try:
            updated = await sync_seller_order_statuses(
                session,
                user.tenant_id,
                body.seller_id,
                http_client,
            )
        except FbsCancellationError as exc:
            _raise_cancellation_http(exc)
    await session.commit()
    return FbsOrderSyncStatusesOut(statuses_updated=updated)
