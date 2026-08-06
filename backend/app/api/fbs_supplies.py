from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc, raise_fbs_http
from app.api.fbs_orders import FbsWorklistOrderOut
from app.db.session import get_db
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.user import User
from app.services import fbs_packaging_integration_service as pack_int_svc
from app.services import fbs_picking_service as picking_svc
from app.services import fbs_shipment_pvz_service as pvz_svc
from app.services import fbs_shipment_service as shipment_svc
from app.services import fbs_supply_service as supply_svc
from app.services.fbs_print_asset_service import (
    FbsPrintAssetError,
    map_print_asset,
    request_supply_print_batch,
)
from app.services.fbs_tracking_service import FbsTrackingError, sync_supply_tracking
from app.services.fbs_workspace_service import FbsWorkspaceError, get_supply_workspace

router = APIRouter(prefix="/operations/fbs-supplies", tags=["operations"])


class FbsSupplyPreflightBody(BaseModel):
    order_ids: list[uuid.UUID] = Field(min_length=1)
    planned_delivery_type: str


class FbsSupplyPlannedDestinationBody(BaseModel):
    office_id: int
    name: str = Field(min_length=1, max_length=255)
    zone: str = Field(min_length=1, max_length=128)


class FbsSupplyFromOrdersBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    order_ids: list[uuid.UUID] = Field(min_length=1)
    planned_delivery_type: str
    planned_destination: FbsSupplyPlannedDestinationBody | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsSupplyPreflightIssueOut(BaseModel):
    order_id: str
    code: str
    message: str


class FbsSupplyPreflightSummaryOut(BaseModel):
    seller: dict[str, str]
    wb_warehouse: dict[str, str | int | None]
    wms_warehouse: dict[str, str]
    buyer_type: str
    cargo_type: str
    orders_count: int
    required_marking_count: int
    pvz_allowed_count: int
    pvz_blocked_count: int
    nearest_deadline_at: str


class FbsSupplyPreflightOut(BaseModel):
    compatible: bool
    summary: FbsSupplyPreflightSummaryOut | None
    issues: list[FbsSupplyPreflightIssueOut]
    server_now: str


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


class FbsPrintBatchRequest(BaseModel):
    kind: str
    order_ids: list[uuid.UUID] | None = None
    retry_missing: bool = False


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


class FbsPrintOrderErrorOut(BaseModel):
    order_id: str
    wb_order_id: int
    code: str
    message: str


class FbsPrintBatchOut(BaseModel):
    requested: int
    ready: int
    missing: int
    failed: int
    assets: list[FbsPrintAssetOut]
    order_errors: list[FbsPrintOrderErrorOut]


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


class FbsWorkspacePrintAssetOut(BaseModel):
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


class FbsWorkspaceSupplyOut(BaseModel):
    id: str
    wb_supply_id: str
    name: str
    status: str
    delivery_type: str
    seller: dict[str, str]
    wb_warehouse: dict[str, str | int | None]
    wms_warehouse: dict[str, str]
    planned_destination: dict[str, str | int] | None
    nearest_deadline_at: str
    packaging_task_id: str | None
    barcode_asset: FbsWorkspacePrintAssetOut | None


class FbsWorkspaceProgressOut(BaseModel):
    picked: int
    packed: int
    metadata_ready: int
    stickers_ready: int
    total: int


class FbsWorkspaceBlockerOut(BaseModel):
    stage: str
    code: str
    message: str
    order_id: str | None
    retryable: bool


class FbsCargoPlaceOut(BaseModel):
    id: str
    wb_trbx_id: str
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    qr_asset: FbsWorkspacePrintAssetOut | None
    applied_at: str | None


class FbsCargoPlaceDraftBody(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    length_mm: int | None = Field(default=None, ge=1)
    width_mm: int | None = Field(default=None, ge=1)
    height_mm: int | None = Field(default=None, ge=1)
    weight_g: int | None = Field(default=None, ge=1)
    measurements_confirmed: bool = False
    packaging_box_id: uuid.UUID | None = None


class FbsCargoPlacesPreflightBody(BaseModel):
    count: int = Field(ge=1, le=100)
    boxes: list[FbsCargoPlaceDraftBody] = Field(default_factory=list)


class FbsCargoPlacesCreateBody(BaseModel):
    count: int = Field(ge=1, le=100)
    boxes: list[FbsCargoPlaceDraftBody] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsCargoPlacesDeleteBody(BaseModel):
    wb_trbx_ids: list[str] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsCargoPlacePreflightIssueOut(BaseModel):
    client_id: str | None
    code: str
    message: str


class FbsCargoPlacesPreflightOut(BaseModel):
    compatible: bool
    limits: dict[str, int | float]
    summary: dict[str, int | float | None]
    issues: list[FbsCargoPlacePreflightIssueOut]


class FbsCargoPlaceListOut(BaseModel):
    cargo_places: list[FbsCargoPlaceOut]


class FbsDeliveryCheckOut(BaseModel):
    code: str
    message: str
    ok: bool
    order_id: str | None


class FbsDeliveryPreflightOut(BaseModel):
    can_deliver: bool
    version: str
    checked_at: str
    checks: list[FbsDeliveryCheckOut]


class FbsSupplyDeliverBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmed_preflight_version: str = Field(min_length=1, max_length=128)


class FbsWorkspaceOut(BaseModel):
    supply: FbsWorkspaceSupplyOut
    stage: str
    progress: FbsWorkspaceProgressOut
    blockers: list[FbsWorkspaceBlockerOut]
    orders: list[FbsWorklistOrderOut]
    cargo_places: list[FbsCargoPlaceOut]
    delivery_preflight: dict[str, object] | None
    last_wb_sync_at: str | None
    tracking_summary: dict[str, object] | None = None
    partial_rejection: dict[str, object] | None = None
    wb_sync_stale: bool = False
    server_now: str


class FbsPickScanLocationBody(BaseModel):
    location_barcode: str = Field(min_length=1, max_length=64)


class FbsPickLocationExpectedProductOut(BaseModel):
    product_id: str
    name: str
    barcode: str | None
    remaining_qty: int
    nearest_deadline_at: str


class FbsPickLocationOut(BaseModel):
    id: str
    code: str
    warehouse_id: str
    warehouse_name: str
    expected_products: list[FbsPickLocationExpectedProductOut]


class FbsPickScanProductBody(BaseModel):
    location_id: uuid.UUID
    product_barcode: str = Field(min_length=1, max_length=64)
    order_id: uuid.UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsPickUndoBody(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsTrbxStickersOut(BaseModel):
    trbxes: list[FbsTrbxOut]


def _order_out(order: FbsOrder) -> FbsSupplyOrderOut:
    return FbsSupplyOrderOut(
        id=str(order.id),
        wb_order_id=int(order.wb_order_id),
        status=order.status,
        supply_id=str(order.supply_id) if order.supply_id is not None else None,
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


def _draft_from_body(body: FbsCargoPlaceDraftBody) -> pvz_svc.CargoPlaceDraft:
    return pvz_svc.CargoPlaceDraft(
        client_id=body.client_id,
        length_mm=body.length_mm,
        width_mm=body.width_mm,
        height_mm=body.height_mm,
        weight_g=body.weight_g,
        measurements_confirmed=body.measurements_confirmed,
        packaging_box_id=body.packaging_box_id,
    )


def _cargo_place_out(place: dict[str, object]) -> FbsCargoPlaceOut:
    qr_raw = place.get("qr_asset")
    qr_out: FbsWorkspacePrintAssetOut | None = None
    if isinstance(qr_raw, dict):
        qr_out = FbsWorkspacePrintAssetOut.model_validate(qr_raw)
    return FbsCargoPlaceOut(
        id=str(place["id"]),
        wb_trbx_id=str(place["wb_trbx_id"]),
        length_mm=place.get("length_mm"),  # type: ignore[arg-type]
        width_mm=place.get("width_mm"),  # type: ignore[arg-type]
        height_mm=place.get("height_mm"),  # type: ignore[arg-type]
        weight_g=place.get("weight_g"),  # type: ignore[arg-type]
        qr_asset=qr_out,
        applied_at=place.get("applied_at"),  # type: ignore[arg-type]
    )


def _raise_from_print_asset_service(exc: FbsPrintAssetError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code in {"supply_not_found", "order_not_in_supply", "asset_not_found"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code in {"invalid_kind", "invalid_order_ids"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _raise_from_pvz_service(exc: pvz_svc.FbsShipmentPvzError) -> None:
    if exc.http_status is not None:
        raise_fbs_http(exc.http_status, exc.code)
    if exc.code in {"wb_timeout", "wb_pending_confirmation"}:
        messages = {
            "wb_timeout": "WB не подтвердил создание грузомест — повторите операцию.",
            "wb_pending_confirmation": (
                "WB пока не подтвердил создание грузомест; выполняется сверка."
            ),
        }
        raise_fbs_http(
            status.HTTP_504_GATEWAY_TIMEOUT,
            exc.code,
            message=messages[exc.code],
            context={"operation_state": "pending_confirmation"},
            retryable=True,
        )
    if exc.code in {
        "supply_not_found",
        "seller_not_found",
        "trbx_not_found",
        "cargo_place_not_found",
    }:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
    if exc.code == "missing_marketplace_token":
        raise_fbs_http(status.HTTP_403_FORBIDDEN, exc.code)
    if exc.code in {
        "wrong_delivery_type",
        "trbx_oversized",
        "trbx_sides_sum_exceeded",
        "trbx_overweight",
        "trbx_min_orders",
        "trbx_volume_exceeded",
        "order_not_in_supply",
        "order_already_in_trbx",
        "invalid_trbx_count",
        "invalid_sticker_path",
        "boxes_count_mismatch",
        "cargo_places_preflight_failed",
        "empty_cargo_place_selection",
        "missing_idempotency_key",
    }:
        raise_fbs_http(status.HTTP_400_BAD_REQUEST, exc.code)
    if exc.code == "idempotency_key_reused":
        raise_fbs_http(status.HTTP_409_CONFLICT, exc.code)
    if exc.code.startswith("wb_"):
        raise_fbs_http(status.HTTP_502_BAD_GATEWAY, exc.code)
    raise_fbs_http(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code)


def _raise_from_shipment_service(exc: shipment_svc.FbsShipmentError) -> None:
    detail = envelope_from_exc(exc)
    if exc.http_status is not None and (exc.context or exc.code in {
        "wb_timeout",
        "wb_pending_confirmation",
        "operation_in_progress",
        "stale_preflight",
        "meta_validation_fail",
        "idempotency_key_reused",
    }):
        raise HTTPException(status_code=exc.http_status, detail=detail)
    if exc.code in {
        "supply_not_found",
        "seller_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if exc.code == "wrong_delivery_type":
        status_code = exc.http_status or status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail)
    if exc.code in {
        "supply_empty",
        "supply_has_cancelled_orders",
        "orders_not_ready",
        "packaging_required",
        "marking_required",
        "marking_not_allowed",
        "invalid_barcode_path",
        "cargo_places_required",
        "cargo_place_qr_not_ready",
        "missing_idempotency_key",
        "order_cancelled",
    }:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if exc.code in {
        "supply_bad_status",
        "stale_preflight",
        "idempotency_key_reused",
        "meta_validation_fail",
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code in {"wb_timeout", "wb_pending_confirmation"}:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=detail)
    if exc.code == "operation_in_progress":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _raise_from_service(exc: supply_svc.FbsSupplyError) -> None:
    detail = envelope_from_exc(exc)
    if exc.http_status is not None and (
        exc.context
        or exc.code
        in {
            "wb_timeout",
            "wb_pending_confirmation",
            "operation_in_progress",
            "order_incompatible",
            "idempotency_key_reused",
            "empty_order_set",
            "missing_idempotency_key",
            "supply_empty",
        }
    ):
        raise HTTPException(status_code=exc.http_status, detail=detail)
    if exc.code in {
        "supply_not_found",
        "order_not_found",
        "seller_not_found",
        "warehouse_not_found",
    }:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if exc.code in {
        "order_already_in_supply",
        "order_bad_status",
        "order_warehouse_mismatch",
        "order_warehouse_unmapped",
        "invalid_delivery_type",
        "supply_not_editable",
        "order_incompatible",
        "idempotency_key_reused",
    }:
        raise HTTPException(
            status_code=exc.http_status or status.HTTP_409_CONFLICT,
            detail=detail,
        )
    if exc.code in {"empty_order_set", "missing_idempotency_key", "supply_empty"}:
        raise HTTPException(
            status_code=exc.http_status or status.HTTP_400_BAD_REQUEST,
            detail=detail,
        )
    if exc.code in {"wb_timeout", "wb_pending_confirmation", "operation_in_progress"}:
        status_code = exc.http_status or (
            status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.code == "operation_in_progress"
            else status.HTTP_504_GATEWAY_TIMEOUT
        )
        raise HTTPException(status_code=status_code, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(
            status_code=exc.http_status or status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _raise_from_service_legacy(exc: supply_svc.FbsSupplyError) -> None:
    """Legacy create/add-order path — plain string detail for old callers."""
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
    if exc.code in {"supply_not_found", "trbx_not_found", "packaging_box_not_found"}:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
    if exc.code in {"wrong_delivery_type", "invalid_status_transition"}:
        raise_fbs_http(status.HTTP_400_BAD_REQUEST, exc.code)
    if exc.code == "packaging_box_already_bound":
        raise_fbs_http(status.HTTP_409_CONFLICT, exc.code)
    raise_fbs_http(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code)


def _raise_from_picking(exc: picking_svc.FbsPickingError) -> None:
    raise HTTPException(status_code=exc.http_status, detail=envelope_from_exc(exc))


@router.post("/preflight", response_model=FbsSupplyPreflightOut)
async def preflight_fbs_supply(
    body: FbsSupplyPreflightBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyPreflightOut:
    try:
        payload = await supply_svc.preflight_supply_composition(
            session,
            user.tenant_id,
            body.order_ids,
            planned_delivery_type=body.planned_delivery_type,
        )
    except supply_svc.FbsSupplyError as exc:
        _raise_from_service(exc)
    return FbsSupplyPreflightOut.model_validate(payload)


@router.post("/from-orders", response_model=FbsWorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_fbs_supply_from_orders(
    body: FbsSupplyFromOrdersBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    planned_dest = (
        body.planned_destination.model_dump() if body.planned_destination is not None else None
    )
    async with httpx.AsyncClient() as http_client:
        try:
            workspace = await supply_svc.create_supply_from_orders(
                session,
                user.tenant_id,
                name=body.name,
                order_ids=body.order_ids,
                planned_delivery_type=body.planned_delivery_type,
                planned_destination=planned_dest,
                idempotency_key=body.idempotency_key,
                http_client=http_client,
            )
        except supply_svc.FbsSupplyError as exc:
            if exc.code in {"wb_timeout", "wb_pending_confirmation"}:
                await session.commit()
            _raise_from_service(exc)
    await session.commit()
    return FbsWorkspaceOut.model_validate(workspace)


@router.post("/{supply_id}/start-work", response_model=FbsWorkspaceOut)
async def start_fbs_supply_work(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    try:
        workspace = await supply_svc.start_supply_work(
            session,
            user.tenant_id,
            supply_id,
        )
    except supply_svc.FbsSupplyError as exc:
        _raise_from_service(exc)
    await session.commit()
    return FbsWorkspaceOut.model_validate(workspace)


@router.post("/{supply_id}/pick/scan-location", response_model=FbsPickLocationOut)
async def scan_fbs_pick_location(
    supply_id: uuid.UUID,
    body: FbsPickScanLocationBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPickLocationOut:
    try:
        payload = await picking_svc.scan_pick_location(
            session,
            user.tenant_id,
            supply_id,
            location_barcode=body.location_barcode.strip(),
        )
    except picking_svc.FbsPickingError as exc:
        _raise_from_picking(exc)
    return FbsPickLocationOut.model_validate(payload)


@router.post("/{supply_id}/pick/scan-product", response_model=FbsWorkspaceOut)
async def scan_fbs_pick_product(
    supply_id: uuid.UUID,
    body: FbsPickScanProductBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    try:
        workspace = await picking_svc.scan_pick_product(
            session,
            user.tenant_id,
            supply_id,
            location_id=body.location_id,
            product_barcode=body.product_barcode.strip(),
            order_id=body.order_id,
            idempotency_key=body.idempotency_key,
            actor=user,
        )
    except picking_svc.FbsPickingError as exc:
        _raise_from_picking(exc)
    await session.commit()
    return FbsWorkspaceOut.model_validate(workspace)


@router.post("/{supply_id}/pick/{order_id}/undo", response_model=FbsWorkspaceOut)
async def undo_fbs_pick(
    supply_id: uuid.UUID,
    order_id: uuid.UUID,
    body: FbsPickUndoBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    try:
        workspace = await picking_svc.undo_pick(
            session,
            user.tenant_id,
            supply_id,
            order_id,
            idempotency_key=body.idempotency_key,
            actor=user,
        )
    except picking_svc.FbsPickingError as exc:
        _raise_from_picking(exc)
    await session.commit()
    return FbsWorkspaceOut.model_validate(workspace)


@router.post("", response_model=FbsSupplyOut, status_code=status.HTTP_201_CREATED, deprecated=True)
async def create_fbs_supply(
    body: FbsSupplyCreateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
            _raise_from_service_legacy(exc)
    await session.commit()
    await session.refresh(supply)
    return _supply_out(supply, include_orders=False)


@router.get("/{supply_id}/workspace", response_model=FbsWorkspaceOut)
async def get_fbs_supply_workspace(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    try:
        workspace = await get_supply_workspace(session, user.tenant_id, supply_id)
    except FbsWorkspaceError as exc:
        if exc.code == "supply_not_found":
            raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
        raise_fbs_http(status.HTTP_500_INTERNAL_SERVER_ERROR, exc.code)
    return FbsWorkspaceOut.model_validate(workspace)


@router.get("/{supply_id}", response_model=FbsSupplyOut)
async def get_fbs_supply(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsSupplyOut:
    try:
        supply = await supply_svc.get_supply(session, user.tenant_id, supply_id)
    except supply_svc.FbsSupplyError as exc:
        _raise_from_service(exc)
    return _supply_out(supply, include_orders=True)


@router.post("/{supply_id}/orders", response_model=FbsSupplyOut, deprecated=True)
async def add_order_to_fbs_supply(
    supply_id: uuid.UUID,
    body: FbsSupplyAddOrderBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
            _raise_from_service_legacy(exc)
    await session.commit()
    return _supply_out(supply, include_orders=True)


@router.get("/{supply_id}/picking-list", response_model=FbsPickingListOut)
async def get_fbs_supply_picking_list(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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


@router.post(
    "/{supply_id}/stickers",
    response_model=FbsStickersOut,
    deprecated=True,
    summary="Deprecated compatibility: order stickers with sticker_file paths",
    description=(
        "Compatibility layer only. New clients must use "
        "POST /operations/fbs-supplies/{supply_id}/print-assets and "
        "GET /operations/fbs-print-assets/{asset_id}/content. "
        "Response field sticker_file is an internal storage path, not a public URL."
    ),
)
async def fetch_fbs_supply_stickers(
    supply_id: uuid.UUID,
    body: FbsSupplyStickersBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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


@router.post("/{supply_id}/print-assets", response_model=FbsPrintBatchOut)
async def fetch_fbs_supply_print_assets(
    supply_id: uuid.UUID,
    body: FbsPrintBatchRequest,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsPrintBatchOut:
    async with httpx.AsyncClient() as http_client:
        try:
            batch = await request_supply_print_batch(
                session,
                user.tenant_id,
                supply_id,
                kind=body.kind,
                order_ids=body.order_ids,
                retry_missing=body.retry_missing,
                http_client=http_client,
            )
        except FbsPrintAssetError as exc:
            _raise_from_print_asset_service(exc)
    await session.commit()
    return FbsPrintBatchOut(
        requested=batch.requested,
        ready=batch.ready,
        missing=batch.missing,
        failed=batch.failed,
        assets=[FbsPrintAssetOut(**map_print_asset(asset)) for asset in batch.assets],
        order_errors=[
            FbsPrintOrderErrorOut(
                order_id=str(err.order_id),
                wb_order_id=err.wb_order_id,
                code=err.code,
                message=err.message,
            )
            for err in batch.order_errors
        ],
    )


@router.post(
    "/{supply_id}/cargo-places/preflight",
    response_model=FbsCargoPlacesPreflightOut,
)
async def preflight_fbs_cargo_places(
    supply_id: uuid.UUID,
    body: FbsCargoPlacesPreflightBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsCargoPlacesPreflightOut:
    try:
        payload = await pvz_svc.preflight_supply_cargo_places(
            session,
            user.tenant_id,
            supply_id,
            body.count,
            [_draft_from_body(box) for box in body.boxes],
        )
    except pvz_svc.FbsShipmentPvzError as exc:
        _raise_from_pvz_service(exc)
    return FbsCargoPlacesPreflightOut.model_validate(payload)


@router.post(
    "/{supply_id}/cargo-places",
    response_model=FbsCargoPlaceListOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_fbs_cargo_places(
    supply_id: uuid.UUID,
    body: FbsCargoPlacesCreateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsCargoPlaceListOut:
    async with httpx.AsyncClient() as http_client:
        try:
            places = await pvz_svc.create_cargo_places(
                session,
                user.tenant_id,
                supply_id,
                body.count,
                [_draft_from_body(box) for box in body.boxes],
                body.idempotency_key,
                http_client,
                actor_user_id=user.id,
                confirmation_source="operator_manual_missing_dims",
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            _raise_from_pvz_service(exc)
    await session.commit()
    return FbsCargoPlaceListOut(cargo_places=[_cargo_place_out(place) for place in places])


@router.delete(
    "/{supply_id}/cargo-places",
    response_model=FbsCargoPlaceListOut,
    summary="Delete selected PVZ cargo places",
    description=(
        "Removes selected WB cargo places while the supply is still being assembled. "
        "Calls WB DELETE /api/v3/supplies/{supplyId}/trbx, then drops local FbsTrbx rows "
        "and QR print assets. Retries reconcile via GET trbx list; absent requested IDs "
        "count as confirmed delete without re-deleting extras."
    ),
)
async def delete_fbs_cargo_places(
    supply_id: uuid.UUID,
    body: FbsCargoPlacesDeleteBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsCargoPlaceListOut:
    async with httpx.AsyncClient() as http_client:
        try:
            places = await pvz_svc.delete_cargo_places(
                session,
                user.tenant_id,
                supply_id,
                body.wb_trbx_ids,
                body.idempotency_key,
                http_client,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            if exc.code in {"wb_timeout", "wb_pending_confirmation"}:
                await session.commit()
            _raise_from_pvz_service(exc)
    await session.commit()
    return FbsCargoPlaceListOut(cargo_places=[_cargo_place_out(place) for place in places])


@router.get("/{supply_id}/cargo-places", response_model=FbsCargoPlaceListOut)
async def list_fbs_cargo_places(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsCargoPlaceListOut:
    async with httpx.AsyncClient() as http_client:
        try:
            places = await pvz_svc.list_cargo_places(
                session,
                user.tenant_id,
                supply_id,
                http_client,
            )
        except pvz_svc.FbsShipmentPvzError as exc:
            _raise_from_pvz_service(exc)
    await session.commit()
    return FbsCargoPlaceListOut(cargo_places=[_cargo_place_out(place) for place in places])


@router.post(
    "/{supply_id}/trbx",
    response_model=FbsTrbxListOut,
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def create_fbs_supply_trbx(
    supply_id: uuid.UUID,
    body: FbsTrbxCreateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
                actor_user_id=user.id,
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


@router.post(
    "/{supply_id}/trbx/stickers",
    response_model=FbsTrbxStickersOut,
    deprecated=True,
    summary="Deprecated compatibility: cargo QR via sticker_file paths",
    description=(
        "Compatibility layer only. Use POST …/print-assets with kind=cargo_place_qr "
        "and authorized binary content URLs."
    ),
)
async def fetch_fbs_supply_trbx_stickers(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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


@router.post("/{supply_id}/trbx/{trbx_id}/orders", response_model=FbsTrbxOut, deprecated=True)
async def bind_orders_to_fbs_trbx(
    supply_id: uuid.UUID,
    trbx_id: uuid.UUID,
    body: FbsTrbxBindOrdersBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsTrbxOut:
    _ = (supply_id, trbx_id, body, user, session)
    raise_fbs_http(
        status.HTTP_410_GONE,
        "deprecated_use_cargo_places",
    )


@router.put("/{supply_id}/status", response_model=FbsSupplyOut)
async def update_fbs_supply_status(
    supply_id: uuid.UUID,
    body: FbsSupplyStatusBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsTrbxOut:
    try:
        trbx = await pack_int_svc.bind_packaging_box_to_trbx(
            session,
            user.tenant_id,
            supply_id,
            body.trbx_id,
            body.packaging_box_id,
        )
    except pack_int_svc.FbsPackagingIntegrationError as exc:
        _raise_from_packaging_integration(exc)
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


@router.post("/{supply_id}/delivery-preflight", response_model=FbsDeliveryPreflightOut)
async def preflight_fbs_delivery(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsDeliveryPreflightOut:
    async with httpx.AsyncClient() as http_client:
        try:
            result = await shipment_svc.preflight_delivery(
                session,
                user.tenant_id,
                supply_id,
                http_client,
            )
        except shipment_svc.FbsShipmentError as exc:
            _raise_from_shipment_service(exc)
    await session.commit()
    payload = shipment_svc.delivery_preflight_to_dict(result)
    return FbsDeliveryPreflightOut.model_validate(payload)


@router.post("/{supply_id}/deliver", response_model=FbsWorkspaceOut)
async def deliver_fbs_supply(
    supply_id: uuid.UUID,
    body: FbsSupplyDeliverBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    async with httpx.AsyncClient() as http_client:
        try:
            supply = await shipment_svc.deliver_supply(
                session,
                user.tenant_id,
                supply_id,
                http_client,
                idempotency_key=body.idempotency_key,
                confirmed_preflight_version=body.confirmed_preflight_version,
            )
        except shipment_svc.FbsShipmentError as exc:
            if exc.code in {"wb_timeout", "wb_pending_confirmation", "meta_validation_fail"}:
                await session.commit()
            _raise_from_shipment_service(exc)
    await session.commit()
    await session.refresh(supply)
    try:
        workspace = await get_supply_workspace(session, user.tenant_id, supply_id)
    except FbsWorkspaceError as exc:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
    return FbsWorkspaceOut.model_validate(workspace)


@router.post("/{supply_id}/sync-tracking", response_model=FbsWorkspaceOut)
async def sync_fbs_supply_tracking(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    async with httpx.AsyncClient() as http_client:
        try:
            await sync_supply_tracking(
                session,
                user.tenant_id,
                supply_id,
                http_client,
            )
        except FbsTrackingError as exc:
            if exc.code == "supply_not_found":
                raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
            if exc.code.startswith("wb_"):
                raise_fbs_http(status.HTTP_502_BAD_GATEWAY, exc.code, retryable=True)
            raise_fbs_http(status.HTTP_502_BAD_GATEWAY, exc.code)
    await session.commit()
    try:
        workspace = await get_supply_workspace(session, user.tenant_id, supply_id)
    except FbsWorkspaceError as exc:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
    return FbsWorkspaceOut.model_validate(workspace)


@router.post(
    "/{supply_id}/retry-supply-qr",
    response_model=FbsWorkspaceOut,
    summary="Retry warehouse/SC supply QR after confirmed deliver",
    description=(
        "Fetches the missing supply QR print asset only. Never re-invokes WB deliver. "
        "Allowed for warehouse_sc supplies in in_delivery or done; PVZ returns 409 wrong_delivery_type."
    ),
)
async def retry_fbs_supply_qr(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsWorkspaceOut:
    async with httpx.AsyncClient() as http_client:
        try:
            supply = await shipment_svc.retry_supply_qr(
                session,
                user.tenant_id,
                supply_id,
                http_client,
            )
        except shipment_svc.FbsShipmentError as exc:
            _raise_from_shipment_service(exc)
    await session.commit()
    await session.refresh(supply)
    try:
        workspace = await get_supply_workspace(session, user.tenant_id, supply_id)
    except FbsWorkspaceError as exc:
        raise_fbs_http(status.HTTP_404_NOT_FOUND, exc.code)
    return FbsWorkspaceOut.model_validate(workspace)


@router.get(
    "/{supply_id}/barcode",
    deprecated=True,
    summary="Deprecated compatibility: supply QR binary",
    description=(
        "Compatibility layer only. Prefer print-assets kind=supply_qr after deliver "
        "(warehouse/sc). Does not return barcode_file paths to the client."
    ),
)
async def get_fbs_supply_barcode(
    supply_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
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
