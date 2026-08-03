from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.user import User
from app.services import fbs_packaging_integration_service as pack_int_svc
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services import fbs_supply_service as supply_svc

router = APIRouter(prefix="/operations/fbs-supplies", tags=["operations"])


class FbsSupplyCreateBody(BaseModel):
    seller_id: uuid.UUID
    warehouse_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    delivery_type: str
    cargo_type: str | None = None
    wb_office_id: int | None = None


class FbsSupplyAddOrderBody(BaseModel):
    order_id: uuid.UUID


class FbsSupplyStickersBody(BaseModel):
    force: bool = False


class FbsSupplyOrderOut(BaseModel):
    id: str
    wb_order_id: int
    status: str
    supply_id: str | None
    trbx_id: str | None
    sticker_code: str | None
    sticker_file: str | None


class FbsSupplyOut(BaseModel):
    id: str
    seller_id: str
    warehouse_id: str
    wb_supply_id: str
    name: str
    status: str
    delivery_type: str
    cargo_type: str | None
    wb_office_id: int | None
    barcode_file: str | None
    document_number: str | None
    display_number: str | None
    packaging_task_id: str | None
    created_at_wb: str | None
    delivered_at: str | None
    created_at: str
    updated_at: str
    orders: list[FbsSupplyOrderOut] | None = None


class FbsPickingListItemOut(BaseModel):
    article: str
    sku_code: str | None
    size: str | None
    product_name: str
    quantity: int


class FbsPickingListOut(BaseModel):
    items: list[FbsPickingListItemOut]


class FbsStickerMetaOut(BaseModel):
    order_id: str
    wb_order_id: int
    sticker_code: str | None
    sticker_file: str | None


class FbsStickersOut(BaseModel):
    stickers: list[FbsStickerMetaOut]


class FbsTrbxCreateBody(BaseModel):
    count: int = Field(ge=1, le=100)
    length_mm: int | None = Field(default=None, ge=1)
    width_mm: int | None = Field(default=None, ge=1)
    height_mm: int | None = Field(default=None, ge=1)
    weight_g: int | None = Field(default=None, ge=1)


class FbsTrbxBindOrdersBody(BaseModel):
    order_ids: list[uuid.UUID] = Field(min_length=1)
    length_mm: int = Field(ge=1)
    width_mm: int = Field(ge=1)
    height_mm: int = Field(ge=1)
    weight_g: int = Field(ge=1)


class FbsTrbxOut(BaseModel):
    id: str
    wb_trbx_id: str
    packaging_box_id: str | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    sticker_file: str | None


class FbsSupplyStatusBody(BaseModel):
    status: str


class FbsTrbxBindBoxBody(BaseModel):
    trbx_id: uuid.UUID
    packaging_box_id: uuid.UUID


class FbsTrbxListOut(BaseModel):
    trbxes: list[FbsTrbxOut]


class FbsTrbxStickersOut(BaseModel):
    trbxes: list[FbsTrbxOut]


def _order_out(order: FbsOrder) -> FbsSupplyOrderOut:
    return FbsSupplyOrderOut(
        id=str(order.id),
        wb_order_id=int(order.wb_order_id),
        status=order.status,
        supply_id=str(order.supply_id) if order.supply_id is not None else None,
        trbx_id=str(order.trbx_id) if order.trbx_id is not None else None,
        sticker_code=order.sticker_code,
        sticker_file=order.sticker_file,
    )


def _supply_out(supply: FbsSupply, *, include_orders: bool) -> FbsSupplyOut:
    orders_out: list[FbsSupplyOrderOut] | None = None
    if include_orders:
        orders_out = [_order_out(order) for order in supply.orders]
    return FbsSupplyOut(
        id=str(supply.id),
        seller_id=str(supply.seller_id),
        warehouse_id=str(supply.warehouse_id),
        wb_supply_id=supply.wb_supply_id,
        name=supply.name,
        status=supply.status,
        delivery_type=supply.delivery_type,
        cargo_type=supply.cargo_type,
        wb_office_id=supply.wb_office_id,
        barcode_file=supply.barcode_file,
        document_number=supply.document_number,
        display_number=supply.display_number,
        packaging_task_id=(
            str(supply.packaging_task_id) if supply.packaging_task_id is not None else None
        ),
        created_at_wb=supply.created_at_wb.isoformat() if supply.created_at_wb else None,
        delivered_at=supply.delivered_at.isoformat() if supply.delivered_at else None,
        created_at=supply.created_at.isoformat(),
        updated_at=supply.updated_at.isoformat(),
        orders=orders_out,
    )


def _trbx_out(trbx: pvz_svc.TrbxMeta) -> FbsTrbxOut:
    return FbsTrbxOut(
        id=str(trbx.id),
        wb_trbx_id=trbx.wb_trbx_id,
        packaging_box_id=(
            str(trbx.packaging_box_id) if trbx.packaging_box_id is not None else None
        ),
        length_mm=trbx.length_mm,
        width_mm=trbx.width_mm,
        height_mm=trbx.height_mm,
        weight_g=trbx.weight_g,
        sticker_file=trbx.sticker_file,
    )


def _raise_from_pvz_service(exc: pvz_svc.FbsShipmentPvzError) -> None:
    if exc.code in {
        "supply_not_found",
        "seller_not_found",
        "trbx_not_found",
        "packaging_box_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.code)
    if exc.code in {
        "wrong_delivery_type",
        "trbx_oversized",
        "trbx_overweight",
        "trbx_min_orders",
        "trbx_volume_exceeded",
        "order_not_in_supply",
        "order_already_in_trbx",
        "invalid_trbx_count",
        "invalid_sticker_path",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    if exc.code in {"supply_trbx_locked", "packaging_task_not_found"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


def _raise_from_shipment_service(exc: shipment_svc.FbsShipmentError) -> None:
    if exc.code in {
        "supply_not_found",
        "seller_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.code)
    if exc.code in {
        "wrong_delivery_type",
        "supply_empty",
        "supply_has_cancelled_orders",
        "orders_not_ready",
        "packaging_required",
        "marking_required",
        "invalid_barcode_path",
        "trbx_required",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    if exc.code == "supply_bad_status":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


def _raise_from_service(exc: supply_svc.FbsSupplyError) -> None:
    if exc.code in {
        "supply_not_found",
        "order_not_found",
        "seller_not_found",
        "warehouse_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.code)
    if exc.code in {
        "order_already_in_supply",
        "order_bad_status",
        "order_warehouse_mismatch",
        "order_warehouse_unmapped",
        "invalid_delivery_type",
        "supply_not_editable",
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


def _raise_from_packaging_integration(
    exc: pack_int_svc.FbsPackagingIntegrationError,
) -> None:
    if exc.code in {"supply_not_found", "trbx_not_found"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code in {"wrong_delivery_type", "invalid_status_transition"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.post("", response_model=FbsSupplyOut, status_code=status.HTTP_201_CREATED)
async def create_fbs_supply(
    body: FbsSupplyCreateBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    async with httpx.AsyncClient() as http_client:
        try:
            supply = await supply_svc.create_supply(
                session,
                user.tenant_id,
                seller_id=body.seller_id,
                warehouse_id=body.warehouse_id,
                name=body.name,
                delivery_type=body.delivery_type,
                cargo_type=body.cargo_type,
                wb_office_id=body.wb_office_id,
                http_client=http_client,
            )
        except supply_svc.FbsSupplyError as exc:
            _raise_from_service(exc)
    await session.commit()
    await session.refresh(supply)
    return _supply_out(supply, include_orders=False)


@router.get("/{supply_id}", response_model=FbsSupplyOut)
async def get_fbs_supply(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    try:
        supply = await supply_svc.get_supply(session, user.tenant_id, supply_id)
    except supply_svc.FbsSupplyError as exc:
        _raise_from_service(exc)
    return _supply_out(supply, include_orders=True)


@router.post("/{supply_id}/orders", response_model=FbsSupplyOut)
async def add_order_to_fbs_supply(
    supply_id: uuid.UUID,
    body: FbsSupplyAddOrderBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    async with httpx.AsyncClient() as http_client:
        try:
            supply = await supply_svc.add_order_to_supply(
                session,
                user.tenant_id,
                supply_id,
                body.order_id,
                http_client,
            )
        except supply_svc.FbsSupplyError as exc:
            _raise_from_service(exc)
    await session.commit()
    return _supply_out(supply, include_orders=True)


@router.get("/{supply_id}/picking-list", response_model=FbsPickingListOut)
async def get_fbs_supply_picking_list(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPickingListOut:
    try:
        items = await supply_svc.get_picking_list(session, user.tenant_id, supply_id)
    except supply_svc.FbsSupplyError as exc:
        _raise_from_service(exc)
    return FbsPickingListOut(
        items=[
            FbsPickingListItemOut(
                article=item.article,
                sku_code=item.sku_code,
                size=item.size,
                product_name=item.product_name,
                quantity=item.quantity,
            )
            for item in items
        ]
    )


@router.post("/{supply_id}/stickers", response_model=FbsStickersOut)
async def fetch_fbs_supply_stickers(
    supply_id: uuid.UUID,
    body: FbsSupplyStickersBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsStickersOut:
    async with httpx.AsyncClient() as http_client:
        try:
            stickers = await supply_svc.fetch_and_cache_stickers(
                session,
                user.tenant_id,
                supply_id,
                http_client,
                force=body.force,
            )
        except supply_svc.FbsSupplyError as exc:
            _raise_from_service(exc)
    await session.commit()
    return FbsStickersOut(
        stickers=[
            FbsStickerMetaOut(
                order_id=str(meta.order_id),
                wb_order_id=meta.wb_order_id,
                sticker_code=meta.sticker_code,
                sticker_file=meta.sticker_file,
            )
            for meta in stickers
        ]
    )


@router.post(
    "/{supply_id}/trbx",
    response_model=FbsTrbxListOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_fbs_supply_trbx(
    supply_id: uuid.UUID,
    body: FbsTrbxCreateBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsTrbxListOut:
    async with httpx.AsyncClient() as http_client:
        try:
            trbxes = await pvz_svc.create_trbxes(
                session,
                user.tenant_id,
                supply_id,
                body.count,
                http_client,
                length_mm=body.length_mm,
                width_mm=body.width_mm,
                height_mm=body.height_mm,
                weight_g=body.weight_g,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            _raise_from_pvz_service(exc)
    await session.commit()
    return FbsTrbxListOut(
        trbxes=[
            _trbx_out(pvz_svc.TrbxMeta(
                id=trbx.id,
                wb_trbx_id=trbx.wb_trbx_id,
                packaging_box_id=trbx.packaging_box_id,
                length_mm=trbx.length_mm,
                width_mm=trbx.width_mm,
                height_mm=trbx.height_mm,
                weight_g=trbx.weight_g,
                sticker_file=trbx.sticker_file,
            ))
            for trbx in trbxes
        ]
    )


@router.post("/{supply_id}/trbx/stickers", response_model=FbsTrbxStickersOut)
async def fetch_fbs_supply_trbx_stickers(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    type: Annotated[str, Query()] = "png",
) -> FbsTrbxStickersOut:
    async with httpx.AsyncClient() as http_client:
        try:
            trbxes = await pvz_svc.fetch_trbx_stickers(
                session,
                user.tenant_id,
                supply_id,
                http_client,
                type=type,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            _raise_from_pvz_service(exc)
    await session.commit()
    return FbsTrbxStickersOut(trbxes=[_trbx_out(trbx) for trbx in trbxes])


@router.post("/{supply_id}/trbx/{trbx_id}/orders", response_model=FbsTrbxOut)
async def bind_orders_to_fbs_trbx(
    supply_id: uuid.UUID,
    trbx_id: uuid.UUID,
    body: FbsTrbxBindOrdersBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsTrbxOut:
    async with httpx.AsyncClient() as http_client:
        try:
            trbx = await pvz_svc.bind_orders_to_trbx(
                session,
                user.tenant_id,
                supply_id,
                trbx_id,
                body.order_ids,
                body.length_mm,
                body.width_mm,
                body.height_mm,
                body.weight_g,
                http_client,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            _raise_from_pvz_service(exc)
    await session.commit()
    return _trbx_out(
        pvz_svc.TrbxMeta(
            id=trbx.id,
            wb_trbx_id=trbx.wb_trbx_id,
            packaging_box_id=trbx.packaging_box_id,
            length_mm=trbx.length_mm,
            width_mm=trbx.width_mm,
            height_mm=trbx.height_mm,
            weight_g=trbx.weight_g,
            sticker_file=trbx.sticker_file,
        )
    )


@router.put("/{supply_id}/status", response_model=FbsSupplyOut)
async def update_fbs_supply_status(
    supply_id: uuid.UUID,
    body: FbsSupplyStatusBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    try:
        await pack_int_svc.update_supply_status(
            session,
            user.tenant_id,
            supply_id,
            body.status,
        )
    except pack_int_svc.FbsPackagingIntegrationError as exc:
        _raise_from_packaging_integration(exc)
    await session.commit()
    refreshed = await supply_svc.get_supply(session, user.tenant_id, supply_id)
    return _supply_out(refreshed, include_orders=True)


@router.post("/{supply_id}/trbx/bind-box", response_model=FbsTrbxOut)
async def bind_fbs_packaging_box_to_trbx(
    supply_id: uuid.UUID,
    body: FbsTrbxBindBoxBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsTrbxOut:
    try:
        trbx = await pvz_svc.bind_packaging_box_to_trbx(
            session,
            user.tenant_id,
            supply_id,
            body.trbx_id,
            body.packaging_box_id,
        )
    except pvz_svc.FbsShipmentPvzError as exc:
        _raise_from_pvz_service(exc)
    await session.commit()
    return _trbx_out(
        pvz_svc.TrbxMeta(
            id=trbx.id,
            wb_trbx_id=trbx.wb_trbx_id,
            packaging_box_id=trbx.packaging_box_id,
            length_mm=trbx.length_mm,
            width_mm=trbx.width_mm,
            height_mm=trbx.height_mm,
            weight_g=trbx.weight_g,
            sticker_file=trbx.sticker_file,
        )
    )


@router.post("/{supply_id}/deliver", response_model=FbsSupplyOut)
async def deliver_fbs_supply(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    async with httpx.AsyncClient() as http_client:
        try:
            supply = await shipment_svc.deliver_supply(
                session,
                user.tenant_id,
                supply_id,
                http_client,
            )
        except shipment_svc.FbsShipmentError as exc:
            _raise_from_shipment_service(exc)
    await session.commit()
    await session.refresh(supply)
    refreshed = await supply_svc.get_supply(session, user.tenant_id, supply_id)
    return _supply_out(refreshed, include_orders=True)


@router.get("/{supply_id}/barcode")
async def get_fbs_supply_barcode(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    type: Annotated[str, Query()] = "png",
) -> Response:
    async with httpx.AsyncClient() as http_client:
        try:
            png_bytes = await shipment_svc.get_supply_barcode(
                session,
                user.tenant_id,
                supply_id,
                http_client,
                type=type,
            )
        except shipment_svc.FbsShipmentError as exc:
            _raise_from_shipment_service(exc)
    await session.commit()
    media_type = "image/png" if type == "png" else "image/svg+xml"
    return Response(content=png_bytes, media_type=media_type)
