from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_current_user,
    get_effective_seller_id,
    require_reception_access,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.inbound_intake import (
    InboundIntakeBox,
    InboundIntakeBoxLine,
    InboundIntakeDistributionLine,
    InboundIntakeLine,
    InboundIntakeRequest,
)
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.services import inbound_intake_box_service as inbound_box_svc
from app.services import inbound_intake_service as svc
from app.services import inventory_service as inv_svc
from app.services.inbound_intake_box_service import InboundIntakeBoxError
from app.services.inbound_intake_service import InboundIntakeError

router = APIRouter(
    prefix="/operations/inbound-intake-requests",
    tags=["operations"],
)


class InboundIntakeRequestCreate(BaseModel):
    warehouse_id: uuid.UUID
    planned_delivery_date: date | None = None


class InboundIntakeRequestPlannedPatch(BaseModel):
    planned_delivery_date: date | None = None
    planned_box_count: int | None = Field(default=None, ge=1, le=100_000)


class InboundIntakeLineCreate(BaseModel):
    product_id: uuid.UUID
    expected_qty: int = Field(ge=1, le=1_000_000_000)
    storage_location_id: uuid.UUID | None = None


class InboundIntakeLineStoragePatch(BaseModel):
    storage_location_id: uuid.UUID


class InboundIntakeLineExpectedPatch(BaseModel):
    expected_qty: int = Field(ge=1, le=1_000_000_000)


class InboundIntakeLineReceiveBody(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000_000)

class InboundIntakeLineActualPatch(BaseModel):
    actual_qty: int = Field(ge=0, le=1_000_000_000)


class InboundIntakeBoxLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    posted_qty: int = 0
    remaining_qty: int = 0


class InboundIntakeBoxOut(BaseModel):
    id: str
    box_number: int
    internal_barcode: str
    label_printed_at: str | None = None
    intake_opened_at: str | None = None
    intake_closed_at: str | None = None
    is_open: bool = False
    remaining_qty: int = 0
    lines: list[InboundIntakeBoxLineOut] = Field(default_factory=list)


class InboundBoxBarcodeBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class InboundBoxScanBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class InboundReceivingScanBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)


class InboundBoxLineQuantityBody(BaseModel):
    quantity: int = Field(ge=0, le=100_000)


class InboundBoxPutawayLineIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)


class InboundBoxPutawayBody(BaseModel):
    storage_location_id: uuid.UUID
    lines: list[InboundBoxPutawayLineIn] | None = None


class InboundIntakeLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    expected_qty: int
    actual_qty: int | None
    effective_actual_qty: int | None = None
    posted_qty: int
    storage_location_id: str | None
    storage_location_code: str | None


class InboundIntakeRequestSummaryOut(BaseModel):
    id: str
    document_number: str | None = None
    warehouse_id: str
    status: str
    line_count: int
    planned_delivery_date: str | None = None
    planned_box_count: int | None = None
    actual_box_count: int | None = None
    boxes_discrepancy: bool = False
    has_discrepancy: bool = False
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str
    sorting_remaining_qty: int = 0


class InboundIntakeRequestOut(BaseModel):
    id: str
    document_number: str | None = None
    warehouse_id: str
    status: str
    planned_delivery_date: str | None = None
    planned_box_count: int | None = None
    actual_box_count: int | None = None
    boxes_discrepancy: bool = False
    has_discrepancy: bool = False
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str | None = None
    distribution_completed_at: str | None = None
    sorting_remaining_qty: int = 0
    boxes: list[InboundIntakeBoxOut] = Field(default_factory=list)
    lines: list[InboundIntakeLineOut]


class InventoryMovementOut(BaseModel):
    id: str
    product_id: str
    storage_location_id: str
    quantity_delta: int
    movement_type: str
    inbound_intake_line_id: str | None
    created_at: str


def _box_line_out(ln: InboundIntakeBoxLine) -> InboundIntakeBoxLineOut:
    prod = ln.product
    remaining = svc.box_line_remaining_qty(ln)
    return InboundIntakeBoxLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=prod.sku_code if prod is not None else "",
        product_name=prod.name if prod is not None else "",
        quantity=int(ln.quantity),
        posted_qty=int(ln.posted_qty),
        remaining_qty=remaining,
    )


def _box_out(b: InboundIntakeBox) -> InboundIntakeBoxOut:
    is_open = b.intake_opened_at is not None and b.intake_closed_at is None
    lines_out: list[InboundIntakeBoxLineOut] = []
    if "lines" not in sa_inspect(b).unloaded:
        lines_out = [_box_line_out(ln) for ln in b.lines]
    return InboundIntakeBoxOut(
        id=str(b.id),
        box_number=int(b.box_number),
        internal_barcode=b.internal_barcode,
        label_printed_at=b.label_printed_at.isoformat() if b.label_printed_at else None,
        intake_opened_at=b.intake_opened_at.isoformat() if b.intake_opened_at else None,
        intake_closed_at=b.intake_closed_at.isoformat() if b.intake_closed_at else None,
        is_open=is_open,
        remaining_qty=svc.box_remaining_qty(b),
        lines=lines_out,
    )


def _map_inbound_box_err(exc: InboundIntakeBoxError) -> HTTPException:
    code = exc.code
    if code == "request_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code in ("box_not_found", "barcode_unknown"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code in (
        "bad_status",
        "box_closed",
        "box_not_empty",
        "no_open_box",
        "open_box_exists",
        "boxes_missing",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
    if code in (
        "barcode_empty",
        "qty_exceeded",
        "product_not_on_request",
        "actual_below_posted",
        "invalid_qty",
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=code,
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=code,
    )


def _map_inbound_svc_err(exc: InboundIntakeError) -> HTTPException:
    code = exc.code
    if code in ("request_not_found", "line_not_found"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    if code in (
        "not_draft",
        "not_submitted",
        "not_verifying",
        "not_verified",
        "not_editable",
        "line_closed",
        "line_already_posted",
        "already_posted",
        "open_box_exists",
        "duplicate_line",
        "not_distributable",
        "distribution_completed",
        "not_reopenable",
        "distribution_not_completed",
        "already_posted_partial",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=code)
    if code in (
        "barcode_empty",
        "invalid_qty",
        "invalid_planned_box_count",
        "submit_empty",
        "actual_missing",
        "nothing_to_receive",
        "storage_not_assigned",
        "lines_missing_storage",
        "product_not_on_request",
        "product_seller_mismatch",
        "mixed_seller_lines",
        "qty_exceeds_accepted",
        "qty_exceeds_box_remaining",
        "product_not_accepted",
        "product_not_in_box",
        "nothing_to_putaway",
        "sorting_location_reserved",
        "insufficient_sorting_stock",
        "distribution_incomplete",
        "invalid_actual_box_count",
        "planned_boxes_missing",
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=code,
        )
    if code in (
        "warehouse_not_found",
        "seller_not_found",
        "product_not_found",
        "location_not_found",
        "box_not_found",
    ):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=code)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=code,
    )


def _request_out(
    r: InboundIntakeRequest,
    lines: list[InboundIntakeLineOut] | None = None,
    boxes: list[InboundIntakeBoxOut] | None = None,
) -> InboundIntakeRequestOut:
    lines_out = lines
    if lines_out is None:
        lines_out = [_line_out_from_orm(ln, ln.product) for ln in r.lines]
    boxes_out = boxes
    if boxes_out is None:
        if "boxes" in sa_inspect(r).unloaded:
            boxes_out = []
        else:
            boxes_out = [
                _box_out(b) for b in sorted(r.boxes, key=lambda x: x.box_number)
            ]
    return InboundIntakeRequestOut(
        id=str(r.id),
        document_number=r.document_number,
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        planned_delivery_date=r.planned_delivery_date.isoformat()
        if r.planned_delivery_date is not None
        else None,
        planned_box_count=r.planned_box_count,
        actual_box_count=r.actual_box_count,
        boxes_discrepancy=bool(r.boxes_discrepancy),
        has_discrepancy=bool(r.has_discrepancy),
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=r.seller.name if r.seller is not None else None,
        created_at=r.created_at.isoformat() if r.created_at is not None else None,
        distribution_completed_at=r.distribution_completed_at.isoformat()
        if r.distribution_completed_at is not None
        else None,
        sorting_remaining_qty=svc.sorting_remaining_qty(r),
        boxes=boxes_out,
        lines=lines_out,
    )


def _line_out_from_orm(
    line: InboundIntakeLine,
    product: Product,
    *,
    effective_actual_qty: int | None = None,
) -> InboundIntakeLineOut:
    loc = line.storage_location
    return InboundIntakeLineOut(
        id=str(line.id),
        product_id=str(line.product_id),
        sku_code=product.sku_code,
        product_name=product.name,
        expected_qty=line.expected_qty,
        actual_qty=line.actual_qty,
        effective_actual_qty=effective_actual_qty,
        posted_qty=line.posted_qty,
        storage_location_id=str(line.storage_location_id)
        if line.storage_location_id
        else None,
        storage_location_code=loc.code if loc is not None else None,
    )


async def _line_out_for_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    request_status: str,
    line: InboundIntakeLine,
    product: Product,
) -> InboundIntakeLineOut:
    effective: int | None = None
    if request_status in svc.RECEIVING_STATUSES:
        effective = await svc.effective_actual_qty(
            session, request_id, line, request_status=request_status
        )
    return _line_out_from_orm(line, product, effective_actual_qty=effective)


def _movement_out(m: InventoryMovement) -> InventoryMovementOut:
    return InventoryMovementOut(
        id=str(m.id),
        product_id=str(m.product_id),
        storage_location_id=str(m.storage_location_id),
        quantity_delta=m.quantity_delta,
        movement_type=m.movement_type,
        inbound_intake_line_id=str(m.inbound_intake_line_id)
        if m.inbound_intake_line_id
        else None,
        created_at=m.created_at.isoformat(),
    )


class InboundDistributionLineIn(BaseModel):
    product_id: uuid.UUID
    storage_location_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)
    box_id: uuid.UUID | None = None


class InboundDistributionLineOut(BaseModel):
    id: str
    product_id: str
    storage_location_id: str
    storage_location_code: str
    quantity: int
    created_at: str
    box_id: str | None = None
    box_number: int | None = None
    box_internal_barcode: str | None = None


def _dist_out(
    row: InboundIntakeDistributionLine,
    loc: StorageLocation,
    box: InboundIntakeBox | None = None,
) -> InboundDistributionLineOut:
    return InboundDistributionLineOut(
        id=str(row.id),
        product_id=str(row.product_id),
        storage_location_id=str(row.storage_location_id),
        storage_location_code=loc.code,
        quantity=row.quantity,
        created_at=row.created_at.isoformat(),
        box_id=str(row.box_id) if row.box_id is not None else None,
        box_number=int(box.box_number) if box is not None else None,
        box_internal_barcode=box.internal_barcode if box is not None else None,
    )


@router.get("", response_model=list[InboundIntakeRequestSummaryOut])
async def list_inbound_requests(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[InboundIntakeRequestSummaryOut]:
    rows = await svc.list_requests(
        session,
        user.tenant_id,
        seller_product_owner_id=seller_scope,
    )
    return [
        InboundIntakeRequestSummaryOut(
            id=str(r.id),
            document_number=r.document_number,
            warehouse_id=str(r.warehouse_id),
            status=r.status,
            line_count=len(r.lines),
            planned_delivery_date=r.planned_delivery_date.isoformat()
            if r.planned_delivery_date is not None
            else None,
            planned_box_count=r.planned_box_count,
            actual_box_count=r.actual_box_count,
            boxes_discrepancy=bool(r.boxes_discrepancy),
            has_discrepancy=bool(r.has_discrepancy),
            seller_id=str(r.seller_id) if r.seller_id is not None else None,
            seller_name=r.seller.name if r.seller is not None else None,
            created_at=r.created_at.isoformat(),
            sorting_remaining_qty=svc.sorting_remaining_qty(r),
        )
        for r in rows
    ]


@router.post("", response_model=InboundIntakeRequestOut, status_code=status.HTTP_201_CREATED)
async def create_inbound_request(
    body: InboundIntakeRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> InboundIntakeRequestOut:
    if user.role == FULFILLMENT_ADMIN:
        owning_seller_id: uuid.UUID | None = None
    elif user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="seller_not_linked",
            )
        owning_seller_id = effective_seller_id
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    try:
        r = await svc.create_request(
            session,
            user.tenant_id,
            warehouse_id=body.warehouse_id,
            seller_id=owning_seller_id,
            planned_delivery_date=body.planned_delivery_date,
        )
    except InboundIntakeError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        if exc.code == "seller_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            ) from None
        raise
    return _request_out(r, lines=[], boxes=[])


@router.get("/{request_id}", response_model=InboundIntakeRequestOut)
async def get_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> InboundIntakeRequestOut:
    r = await svc.get_request(
        session,
        user.tenant_id,
        request_id,
        seller_product_owner_id=seller_scope,
    )
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="request_not_found",
        )
    lines_out: list[InboundIntakeLineOut] = []
    for ln in r.lines:
        p = ln.product
        lines_out.append(
            await _line_out_for_request(session, request_id, r.status, ln, p)
        )
    return _request_out(r, lines=lines_out)


@router.patch("/{request_id}", response_model=InboundIntakeRequestOut)
async def patch_inbound_request_planned(
    request_id: uuid.UUID,
    body: InboundIntakeRequestPlannedPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> InboundIntakeRequestOut:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    line_seller_scope: uuid.UUID | None = (
        None if user.role == FULFILLMENT_ADMIN else seller_scope
    )
    patch_fields = body.model_dump(exclude_unset=True)
    try:
        r = await svc.patch_request_draft(
            session,
            user.tenant_id,
            request_id,
            planned_delivery_date=patch_fields.get("planned_delivery_date"),
            planned_delivery_date_set="planned_delivery_date" in patch_fields,
            planned_box_count=patch_fields.get("planned_box_count"),
            planned_box_count_set="planned_box_count" in patch_fields,
            seller_product_owner_id=line_seller_scope,
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_draft",
            ) from None
        if exc.code == "invalid_planned_box_count":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_planned_box_count",
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.post(
    "/{request_id}/boxes",
    response_model=InboundIntakeBoxOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_inbound_box(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxOut:
    try:
        box = await inbound_box_svc.create_open_box(
            session, user.tenant_id, request_id
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None
    return _box_out(box)


@router.post(
    "/{request_id}/receiving/scan",
    response_model=InboundIntakeLineOut,
)
async def scan_barcode_to_loose_intake(
    request_id: uuid.UUID,
    body: InboundReceivingScanBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeLineOut:
    try:
        line = await svc.scan_barcode_to_loose_intake(
            session,
            user.tenant_id,
            request_id,
            barcode=body.barcode,
        )
    except InboundIntakeError as exc:
        raise _map_inbound_svc_err(exc) from None
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    req = await svc.get_request(session, user.tenant_id, request_id)
    assert req is not None
    return await _line_out_for_request(
        session, request_id, req.status, line, prod
    )


@router.post(
    "/{request_id}/complete-receiving",
    response_model=InboundIntakeRequestOut,
)
async def complete_inbound_receiving(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.complete_receiving(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        raise _map_inbound_svc_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.post(
    "/{request_id}/boxes/{box_id}/mark-label-printed",
    response_model=InboundIntakeBoxOut,
)
async def mark_inbound_box_label_printed(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxOut:
    try:
        box = await inbound_box_svc.mark_box_label_printed(
            session, user.tenant_id, request_id, box_id
        )
    except InboundIntakeBoxError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "box_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="box_not_found",
            ) from None
        if exc.code == "bad_status":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="bad_status",
            ) from None
        raise
    await session.commit()
    return _box_out(box)


@router.post(
    "/{request_id}/boxes/open",
    response_model=InboundIntakeBoxOut,
)
async def open_inbound_box_by_barcode(
    request_id: uuid.UUID,
    body: InboundBoxBarcodeBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxOut:
    try:
        box = await inbound_box_svc.open_box_by_barcode(
            session,
            user.tenant_id,
            request_id,
            barcode=body.barcode,
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None
    return _box_out(box)


@router.post(
    "/{request_id}/boxes/{box_id}/scan",
    response_model=InboundIntakeBoxLineOut,
)
async def scan_product_into_inbound_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    body: InboundBoxScanBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxLineOut:
    bx = await session.get(InboundIntakeBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="box_not_found",
        )
    try:
        ln = await inbound_box_svc.scan_product_into_box(
            session,
            user.tenant_id,
            request_id,
            box_id,
            barcode=body.barcode,
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None
    return _box_line_out(ln)


@router.put(
    "/{request_id}/boxes/{box_id}/lines/{product_id}",
    response_model=InboundIntakeBoxOut,
)
async def set_inbound_box_line_quantity(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    product_id: uuid.UUID,
    body: InboundBoxLineQuantityBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxOut:
    bx = await session.get(InboundIntakeBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="box_not_found",
        )
    try:
        await inbound_box_svc.set_product_quantity_in_open_box(
            session,
            user.tenant_id,
            request_id,
            box_id,
            product_id=product_id,
            quantity=body.quantity,
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None
    stmt = (
        select(InboundIntakeBox)
        .where(InboundIntakeBox.id == box_id)
        .options(
            selectinload(InboundIntakeBox.lines).selectinload(InboundIntakeBoxLine.product),
        )
    )
    res = await session.execute(stmt)
    box = res.scalar_one()
    return _box_out(box)


@router.post(
    "/{request_id}/boxes/{box_id}/close",
    response_model=InboundIntakeBoxOut,
)
async def close_inbound_box_intake(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeBoxOut:
    bx = await session.get(InboundIntakeBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="box_not_found",
        )
    try:
        box = await inbound_box_svc.close_box_intake(
            session, user.tenant_id, request_id, box_id
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None
    return _box_out(box)


@router.delete(
    "/{request_id}/boxes/{box_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_inbound_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    bx = await session.get(InboundIntakeBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="box_not_found",
        )
    try:
        await inbound_box_svc.delete_empty_box(
            session, user.tenant_id, request_id, box_id
        )
    except InboundIntakeBoxError as exc:
        raise _map_inbound_box_err(exc) from None


@router.post(
    "/{request_id}/boxes/{box_id}/putaway",
    response_model=InboundIntakeRequestOut,
)
async def putaway_inbound_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    body: InboundBoxPutawayBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    line_items: list[tuple[uuid.UUID, int]] | None = None
    if body.lines is not None:
        line_items = [(ln.product_id, ln.quantity) for ln in body.lines]
    try:
        r = await svc.apply_box_putaway(
            session,
            user.tenant_id,
            request_id,
            box_id,
            storage_location_id=body.storage_location_id,
            line_items=line_items,
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code in ("box_not_found", "location_not_found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=exc.code,
            ) from None
        if exc.code in ("not_distributable", "box_not_closed"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        if exc.code in (
            "invalid_qty",
            "qty_exceeds_accepted",
            "qty_exceeds_box_remaining",
            "product_not_accepted",
            "product_not_on_request",
            "product_not_in_box",
            "nothing_to_putaway",
            "sorting_location_reserved",
            "insufficient_sorting_stock",
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        raise
    return _request_out(r)


@router.post(
    "/{request_id}/resync-sorting-stock",
    response_model=InboundIntakeRequestOut,
)
async def resync_inbound_sorting_stock(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.resync_sorting_stock_for_request(
            session, user.tenant_id, request_id
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_distributable":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        raise
    return _request_out(r)


@router.patch(
    "/{request_id}/lines/{line_id}/actual",
    response_model=InboundIntakeLineOut,
)
async def patch_inbound_line_actual(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineActualPatch,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeLineOut:
    try:
        line = await svc.set_line_actual_qty(
            session,
            user.tenant_id,
            request_id,
            line_id,
            actual_qty=body.actual_qty,
        )
    except InboundIntakeError as exc:
        if exc.code == "line_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="line_not_found",
            ) from None
        if exc.code in ("not_verifying", "use_box_scan"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        if exc.code == "actual_below_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="actual_below_posted",
            ) from None
        if exc.code == "invalid_qty":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_qty",
            ) from None
        raise
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    req = await svc.get_request(session, user.tenant_id, request_id)
    assert req is not None
    return await _line_out_for_request(
        session, request_id, req.status, line, prod
    )


@router.post("/{request_id}/verify", response_model=InboundIntakeRequestOut)
async def complete_inbound_verification(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    """Legacy alias for POST .../complete-receiving."""
    try:
        r = await svc.complete_receiving(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        raise _map_inbound_svc_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.get(
    "/{request_id}/movements",
    response_model=list[InventoryMovementOut],
)
async def list_inbound_movements(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[InventoryMovementOut]:
    r = await svc.get_request(
        session,
        user.tenant_id,
        request_id,
        seller_product_owner_id=seller_scope,
    )
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="request_not_found",
        )
    movements = await inv_svc.list_movements_for_request(
        session,
        user.tenant_id,
        request_id,
        seller_product_owner_id=seller_scope,
    )
    return [_movement_out(m) for m in movements]


@router.post(
    "/{request_id}/lines",
    response_model=InboundIntakeLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_inbound_line(
    request_id: uuid.UUID,
    body: InboundIntakeLineCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> InboundIntakeLineOut:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    line_seller_scope: uuid.UUID | None = (
        None if user.role == FULFILLMENT_ADMIN else seller_scope
    )
    try:
        line = await svc.add_line(
            session,
            user.tenant_id,
            request_id,
            product_id=body.product_id,
            expected_qty=body.expected_qty,
            storage_location_id=body.storage_location_id,
            seller_product_owner_id=line_seller_scope,
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_draft",
            ) from None
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from None
        if exc.code == "invalid_qty":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_qty",
            ) from None
        if exc.code == "duplicate_line":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="duplicate_line",
            ) from None
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
            ) from None
        if exc.code == "product_seller_mismatch":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="product_seller_mismatch",
            ) from None
        if exc.code == "mixed_seller_lines":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="mixed_seller_lines",
            ) from None
        raise
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    req = await svc.get_request(session, user.tenant_id, request_id)
    assert req is not None
    return await _line_out_for_request(
        session, request_id, req.status, line, prod
    )


@router.patch(
    "/{request_id}/lines/{line_id}/expected",
    response_model=InboundIntakeLineOut,
)
async def patch_inbound_line_expected(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineExpectedPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> InboundIntakeLineOut:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    line_seller_scope: uuid.UUID | None = (
        None if user.role == FULFILLMENT_ADMIN else seller_scope
    )
    try:
        line = await svc.update_line_expected_qty(
            session,
            user.tenant_id,
            request_id,
            line_id,
            expected_qty=body.expected_qty,
            seller_product_owner_id=line_seller_scope,
        )
    except InboundIntakeError as exc:
        if exc.code == "line_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="line_not_found",
            ) from None
        if exc.code == "not_draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_draft",
            ) from None
        if exc.code == "line_already_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="line_already_posted",
            ) from None
        if exc.code == "invalid_qty":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_qty",
            ) from None
        raise
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    req = await svc.get_request(session, user.tenant_id, request_id)
    assert req is not None
    return await _line_out_for_request(
        session, request_id, req.status, line, prod
    )


@router.delete(
    "/{request_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_inbound_draft_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> Response:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    line_seller_scope: uuid.UUID | None = (
        None if user.role == FULFILLMENT_ADMIN else seller_scope
    )
    try:
        await svc.delete_draft_line(
            session,
            user.tenant_id,
            request_id,
            line_id,
            seller_product_owner_id=line_seller_scope,
        )
    except InboundIntakeError as exc:
        if exc.code == "line_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="line_not_found",
            ) from None
        if exc.code == "not_draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_draft",
            ) from None
        if exc.code == "line_already_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="line_already_posted",
            ) from None
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{request_id}/lines/{line_id}",
    response_model=InboundIntakeLineOut,
)
async def patch_inbound_line_storage(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineStoragePatch,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeLineOut:
    try:
        line = await svc.set_line_storage_location(
            session,
            user.tenant_id,
            request_id,
            line_id,
            storage_location_id=body.storage_location_id,
        )
    except InboundIntakeError as exc:
        if exc.code == "line_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="line_not_found",
            ) from None
        if exc.code == "not_editable":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_editable",
            ) from None
        if exc.code == "line_closed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="line_closed",
            ) from None
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
            ) from None
        raise
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    req = await svc.get_request(session, user.tenant_id, request_id)
    assert req is not None
    return await _line_out_for_request(
        session, request_id, req.status, line, prod
    )


@router.post(
    "/{request_id}/lines/{line_id}/receive",
    response_model=InboundIntakeRequestOut,
)
async def receive_inbound_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineReceiveBody,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.receive_line(
            session,
            user.tenant_id,
            request_id,
            line_id,
            quantity=body.quantity,
        )
    except InboundIntakeError as exc:
        if exc.code == "line_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="line_not_found",
            ) from None
        if exc.code == "already_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="already_posted",
            ) from None
        if exc.code == "not_submitted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_submitted",
            ) from None
        if exc.code == "not_verified":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_verified",
            ) from None
        if exc.code == "nothing_to_receive":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="nothing_to_receive",
            ) from None
        if exc.code == "actual_missing":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="actual_missing",
            ) from None
        if exc.code == "storage_not_assigned":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="storage_not_assigned",
            ) from None
        if exc.code == "invalid_qty":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_qty",
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.post("/{request_id}/submit", response_model=InboundIntakeRequestOut)
async def submit_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> InboundIntakeRequestOut:
    if user.role not in (FULFILLMENT_ADMIN, FULFILLMENT_SELLER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    try:
        r = await svc.submit_request(
            session,
            user.tenant_id,
            request_id,
            seller_product_owner_id=seller_scope,
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_draft":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_draft",
            ) from None
        if exc.code == "submit_empty":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="submit_empty",
            ) from None
        if exc.code == "planned_boxes_missing":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="planned_boxes_missing",
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.post("/{request_id}/post", response_model=InboundIntakeRequestOut)
async def post_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.post_all_remaining(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_submitted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_submitted",
            ) from None
        if exc.code == "not_verified":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_verified",
            ) from None
        if exc.code == "already_posted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="already_posted",
            ) from None
        if exc.code == "lines_missing_storage":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="lines_missing_storage",
            ) from None
        if exc.code == "actual_missing":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="actual_missing",
            ) from None
        if exc.code == "nothing_to_receive":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="nothing_to_receive",
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.get(
    "/{request_id}/distribution-lines",
    response_model=list[InboundDistributionLineOut],
)
async def list_distribution_lines(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InboundDistributionLineOut]:
    try:
        rows = await svc.list_distribution_lines(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        raise
    out: list[InboundDistributionLineOut] = []
    for r in rows:
        loc = await session.get(StorageLocation, r.storage_location_id)
        if loc is None:
            continue
        box = await session.get(InboundIntakeBox, r.box_id) if r.box_id is not None else None
        out.append(_dist_out(r, loc, box))
    return out


@router.put(
    "/{request_id}/distribution-lines",
    response_model=list[InboundDistributionLineOut],
)
async def replace_distribution_lines(
    request_id: uuid.UUID,
    body: list[InboundDistributionLineIn],
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InboundDistributionLineOut]:
    try:
        rows = await svc.replace_distribution_lines(
            session,
            user.tenant_id,
            request_id,
            lines=[
                (x.box_id, x.product_id, x.storage_location_id, x.quantity) for x in body
            ],
        )
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_distributable":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_distributable",
            ) from None
        if exc.code == "distribution_completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="distribution_completed",
            ) from None
        if exc.code in ("invalid_qty", "qty_exceeds_accepted", "product_not_accepted"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        if exc.code == "product_not_on_request":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="product_not_on_request",
            ) from None
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
            ) from None
        if exc.code in (
            "box_required",
            "product_not_in_box",
            "qty_exceeds_box_remaining",
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        raise
    out: list[InboundDistributionLineOut] = []
    for r in rows:
        loc = await session.get(StorageLocation, r.storage_location_id)
        if loc is None:
            continue
        box = await session.get(InboundIntakeBox, r.box_id) if r.box_id is not None else None
        out.append(_dist_out(r, loc, box))
    return out


@router.post(
    "/{request_id}/distribution-complete",
    response_model=InboundIntakeRequestOut,
)
async def complete_distribution(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        await svc.complete_distribution(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_distributable":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_distributable",
            ) from None
        if exc.code in (
            "invalid_qty",
            "qty_exceeds_accepted",
            "product_not_on_request",
            "product_not_accepted",
            "distribution_incomplete",
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, request_id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return _request_out(r2)


@router.post(
    "/{request_id}/distribution-reopen",
    response_model=InboundIntakeRequestOut,
)
async def reopen_distribution_route(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_reception_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.reopen_distribution(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        code = exc.code
        if code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=code,
            ) from None
        if code in ("not_reopenable", "distribution_not_completed", "already_posted_partial"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=code,
            ) from None
        raise
    lines_out: list[InboundIntakeLineOut] = []
    for ln in r.lines:
        p = ln.product
        lines_out.append(_line_out_from_orm(ln, p))
    return _request_out(r, lines=lines_out)
