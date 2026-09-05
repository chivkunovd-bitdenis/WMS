from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_effective_seller_id,
    require_fbs_operator_access,
    require_fulfillment_admin,
)
from app.api.fbs_errors import envelope_from_exc, raise_fbs_http
from app.core.settings import settings
from app.db.session import get_db
from app.models.fbs_order import FbsOrder
from app.models.marketplace_account import MarketplaceAccount
from app.models.seller import Seller
from app.models.user import User
from app.services import background_job_service as job_svc
from app.services.background_job_service import JOB_TYPE_WILDBERRIES_MARKETPLACE_ORDERS_SYNC
from app.services.fbs_assembly_time_service import calculate_fbs_assembly_time
from app.services.fbs_cancellation_service import (
    FbsCancellationError,
    cancel_order,
    sync_seller_order_statuses,
)
from app.services.fbs_cancelled_after_pack_service import fetch_cancelled_after_pack_page
from app.services.fbs_order_history_service import FbsOrderHistoryError, order_history
from app.services.fbs_worklist_service import fetch_worklist_page
from app.services.marketplace_provider import (
    MarketplaceProviderError,
    provider_error_message,
)
from app.services.ozon_fbs_sync_service import sync_ozon_order_statuses, sync_ozon_orders
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
from app.services.wb_marketplace_orders_service import list_orders

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)
contract_router = APIRouter(prefix="/fbs", tags=["operations"])


class FbsOrderSyncBody(BaseModel):
    seller_id: uuid.UUID
    marketplace: Literal["wb", "ozon"] = "wb"
    # Ignored: WMS warehouse is resolved from WB warehouse bindings on each order row.
    warehouse_id: uuid.UUID | None = None


class FbsOrderSyncStatusesBody(BaseModel):
    seller_id: uuid.UUID
    marketplace: Literal["wb", "ozon"] = "wb"


class FbsOrderCancelBody(BaseModel):
    """Причина отмены — она нужна только Ozon и только там применяется.

    Тело необязательное: у метода отмены WB причины нет вовсе, а у Ozon без
    явного указания берётся «товар закончился на складе продавца» — та, по
    которой отменяет фулфилмент чаще всего. Экран сегодня тело не шлёт, и
    ломать его этим полем не нужно: отсутствие тела означает причину по
    умолчанию.
    """

    reason_id: int | None = None
    reason_message: str | None = None


class FbsOrderSyncStatusesOut(BaseModel):
    statuses_updated: int


class FbsOrderSyncOut(BaseModel):
    id: str
    status: str


class FbsAssemblyTimeOut(BaseModel):
    hours: float
    orders: int
    within_12_hours_percent: int
    within_24_hours_percent: int


class FbsCancelledProductOut(BaseModel):
    id: str | None
    name: str
    article: str | None
    wb_article: str | None
    size: str | None


class FbsCancelledSellerOut(BaseModel):
    id: str
    name: str


class FbsCancelledSupplyOut(BaseModel):
    id: str | None
    wb_supply_id: str | None
    name: str | None
    status: str | None


class FbsCancelledCargoPlaceOut(BaseModel):
    box_id: str
    box_number: int
    box_barcode: str
    trbx_id: str | None
    wb_trbx_id: str | None


class FbsCancelledAfterPackItemOut(BaseModel):
    order_id: str
    wb_order_id: int
    product: FbsCancelledProductOut
    seller: FbsCancelledSellerOut
    supply: FbsCancelledSupplyOut
    # Заказ может лежать в нескольких коробах (WMS-355) — список, а не одно
    # значение. Пустой список означает, что по коробам заказ не раскладывали.
    cargo_places: list[FbsCancelledCargoPlaceOut] = Field(default_factory=list)
    assembled_at: datetime | None
    picked_at: datetime | None
    packed_at: datetime | None
    cancelled_at: datetime
    cancellation_code: str
    cancellation_reason: str
    sticker_printed: bool
    sticker_printed_at: datetime | None
    supply_departed: bool | None


class FbsCancelledAfterPackPageOut(BaseModel):
    items: list[FbsCancelledAfterPackItemOut]
    total: int
    limit: int
    offset: int


async def _active_ozon_account_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> bool:
    stmt = select(MarketplaceAccount.id).where(
        MarketplaceAccount.tenant_id == tenant_id,
        MarketplaceAccount.seller_id == seller_id,
        MarketplaceAccount.marketplace == "ozon",
        MarketplaceAccount.is_active.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


@contract_router.get("/assembly-time", response_model=FbsAssemblyTimeOut)
async def get_fbs_assembly_time(
    period_from: Annotated[datetime, Query(alias="from")],
    period_to: Annotated[datetime, Query(alias="to")],
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> FbsAssemblyTimeOut:
    if seller_id is not None:
        seller = await session.get(Seller, seller_id)
        if seller is None or seller.tenant_id != user.tenant_id:
            raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    try:
        result = await calculate_fbs_assembly_time(
            session,
            user.tenant_id,
            period_from=period_from,
            period_to=period_to,
            seller_id=seller_id,
        )
    except ValueError as exc:
        if str(exc) == "invalid_period":
            raise_fbs_http(status.HTTP_400_BAD_REQUEST, "invalid_period")
        raise
    return FbsAssemblyTimeOut(
        hours=result.hours,
        orders=result.orders,
        within_12_hours_percent=result.within_12_hours_percent,
        within_24_hours_percent=result.within_24_hours_percent,
    )


@contract_router.get(
    "/cancelled-after-pack",
    response_model=FbsCancelledAfterPackPageOut,
)
async def get_fbs_cancelled_after_pack(
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    supply_id: Annotated[uuid.UUID | None, Query()] = None,
    cancelled_from: Annotated[datetime | None, Query()] = None,
    cancelled_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FbsCancelledAfterPackPageOut:
    filter_seller = seller_id if seller_id is not None else effective_seller_id
    if filter_seller is not None:
        seller = await session.get(Seller, filter_seller)
        if seller is None or seller.tenant_id != user.tenant_id:
            raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    try:
        page = await fetch_cancelled_after_pack_page(
            session,
            user.tenant_id,
            seller_id=filter_seller,
            supply_id=supply_id,
            cancelled_from=cancelled_from,
            cancelled_to=cancelled_to,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "supply_not_found":
            raise_fbs_http(status.HTTP_404_NOT_FOUND, code)
        if code == "invalid_period":
            raise_fbs_http(status.HTTP_400_BAD_REQUEST, code)
        raise
    return FbsCancelledAfterPackPageOut(
        items=[FbsCancelledAfterPackItemOut.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


async def _run_blocked_ozon_fake() -> None:
    """Локальный отказ, пока боевой транспорт Ozon выключен настройкой."""
    provider = build_ozon_provider(blocked_operation="fetch_orders")
    try:
        await provider.fetch_orders(client_id="fake", api_key="fake")
    except MarketplaceProviderError as exc:
        raise_fbs_http(
            status.HTTP_403_FORBIDDEN,
            "ozon_account_blocked",
            message=provider_error_message(exc),
        )


def _raise_ozon_provider_http(exc: MarketplaceProviderError) -> None:
    raise_fbs_http(
        status.HTTP_403_FORBIDDEN if exc.is_account_blocked else status.HTTP_502_BAD_GATEWAY,
        "ozon_account_blocked" if exc.is_account_blocked else exc.code,
        message=provider_error_message(exc),
    )


class FbsWorklistSellerOut(BaseModel):
    id: str
    name: str


class FbsWorklistWarehouseOut(BaseModel):
    id: int | str
    name: str | None


class FbsWorklistProductOut(BaseModel):
    id: str | None
    name: str
    image_url: str | None
    seller_article: str | None
    wb_article: int | None
    barcode: str | None
    sku: str | None = None
    chrt_id: int | None = None
    category: str | None = None
    color: str | None = None
    size: str | None


class FbsWorklistInventoryLocationOut(BaseModel):
    id: str
    code: str
    available_unpacked: int


class FbsWorklistInventoryOut(BaseModel):
    available_unpacked: int
    locations: list[FbsWorklistInventoryLocationOut]


class FbsWorklistMetadataStateOut(BaseModel):
    kind: str
    status: str
    reason: str | None
    source: str | None = None
    # Хвост кода маркировки для экрана упаковки. Без явного поля pydantic молча
    # выбрасывал его из ответа: сервис клал значение, схема снимала, и колонка «ЧЗ»
    # на экране всегда показывала прочерк.
    value_tail: str | None = None


class FbsWorklistMetadataOut(BaseModel):
    required: list[str]
    optional: list[str]
    states: list[FbsWorklistMetadataStateOut]
    delivery_allowed: bool
    last_checked_at: str | None


class FbsWorklistStickerOut(BaseModel):
    code: str | None
    status: str
    asset_url: str | None
    applied_at: str | None


class FbsWorklistPickOut(BaseModel):
    status: str
    location_code: str | None
    picked_at: str | None


class FbsWorklistPackOut(BaseModel):
    status: str
    packed_at: str | None


class FbsWorklistBlockerOut(BaseModel):
    code: str
    message: str


class FbsWorklistPositionOut(BaseModel):
    product_id: str | None
    name: str
    seller_article: str | None
    sku: str | None
    quantity: int
    reserved_quantity: int
    picked_quantity: int


class FbsWorklistOrderOut(BaseModel):
    id: str
    marketplace: str = "wb"
    external_order_id: str | None = None
    wb_order_id: int
    status: str
    wb_status: str | None
    supplier_status: str | None
    seller: FbsWorklistSellerOut
    wb_warehouse: FbsWorklistWarehouseOut
    wms_warehouse: FbsWorklistWarehouseOut
    product: FbsWorklistProductOut
    positions: list[FbsWorklistPositionOut]
    inventory: FbsWorklistInventoryOut
    buyer_type: str
    cargo_type: str
    can_pvz: bool
    # Маршрут сдачи Ozon: название метода доставки, по которому потом собирается
    # отгрузка (WMS-358). У Wildberries маршрут виден из `can_pvz`, поэтому там
    # поле пустое и колонка рисуется по-старому.
    delivery_route: str | None = None
    metadata: FbsWorklistMetadataOut
    sticker: FbsWorklistStickerOut
    pick: FbsWorklistPickOut
    pack: FbsWorklistPackOut
    created_at_wb: str
    deadline_at: str
    supply_id: str | None
    selection_blockers: list[FbsWorklistBlockerOut]


class FbsWorklistWarehouseOptionOut(BaseModel):
    id: str
    name: str
    wb_warehouse: FbsWorklistWarehouseOut


class FbsWorklistPageOut(BaseModel):
    items: list[FbsWorklistOrderOut]
    next_cursor: str | None
    server_now: str
    warehouse_options: list[FbsWorklistWarehouseOptionOut]


class FbsOrderOut(BaseModel):
    id: str
    marketplace: str = "wb"
    external_order_id: str | None = None
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
    supplier_status: str | None
    created_at_wb: str
    deadline_at: str
    mapping_status: str
    reserve_status: str
    created_at: str
    updated_at: str


def _order_out(order: FbsOrder) -> FbsOrderOut:
    return FbsOrderOut(
        id=str(order.id),
        marketplace=order.marketplace,
        external_order_id=order.external_order_id,
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
        supplier_status=order.supplier_status,
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
        # КРИТ-2 (HANDOFF-POLISH.md, пул 1, п.3): используем словарь fbs_errors.py вместо
        # сырой строки в detail — фронт получает {code, message} и показывает человеческий текст.
        raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    if body.marketplace == "ozon":
        if not await _active_ozon_account_exists(session, user.tenant_id, body.seller_id):
            return FbsOrderSyncOut(id="", status="skipped")
        if not ozon_live_api_enabled():
            await _run_blocked_ozon_fake()
            return FbsOrderSyncOut(id="", status="skipped")
        async with httpx.AsyncClient() as http_client:
            try:
                await sync_ozon_orders(
                    session,
                    user.tenant_id,
                    body.seller_id,
                    build_ozon_provider(),
                    http_client,
                )
            except MarketplaceProviderError as exc:
                _raise_ozon_provider_http(exc)
        return FbsOrderSyncOut(id="", status="done")
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
        background_tasks.add_task(job_svc.run_wildberries_marketplace_orders_sync_job, job.id)
    return FbsOrderSyncOut(id=str(job.id), status=job.status)


@router.get("/worklist", response_model=FbsWorklistPageOut)
async def get_fbs_orders_worklist(
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    marketplace: Annotated[str | None, Query(pattern="^(wb|ozon)$")] = None,
    status_group: Annotated[str | None, Query()] = None,
    wb_warehouse_id: Annotated[int | None, Query(gt=0)] = None,
    search: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[str | None, Query()] = None,
) -> FbsWorklistPageOut:
    filter_seller = seller_id if seller_id is not None else effective_seller_id
    if filter_seller is not None:
        seller = await session.get(Seller, filter_seller)
        if seller is None or seller.tenant_id != user.tenant_id:
            raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    try:
        page = await fetch_worklist_page(
            session,
            user.tenant_id,
            seller_id=filter_seller,
            marketplace=marketplace,
            status_group=status_group,
            wb_warehouse_id=wb_warehouse_id,
            search=search,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"invalid_cursor", "invalid_status_group"}:
            raise_fbs_http(status.HTTP_400_BAD_REQUEST, code)
        raise
    return FbsWorklistPageOut.model_validate(
        {
            "items": page.items,
            "next_cursor": page.next_cursor,
            "server_now": page.server_now,
            "warehouse_options": page.warehouse_options,
        }
    )


@router.get("/{order_id}/history")
async def get_fbs_order_history(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Хронология заказа: подбор, упаковка, коды, печать, поставка.

    Собирается из уже существующих записей, поэтому работает и по старым
    заказам, а не только по тем, что появятся после выкатки.
    """
    try:
        return await order_history(session, tenant_id=user.tenant_id, order_id=order_id)
    except FbsOrderHistoryError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=list[FbsOrderOut])
async def get_fbs_orders(
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
    detail = envelope_from_exc(exc)
    if exc.code == "order_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code in ("order_not_cancellable", "marketplace_not_supported"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code in ("seller_not_found", "missing_marketplace_token", "ozon_not_connected"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    # Отказы Ozon — не наша внутренняя ошибка, и отдавать по ним 500 значит
    # спрятать от оператора причину. «Причина отмены недоступна» — это конфликт
    # состояния, «транспорт выключен» — временная недоступность, остальное
    # пришло от маркетплейса.
    if exc.code in (
        "ozon_cancel_reason_unavailable",
        "ozon_cancel_not_available",
        "ozon_cancel_reason_message_required",
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code == "ozon_live_cancel_blocked":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if exc.code.startswith("wb_") or exc.code.startswith("ozon_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


@router.patch("/{order_id}/cancel", response_model=FbsOrderOut)
async def cancel_fbs_order(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: FbsOrderCancelBody | None = None,
) -> FbsOrderOut:
    async with httpx.AsyncClient() as http_client:
        try:
            order = await cancel_order(
                session,
                user.tenant_id,
                order_id,
                http_client,
                actor_user_id=user.id,
                reason_id=body.reason_id if body is not None else None,
                reason_message=body.reason_message if body is not None else None,
            )
        except FbsCancellationError as exc:
            _raise_cancellation_http(exc)
    await session.commit()
    await session.refresh(order)
    return _order_out(order)


@router.post("/sync-statuses", response_model=FbsOrderSyncStatusesOut)
async def sync_fbs_order_statuses(
    body: FbsOrderSyncStatusesBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsOrderSyncStatusesOut:
    seller = await session.get(Seller, body.seller_id)
    if seller is None or seller.tenant_id != user.tenant_id:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, "seller_not_found")
    if body.marketplace == "ozon":
        if not await _active_ozon_account_exists(session, user.tenant_id, body.seller_id):
            return FbsOrderSyncStatusesOut(statuses_updated=0)
        if not ozon_live_api_enabled():
            await _run_blocked_ozon_fake()
            return FbsOrderSyncStatusesOut(statuses_updated=0)
        async with httpx.AsyncClient() as http_client:
            try:
                ozon_updated = await sync_ozon_order_statuses(
                    session,
                    user.tenant_id,
                    body.seller_id,
                    build_ozon_provider(),
                    http_client,
                )
            except MarketplaceProviderError as exc:
                _raise_ozon_provider_http(exc)
        return FbsOrderSyncStatusesOut(statuses_updated=ozon_updated)
    async with httpx.AsyncClient() as http_client:
        try:
            updated = await sync_seller_order_statuses(
                session,
                user.tenant_id,
                body.seller_id,
                http_client,
                actor_user_id=user.id,
            )
        except FbsCancellationError as exc:
            _raise_cancellation_http(exc)
    await session.commit()
    return FbsOrderSyncStatusesOut(statuses_updated=updated)


# Короткий путь из продуктового контракта добавляется тем же экспортируемым
# роутером, поэтому менять глобальную сборку приложения не требуется.
router.routes.extend(contract_router.routes)
