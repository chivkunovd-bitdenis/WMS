from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_effective_seller_id,
    require_mp_shipments_access,
    resolve_effective_seller_id,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.seller import Seller
from app.models.user import User
from app.services import marketplace_unload_box_service as box_svc
from app.services import marketplace_unload_pick_service as pick_svc
from app.services import marketplace_unload_service as svc
from app.services import packaging_task_service as pkg_svc
from app.services.catalog_service import get_warehouse
from app.services.marketplace_unload_box_service import MarketplaceUnloadBoxError
from app.services.marketplace_unload_pick_service import MarketplaceUnloadPickError
from app.services.marketplace_unload_service import MarketplaceUnloadError

# Продукт (RU): отгрузка фулфилмента на маркетплейс. Имя префикса API — историческое.
router = APIRouter(
    prefix="/operations/marketplace-unload-requests",
    tags=["operations"],
)
_bearer = HTTPBearer(auto_error=False)


class MarketplaceUnloadRequestCreate(BaseModel):
    warehouse_id: uuid.UUID
    seller_id: uuid.UUID
    wb_mp_warehouse_id: int | None = Field(default=None, ge=1, le=2_000_000_000)


class SellerMarketplaceUnloadRequestCreate(BaseModel):
    warehouse_id: uuid.UUID
    wb_mp_warehouse_id: int | None = Field(default=None, ge=1, le=2_000_000_000)


class MarketplaceUnloadRequestUpdate(BaseModel):
    wb_mp_warehouse_id: int | None = Field(default=None, ge=1, le=2_000_000_000)
    planned_shipment_date: date | None = None


class MarketplaceUnloadConfirmBody(BaseModel):
    planned_shipment_date: date | None = None


class MarketplaceUnloadShipBody(BaseModel):
    acknowledge_discrepancy: bool = False


class MarketplaceUnloadLineBulkItem(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=0, le=1_000_000_000)


class MarketplaceUnloadLinesBulkReplace(BaseModel):
    lines: list[MarketplaceUnloadLineBulkItem] = Field(default_factory=list)


class MarketplaceUnloadManualBoxLineBody(BaseModel):
    product_id: uuid.UUID
    storage_location_id: uuid.UUID | None = None
    quantity: int = Field(ge=1, le=1_000_000_000)


class MarketplaceUnloadBoxLineRemoveBody(BaseModel):
    quantity: int | None = Field(default=None, ge=1, le=1_000_000_000)


_DEFAULT_BOX_LINE_REMOVE = MarketplaceUnloadBoxLineRemoveBody()


class MarketplaceUnloadBoxLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int


class MarketplaceUnloadBoxScanOut(BaseModel):
    """TSD scan response: location step, ready box, or product added to box."""

    kind: str
    storage_location_id: str | None = None
    location_code: str | None = None
    id: str | None = None
    product_id: str | None = None
    sku_code: str | None = None
    product_name: str | None = None
    quantity: int | None = None
    picked_qty: int | None = None
    lines_added: int | None = None
    total_qty: int | None = None


class MarketplaceUnloadBoxOut(BaseModel):
    id: str
    box_preset: str
    internal_barcode: str | None = None
    closed_at: str | None
    lines: list[MarketplaceUnloadBoxLineOut]


class MarketplaceUnloadBoxCreate(BaseModel):
    box_preset: str = Field(min_length=1, max_length=32)


class MarketplaceUnloadBoxBatchCreate(BaseModel):
    count: int = Field(ge=1, le=50)
    box_preset: str = Field(min_length=1, max_length=32)


class MarketplaceUnloadScanBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)
    storage_location_id: uuid.UUID | None = None
    quantity: int = Field(default=1, ge=1, le=1_000_000_000)
    allow_over_plan: bool = False


class MarketplaceUnloadLineCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)


class MarketplaceUnloadLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    picked_qty: int = 0
    has_discrepancy: bool = False


class MarketplaceUnloadRequestSummaryOut(BaseModel):
    id: str
    document_number: str | None = None
    warehouse_id: str
    warehouse_name: str
    status: str
    line_count: int = Field(default=0, ge=0)
    seller_id: str | None = None
    seller_name: str | None = None
    wb_mp_warehouse_id: int | None = None
    planned_shipment_date: str | None = None
    ff_modified: bool = False
    created_at: str


class MarketplaceUnloadPickAllocationOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    storage_location_id: str
    location_code: str
    quantity: int


class MarketplaceUnloadPickOptionLocationOut(BaseModel):
    storage_location_id: str
    location_code: str
    quantity: int
    reserved: int
    available: int


class MarketplaceUnloadPickOptionProductOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    planned_qty: int
    picked_qty: int
    locations: list[MarketplaceUnloadPickOptionLocationOut]


class MarketplaceUnloadPickScanBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)
    storage_location_id: uuid.UUID | None = None


class MarketplaceUnloadPickScanOut(BaseModel):
    kind: str
    storage_location_id: str | None = None
    location_code: str | None = None
    product_id: str | None = None
    sku_code: str | None = None
    product_name: str | None = None
    picked_qty: int | None = None
    allocation_quantity: int | None = None


class MarketplaceUnloadPickAddBody(BaseModel):
    storage_location_id: uuid.UUID | None = None
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)


class MarketplaceUnloadAttachBoxBody(BaseModel):
    barcode: str = Field(min_length=1, max_length=128)
    box_preset: str = Field(default="60_40_40", min_length=1, max_length=32)
    allow_over_plan: bool = False


class PickAllocationItemIn(BaseModel):
    product_id: uuid.UUID
    storage_location_id: uuid.UUID | None = None
    quantity: int = Field(ge=1, le=1_000_000_000)


class PickAllocationsSave(BaseModel):
    allocations: list[PickAllocationItemIn] = Field(default_factory=list)


class LinkedPackagingTaskOut(BaseModel):
    task_id: str
    status: str
    qty_done: int
    qty_total: int
    is_complete: bool


class MarketplaceUnloadRequestDetailOut(BaseModel):
    id: str
    document_number: str | None = None
    warehouse_id: str
    warehouse_name: str
    status: str
    seller_id: str | None = None
    seller_name: str | None = None
    wb_mp_warehouse_id: int | None = None
    planned_shipment_date: str | None = None
    ff_modified: bool = False
    created_at: str
    lines: list[MarketplaceUnloadLineOut]
    boxes: list[MarketplaceUnloadBoxOut] = Field(default_factory=list)
    pick_allocations: list[MarketplaceUnloadPickAllocationOut] = Field(default_factory=list)
    linked_packaging_task: LinkedPackagingTaskOut | None = None


def _box_scan_out(result: box_svc.BoxScanResult) -> MarketplaceUnloadBoxScanOut:
    if result.kind == "location":
        return MarketplaceUnloadBoxScanOut(
            kind="location",
            storage_location_id=str(result.storage_location_id)
            if result.storage_location_id is not None
            else None,
            location_code=result.location_code,
        )
    if result.kind == "ready_box":
        return MarketplaceUnloadBoxScanOut(
            kind="ready_box",
            lines_added=result.lines_added,
            total_qty=result.total_qty,
        )
    ln = result.box_line
    assert ln is not None
    p = ln.product
    return MarketplaceUnloadBoxScanOut(
        kind="product",
        storage_location_id=str(result.storage_location_id)
        if result.storage_location_id is not None
        else None,
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        quantity=int(ln.quantity),
        picked_qty=result.picked_qty,
    )


def _box_line_out(ln: MarketplaceUnloadBoxLine) -> MarketplaceUnloadBoxLineOut:
    p = ln.product
    return MarketplaceUnloadBoxLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        quantity=int(ln.quantity),
    )


def _box_out(b: MarketplaceUnloadBox) -> MarketplaceUnloadBoxOut:
    barcode: str | None = None
    if b.warehouse_box is not None:
        barcode = b.warehouse_box.internal_barcode
    return MarketplaceUnloadBoxOut(
        id=str(b.id),
        box_preset=b.box_preset,
        internal_barcode=barcode,
        closed_at=b.closed_at.isoformat() if b.closed_at is not None else None,
        lines=[_box_line_out(x) for x in b.lines],
    )


def _line_out(
    ln: MarketplaceUnloadLine,
    *,
    picked_qty: int = 0,
    show_pick_discrepancy: bool = False,
) -> MarketplaceUnloadLineOut:
    p = ln.product
    plan = int(ln.quantity)
    return MarketplaceUnloadLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        quantity=plan,
        picked_qty=picked_qty,
        has_discrepancy=show_pick_discrepancy and picked_qty != plan,
    )


def _picked_by_product(r: MarketplaceUnloadRequest) -> dict[uuid.UUID, int]:
    picked: dict[uuid.UUID, int] = {}
    for b in getattr(r, "boxes", []) or []:
        for bl in b.lines:
            pid = bl.product_id
            picked[pid] = picked.get(pid, 0) + int(bl.quantity)
    return picked


def _summary_out(
    r: MarketplaceUnloadRequest,
    *,
    warehouse_name: str,
    seller_name: str | None,
) -> MarketplaceUnloadRequestSummaryOut:
    return MarketplaceUnloadRequestSummaryOut(
        id=str(r.id),
        document_number=r.document_number,
        warehouse_id=str(r.warehouse_id),
        warehouse_name=warehouse_name,
        status=r.status,
        line_count=len(r.lines),
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        wb_mp_warehouse_id=int(r.wb_mp_warehouse_id) if r.wb_mp_warehouse_id is not None else None,
        planned_shipment_date=r.planned_shipment_date.isoformat()
        if r.planned_shipment_date is not None
        else None,
        ff_modified=bool(r.ff_modified),
        created_at=r.created_at.isoformat(),
    )


def _pick_alloc_out(alloc: MarketplaceUnloadPickAllocation) -> MarketplaceUnloadPickAllocationOut:
    p = alloc.product
    loc = alloc.storage_location
    return MarketplaceUnloadPickAllocationOut(
        id=str(alloc.id),
        product_id=str(alloc.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        storage_location_id=str(alloc.storage_location_id),
        location_code=loc.code,
        quantity=int(alloc.quantity),
    )


def _linked_packaging_out(
    progress: pkg_svc.PackagingTaskProgress,
) -> LinkedPackagingTaskOut:
    return LinkedPackagingTaskOut(
        task_id=str(progress.task_id),
        status=progress.status,
        qty_done=progress.qty_done,
        qty_total=progress.qty_total,
        is_complete=progress.is_complete,
    )


def _detail_out(
    r: MarketplaceUnloadRequest,
    *,
    warehouse_name: str,
    seller_name: str | None,
    linked_packaging_task: LinkedPackagingTaskOut | None = None,
    seller_plan_only: bool = False,
) -> MarketplaceUnloadRequestDetailOut:
    boxes = [] if seller_plan_only else [_box_out(b) for b in getattr(r, "boxes", []) or []]
    picks = (
        []
        if seller_plan_only
        else [_pick_alloc_out(a) for a in getattr(r, "pick_allocations", []) or []]
    )
    picked_map = {} if seller_plan_only else _picked_by_product(r)
    show_pick_discrepancy = (not seller_plan_only) and r.status in (
        "confirmed",
        "collecting",
        "shipped",
    )
    return MarketplaceUnloadRequestDetailOut(
        id=str(r.id),
        document_number=r.document_number,
        warehouse_id=str(r.warehouse_id),
        warehouse_name=warehouse_name,
        status=r.status,
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        wb_mp_warehouse_id=int(r.wb_mp_warehouse_id) if r.wb_mp_warehouse_id is not None else None,
        planned_shipment_date=r.planned_shipment_date.isoformat()
        if r.planned_shipment_date is not None
        else None,
        ff_modified=bool(r.ff_modified),
        created_at=r.created_at.isoformat(),
        lines=[
            _line_out(
                ln,
                picked_qty=picked_map.get(ln.product_id, 0),
                show_pick_discrepancy=show_pick_discrepancy,
            )
            for ln in r.lines
        ],
        boxes=boxes,
        pick_allocations=picks,
        linked_packaging_task=None if seller_plan_only else linked_packaging_task,
    )


def _require_ff_execution(user: User) -> None:
    """DEC-015 / TASK-020: boxes, cells, packaging complete, ship — FF only."""
    if user.role == FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _seller_plan_only(user: User) -> bool:
    return user.role == FULFILLMENT_SELLER


async def _detail_with_packaging(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    r: MarketplaceUnloadRequest,
    *,
    warehouse_name: str,
    seller_name: str | None,
    sync_packaging: bool = False,
    seller_plan_only: bool = False,
) -> MarketplaceUnloadRequestDetailOut:
    linked: LinkedPackagingTaskOut | None = None
    if not seller_plan_only:
        progress = await pkg_svc.progress_for_unload(
            session,
            tenant_id,
            r.id,
            sync_from_pick=sync_packaging and r.status in ("confirmed", "collecting", "shipped"),
        )
        if progress is not None:
            linked = _linked_packaging_out(progress)
    return _detail_out(
        r,
        warehouse_name=warehouse_name,
        seller_name=seller_name,
        linked_packaging_task=linked,
        seller_plan_only=seller_plan_only,
    )


def _map_mu_err(exc: MarketplaceUnloadError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if exc.code == "not_editable":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="not_editable")
    if exc.code == "bad_status":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="bad_status")
    if exc.code == "line_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="line_not_found")
    if exc.code == "product_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_not_found",
        )
    if exc.code == "duplicate_line":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_line")
    if exc.code == "wb_mp_warehouse_unknown":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="wb_mp_warehouse_unknown",
        )
    if exc.code == "wb_mp_warehouse_required":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="wb_mp_warehouse_required",
        )
    if exc.code == "planned_shipment_date_required":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="planned_shipment_date_required",
        )
    if exc.code == "forbidden":
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if exc.code == "product_seller_mismatch":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="product_seller_mismatch",
        )
    if exc.code == "insufficient_available":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="insufficient_available",
        )
    if exc.code == "no_lines":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_lines")
    if exc.code == "packaging_instructions_required":
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="packaging_instructions_required",
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


def _map_pick_err(exc: MarketplaceUnloadPickError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if exc.code in ("not_editable", "bad_status", "open_box_exists"):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code in (
        "invalid_quantity",
        "product_not_in_shipment",
        "location_not_found",
        "location_required",
        "product_not_found",
        "product_seller_mismatch",
        "insufficient_available",
        "barcode_empty",
        "barcode_unknown",
        "pick_required",
        "no_lines",
        "distribution_incomplete",
        "wb_mp_warehouse_required",
        "seller_required",
        "open_box_required",
        "box_not_found",
        "box_closed",
        "planned_shipment_date_required",
        "packaging_not_done",
        "marking_not_done",
        "plan_limit_exceeded",
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


def _map_box_err(exc: MarketplaceUnloadBoxError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if exc.code in (
        "not_editable",
        "open_box_exists",
        "box_closed",
        "box_already_attached",
        "warehouse_mismatch",
        "box_not_empty",
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    if exc.code in (
        "invalid_preset",
        "invalid_quantity",
        "invalid_batch_count",
        "barcode_empty",
        "barcode_unknown",
        "box_barcode_unknown",
        "box_needs_location",
        "product_not_in_shipment",
        "seller_required",
        "location_required",
        "open_box_required",
        "insufficient_available",
        "packaging_not_done",
        "marking_not_done",
        "box_empty",
        "plan_limit_exceeded",
        "line_not_found",
        "line_empty",
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        )
    if exc.code == "box_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


async def _get_visible_request(
    session: AsyncSession,
    user: User,
    request_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials | None = None,
    *,
    effective_seller_id: uuid.UUID | None = None,
) -> MarketplaceUnloadRequest:
    if effective_seller_id is None:
        effective_seller_id = await resolve_effective_seller_id(
            session, user, credentials
        )
    r = await svc.get_request(session, user.tenant_id, request_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    try:
        svc.assert_request_visible(user, r, effective_seller_id=effective_seller_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return r


@router.get("", response_model=list[MarketplaceUnloadRequestSummaryOut])
async def list_marketplace_unloads(
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[MarketplaceUnloadRequestSummaryOut]:
    seller_filter = effective_seller_id if user.role == FULFILLMENT_SELLER else None
    rows = await svc.list_requests(session, user.tenant_id, seller_id=seller_filter)
    return [
        _summary_out(
            r,
            warehouse_name=r.warehouse.name,
            seller_name=r.seller.name if r.seller is not None else None,
        )
        for r in rows
    ]


@router.get("/{request_id}", response_model=MarketplaceUnloadRequestDetailOut)
async def get_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MarketplaceUnloadRequestDetailOut:
    r = await _get_visible_request(
        session,
        user,
        request_id,
        credentials,
        effective_seller_id=effective_seller_id,
    )
    return await _detail_with_packaging(
        session,
        user.tenant_id,
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
        sync_packaging=True,
        seller_plan_only=_seller_plan_only(user),
    )


@router.post(
    "",
    response_model=MarketplaceUnloadRequestSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_marketplace_unload(
    body: MarketplaceUnloadRequestCreate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestSummaryOut:
    try:
        r = await svc.create_request(
            session,
            user.tenant_id,
            warehouse_id=body.warehouse_id,
            seller_id=body.seller_id,
            wb_mp_warehouse_id=body.wb_mp_warehouse_id,
        )
    except MarketplaceUnloadError as exc:
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
        raise _map_mu_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    assert r2 is not None
    wh = await get_warehouse(session, user.tenant_id, r2.warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="warehouse_missing_after_create",
        )
    seller_name: str | None = None
    if r2.seller_id is not None:
        sl = await session.get(Seller, r2.seller_id)
        seller_name = sl.name if sl is not None else None
    return _summary_out(r2, warehouse_name=wh.name, seller_name=seller_name)


@router.post(
    "/seller",
    response_model=MarketplaceUnloadRequestSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_seller_marketplace_unload(
    body: SellerMarketplaceUnloadRequestCreate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MarketplaceUnloadRequestSummaryOut:
    if user.role != FULFILLMENT_SELLER or effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        r = await svc.create_request(
            session,
            user.tenant_id,
            warehouse_id=body.warehouse_id,
            seller_id=effective_seller_id,
            wb_mp_warehouse_id=body.wb_mp_warehouse_id,
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    assert r2 is not None
    wh = await get_warehouse(session, user.tenant_id, r2.warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="warehouse_missing_after_create",
        )
    sl = await session.get(Seller, effective_seller_id)
    return _summary_out(r2, warehouse_name=wh.name, seller_name=sl.name if sl else None)


@router.patch(
    "/{request_id}",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def update_marketplace_unload(
    request_id: uuid.UUID,
    body: MarketplaceUnloadRequestUpdate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadRequestDetailOut:
    await _get_visible_request(session, user, request_id, credentials)
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="no_fields",
        )
    try:
        r: MarketplaceUnloadRequest | None = None
        if "wb_mp_warehouse_id" in fields:
            wb_id = fields["wb_mp_warehouse_id"]
            if wb_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="wb_mp_warehouse_required",
                )
            r = await svc.set_wb_mp_warehouse(
                session,
                user.tenant_id,
                request_id,
                wb_mp_warehouse_id=int(wb_id),
            )
        if "planned_shipment_date" in fields:
            raw_date = fields["planned_shipment_date"]
            planned = raw_date if isinstance(raw_date, date) else None
            r = await svc.patch_request(
                session,
                user.tenant_id,
                request_id,
                user=user,
                planned_shipment_date=planned,
                set_planned_shipment_date=True,
            )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="patch_failed",
        )
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
        seller_plan_only=_seller_plan_only(user),
    )


@router.post(
    "/{request_id}/lines",
    response_model=MarketplaceUnloadLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_marketplace_unload_line(
    request_id: uuid.UUID,
    body: MarketplaceUnloadLineCreate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadLineOut:
    await _get_visible_request(session, user, request_id, credentials)
    allow_ff_confirmed = user.role == FULFILLMENT_ADMIN
    try:
        line = await svc.add_line(
            session,
            user.tenant_id,
            request_id,
            product_id=body.product_id,
            quantity=body.quantity,
            allow_ff_confirmed=allow_ff_confirmed,
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _line_out(line)


@router.put(
    "/{request_id}/lines",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def replace_marketplace_unload_lines(
    request_id: uuid.UUID,
    body: MarketplaceUnloadLinesBulkReplace,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadRequestDetailOut:
    await _get_visible_request(session, user, request_id, credentials)
    pairs = [(item.product_id, item.quantity) for item in body.lines]
    try:
        r = await svc.replace_lines(
            session, user.tenant_id, request_id, lines=pairs
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
        seller_plan_only=_seller_plan_only(user),
    )


@router.post(
    "/{request_id}/plan",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def plan_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadRequestDetailOut:
    await _get_visible_request(session, user, request_id, credentials)
    try:
        r = await svc.plan_request(session, user.tenant_id, request_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
        seller_plan_only=_seller_plan_only(user),
    )


@router.post(
    "/{request_id}/unplan",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def unplan_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadRequestDetailOut:
    await _get_visible_request(session, user, request_id, credentials)
    try:
        r = await svc.unplan_request(session, user.tenant_id, request_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
        seller_plan_only=_seller_plan_only(user),
    )


@router.post(
    "/{request_id}/cancel",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def cancel_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> MarketplaceUnloadRequestDetailOut:
    _require_ff_execution(user)
    await _get_visible_request(session, user, request_id, credentials)
    try:
        r = await svc.cancel_request(session, user.tenant_id, request_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.post(
    "/{request_id}/confirm",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def confirm_marketplace_unload(
    request_id: uuid.UUID,
    body: MarketplaceUnloadConfirmBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestDetailOut:
    _require_ff_execution(user)
    try:
        r = await svc.confirm_request(
            session,
            user.tenant_id,
            request_id,
            planned_shipment_date=body.planned_shipment_date,
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.get(
    "/{request_id}/pick-options",
    response_model=list[MarketplaceUnloadPickOptionProductOut],
)
async def get_marketplace_unload_pick_options(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MarketplaceUnloadPickOptionProductOut]:
    _require_ff_execution(user)
    try:
        opts = await pick_svc.get_pick_options(session, user.tenant_id, request_id)
    except MarketplaceUnloadPickError as exc:
        raise _map_pick_err(exc) from None
    return [
        MarketplaceUnloadPickOptionProductOut(
            product_id=str(o.product_id),
            sku_code=o.sku_code,
            product_name=o.product_name,
            planned_qty=o.planned_qty,
            picked_qty=o.picked_qty,
            locations=[
                MarketplaceUnloadPickOptionLocationOut(
                    storage_location_id=str(loc.storage_location_id),
                    location_code=loc.location_code,
                    quantity=loc.quantity,
                    reserved=loc.reserved,
                    available=loc.available,
                )
                for loc in o.locations
            ],
        )
        for o in opts
    ]


@router.post(
    "/{request_id}/pick/scan",
    response_model=MarketplaceUnloadPickScanOut,
    deprecated=True,
    summary="Deprecated: use POST .../boxes/{box_id}/scan for TSD location→product flow",
)
async def scan_marketplace_unload_pick(
    request_id: uuid.UUID,
    body: MarketplaceUnloadPickScanBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadPickScanOut:
    _require_ff_execution(user)
    try:
        result = await pick_svc.pick_scan(
            session,
            user.tenant_id,
            request_id,
            barcode=body.barcode,
            storage_location_id=body.storage_location_id,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_pick_err(exc) from None
    return MarketplaceUnloadPickScanOut(
        kind=result.kind,
        storage_location_id=str(result.storage_location_id)
        if result.storage_location_id is not None
        else None,
        location_code=result.location_code,
        product_id=str(result.product_id) if result.product_id is not None else None,
        sku_code=result.sku_code,
        product_name=result.product_name,
        picked_qty=result.picked_qty,
        allocation_quantity=result.allocation_quantity,
    )


@router.post(
    "/{request_id}/pick/add",
    response_model=MarketplaceUnloadPickAllocationOut,
    status_code=status.HTTP_200_OK,
)
async def add_marketplace_unload_pick_qty(
    request_id: uuid.UUID,
    body: MarketplaceUnloadPickAddBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadPickAllocationOut:
    _require_ff_execution(user)
    try:
        alloc = await pick_svc.add_pick_qty(
            session,
            user.tenant_id,
            request_id,
            storage_location_id=body.storage_location_id,
            product_id=body.product_id,
            quantity=body.quantity,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_pick_err(exc) from None
    return _pick_alloc_out(alloc)


@router.put(
    "/{request_id}/pick-allocations",
    response_model=list[MarketplaceUnloadPickAllocationOut],
    deprecated=True,
)
async def save_marketplace_unload_pick_allocations(
    request_id: uuid.UUID,
    body: PickAllocationsSave,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MarketplaceUnloadPickAllocationOut]:
    """Admin-only legacy bypass of box-based collect. Do not use from UI."""
    if user.role != FULFILLMENT_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_only",
        )
    rows = [
        pick_svc.PickAllocationRow(
            product_id=item.product_id,
            storage_location_id=item.storage_location_id,
            quantity=item.quantity,
        )
        for item in body.allocations
    ]
    try:
        allocs = await pick_svc.save_pick_allocations(
            session, user.tenant_id, request_id, rows
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_pick_err(exc) from None
    return [_pick_alloc_out(a) for a in allocs]


@router.post(
    "/{request_id}/submit",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def submit_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestDetailOut:
    _require_ff_execution(user)
    try:
        await svc.submit_request(session, user.tenant_id, request_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, request_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.delete(
    "/{request_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_marketplace_unload_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> None:
    await _get_visible_request(session, user, request_id, credentials)
    allow_ff_confirmed = user.role == FULFILLMENT_ADMIN
    try:
        await svc.delete_line(
            session,
            user.tenant_id,
            request_id,
            line_id,
            allow_ff_confirmed=allow_ff_confirmed,
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None


@router.post(
    "/{request_id}/ship",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def ship_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: MarketplaceUnloadShipBody | None = None,
) -> MarketplaceUnloadRequestDetailOut:
    _require_ff_execution(user)
    try:
        await pick_svc.ship_request(
            session,
            user.tenant_id,
            request_id,
            acknowledge_discrepancy=bool(body.acknowledge_discrepancy) if body else False,
        )
    except MarketplaceUnloadPickError as exc:
        raise _map_pick_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, request_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.post(
    "/{request_id}/boxes",
    response_model=MarketplaceUnloadBoxOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_marketplace_unload_box(
    request_id: uuid.UUID,
    body: MarketplaceUnloadBoxCreate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxOut:
    _require_ff_execution(user)
    try:
        b = await box_svc.create_open_box(
            session, user.tenant_id, request_id, box_preset=body.box_preset
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, request_id)
    assert r is not None
    for ob in r.boxes:
        if ob.id == b.id:
            return _box_out(ob)
    return MarketplaceUnloadBoxOut(
        id=str(b.id),
        box_preset=b.box_preset,
        internal_barcode=b.warehouse_box.internal_barcode if b.warehouse_box else None,
        closed_at=None,
        lines=[],
    )


@router.post(
    "/{request_id}/boxes/batch",
    response_model=list[MarketplaceUnloadBoxOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_marketplace_unload_boxes_batch(
    request_id: uuid.UUID,
    body: MarketplaceUnloadBoxBatchCreate,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MarketplaceUnloadBoxOut]:
    _require_ff_execution(user)
    try:
        boxes = await box_svc.create_boxes_batch(
            session,
            user.tenant_id,
            request_id,
            count=body.count,
            box_preset=body.box_preset,
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    return [
        MarketplaceUnloadBoxOut(
            id=str(b.id),
            box_preset=b.box_preset,
            internal_barcode=b.warehouse_box.internal_barcode if b.warehouse_box else None,
            closed_at=b.closed_at.isoformat() if b.closed_at else None,
            lines=[],
        )
        for b in boxes
    ]


@router.post(
    "/{request_id}/boxes/attach",
    response_model=MarketplaceUnloadBoxOut,
    status_code=status.HTTP_201_CREATED,
)
async def attach_marketplace_unload_box(
    request_id: uuid.UUID,
    body: MarketplaceUnloadAttachBoxBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxOut:
    _require_ff_execution(user)
    try:
        b = await box_svc.attach_existing_box_by_barcode(
            session,
            user.tenant_id,
            request_id,
            barcode=body.barcode,
            box_preset=body.box_preset,
            allow_over_plan=body.allow_over_plan,
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, b.request_id)
    assert r is not None
    for ob in r.boxes:
        if ob.id == b.id:
            return _box_out(ob)
    return _box_out(b)


@router.post(
    "/{request_id}/boxes/{box_id}/scan",
    response_model=MarketplaceUnloadBoxScanOut,
    status_code=status.HTTP_200_OK,
    summary="TSD scan: location barcode (optional) then product → box line",
)
async def scan_marketplace_unload_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    body: MarketplaceUnloadScanBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxScanOut:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        result = await box_svc.scan_barcode_into_box(
            session,
            user.tenant_id,
            box_id,
            barcode=body.barcode,
            storage_location_id=body.storage_location_id,
            quantity=body.quantity,
            allow_over_plan=body.allow_over_plan,
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    return _box_scan_out(result)


@router.post(
    "/{request_id}/boxes/{box_id}/manual-line",
    response_model=MarketplaceUnloadBoxLineOut,
    status_code=status.HTTP_200_OK,
)
async def manual_marketplace_unload_box_line(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    body: MarketplaceUnloadManualBoxLineBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxLineOut:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        ln = await box_svc.add_manual_qty_to_box(
            session,
            user.tenant_id,
            box_id,
            product_id=body.product_id,
            storage_location_id=body.storage_location_id,
            quantity=body.quantity,
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    return _box_line_out(ln)


@router.post(
    "/{request_id}/boxes/{box_id}/close",
    response_model=MarketplaceUnloadBoxOut,
)
async def close_marketplace_unload_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxOut:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        b = await box_svc.close_box(session, user.tenant_id, box_id)
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, b.request_id)
    assert r is not None
    for ob in r.boxes:
        if ob.id == b.id:
            return _box_out(ob)
    return MarketplaceUnloadBoxOut(
        id=str(b.id),
        box_preset=b.box_preset,
        closed_at=b.closed_at.isoformat() if b.closed_at else None,
        lines=[],
    )


@router.post(
    "/{request_id}/boxes/{box_id}/copy",
    response_model=MarketplaceUnloadBoxOut,
    status_code=status.HTTP_201_CREATED,
)
async def copy_marketplace_unload_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadBoxOut:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        b = await box_svc.copy_box(session, user.tenant_id, box_id)
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    r = await svc.get_request(session, user.tenant_id, request_id)
    assert r is not None
    for ob in r.boxes:
        if ob.id == b.id:
            return _box_out(ob)
    return _box_out(b)


@router.delete(
    "/{request_id}/boxes/{box_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_marketplace_unload_box(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        await box_svc.delete_box(session, user.tenant_id, box_id)
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None


@router.post(
    "/{request_id}/boxes/{box_id}/lines/{line_id}/remove",
    response_model=MarketplaceUnloadBoxLineOut | None,
)
async def remove_marketplace_unload_box_line(
    request_id: uuid.UUID,
    box_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    body: MarketplaceUnloadBoxLineRemoveBody = _DEFAULT_BOX_LINE_REMOVE,
) -> MarketplaceUnloadBoxLineOut | None:
    _require_ff_execution(user)
    bx = await session.get(MarketplaceUnloadBox, box_id)
    if bx is None or bx.request_id != request_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="box_not_found")
    try:
        line = await box_svc.remove_box_line(
            session,
            user.tenant_id,
            box_id,
            line_id,
            quantity=body.quantity,
        )
    except MarketplaceUnloadBoxError as exc:
        raise _map_box_err(exc) from None
    if line is None:
        return None
    prod = line.product
    return MarketplaceUnloadBoxLineOut(
        id=str(line.id),
        product_id=str(line.product_id),
        sku_code=prod.sku_code if prod else "",
        product_name=prod.name if prod else "",
        quantity=int(line.quantity),
    )
