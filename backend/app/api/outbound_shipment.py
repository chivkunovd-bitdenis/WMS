from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin, seller_line_product_scope
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.inventory_movement import InventoryMovement
from app.models.outbound_shipment import OutboundShipmentLine
from app.models.product import Product
from app.models.user import User
from app.services import outbound_shipment_service as svc
from app.services.outbound_shipment_service import OutboundShipmentError

router = APIRouter(
    prefix="/operations/outbound-shipment-requests",
    tags=["operations"],
)


class OutboundShipmentRequestCreate(BaseModel):
    warehouse_id: uuid.UUID


class OutboundShipmentLineCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)
    storage_location_id: uuid.UUID | None = None


class OutboundShipmentLineStoragePatch(BaseModel):
    storage_location_id: uuid.UUID


class OutboundShipmentLineShipBody(BaseModel):
    quantity: int = Field(ge=1, le=1_000_000_000)


class OutboundShipmentLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    shipped_qty: int
    storage_location_id: str | None
    storage_location_code: str | None


class OutboundShipmentRequestSummaryOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    line_count: int


class OutboundShipmentRequestOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    lines: list[OutboundShipmentLineOut]


class OutboundMovementOut(BaseModel):
    id: str
    product_id: str
    storage_location_id: str
    quantity_delta: int
    movement_type: str
    outbound_shipment_line_id: str
    created_at: str


def _line_out(line: OutboundShipmentLine, product: Product) -> OutboundShipmentLineOut:
    loc = line.storage_location
    return OutboundShipmentLineOut(
        id=str(line.id),
        product_id=str(line.product_id),
        sku_code=product.sku_code,
        product_name=product.name,
        quantity=line.quantity,
        shipped_qty=line.shipped_qty,
        storage_location_id=str(line.storage_location_id)
        if line.storage_location_id
        else None,
        storage_location_code=loc.code if loc is not None else None,
    )


def _movement_out(m: InventoryMovement) -> OutboundMovementOut:
    if m.outbound_shipment_line_id is None:
        msg = "outbound movement missing line ref"
        raise RuntimeError(msg)
    return OutboundMovementOut(
        id=str(m.id),
        product_id=str(m.product_id),
        storage_location_id=str(m.storage_location_id),
        quantity_delta=m.quantity_delta,
        movement_type=m.movement_type,
        outbound_shipment_line_id=str(m.outbound_shipment_line_id),
        created_at=m.created_at.isoformat(),
    )


def _map_out_err(exc: OutboundShipmentError) -> HTTPException:
    code = exc.code
    mapping: dict[str, tuple[int, str]] = {
        "warehouse_not_found": (status.HTTP_404_NOT_FOUND, "warehouse_not_found"),
        "request_not_found": (status.HTTP_404_NOT_FOUND, "request_not_found"),
        "line_not_found": (status.HTTP_404_NOT_FOUND, "line_not_found"),
        "product_not_found": (status.HTTP_404_NOT_FOUND, "product_not_found"),
        "location_not_found": (status.HTTP_404_NOT_FOUND, "location_not_found"),
        "not_draft": (status.HTTP_409_CONFLICT, "not_draft"),
        "not_editable": (status.HTTP_409_CONFLICT, "not_editable"),
        "not_submitted": (status.HTTP_409_CONFLICT, "not_submitted"),
        "already_posted": (status.HTTP_409_CONFLICT, "already_posted"),
        "duplicate_line": (status.HTTP_409_CONFLICT, "duplicate_line"),
        "invalid_qty": (status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_qty"),
        "submit_empty": (status.HTTP_422_UNPROCESSABLE_ENTITY, "submit_empty"),
        "lines_missing_storage": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "lines_missing_storage",
        ),
        "insufficient_stock": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "insufficient_stock",
        ),
        "nothing_to_ship": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "nothing_to_ship",
        ),
        "storage_not_assigned": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "storage_not_assigned",
        ),
        "line_closed": (status.HTTP_409_CONFLICT, "line_closed"),
        "mixed_seller_lines": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "mixed_seller_lines",
        ),
        "seller_not_found": (status.HTTP_404_NOT_FOUND, "seller_not_found"),
        "product_seller_mismatch": (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "product_seller_mismatch",
        ),
    }
    st, detail = mapping.get(code, (status.HTTP_400_BAD_REQUEST, code))
    return HTTPException(status_code=st, detail=detail)


@router.get("", response_model=list[OutboundShipmentRequestSummaryOut])
async def list_outbound_requests(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[OutboundShipmentRequestSummaryOut]:
    rows = await svc.list_requests(
        session,
        user.tenant_id,
        seller_product_owner_id=seller_scope,
    )
    return [
        OutboundShipmentRequestSummaryOut(
            id=str(r.id),
            warehouse_id=str(r.warehouse_id),
            status=r.status,
            line_count=len(r.lines),
        )
        for r in rows
    ]


@router.post("", response_model=OutboundShipmentRequestOut, status_code=status.HTTP_201_CREATED)
async def create_outbound_request(
    body: OutboundShipmentRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OutboundShipmentRequestOut:
    if user.role == FULFILLMENT_ADMIN:
        owning_seller_id: uuid.UUID | None = None
    elif user.role == FULFILLMENT_SELLER:
        if user.seller_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="seller_not_linked",
            )
        owning_seller_id = user.seller_id
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
        )
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    return OutboundShipmentRequestOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        lines=[],
    )


@router.get("/{request_id}", response_model=OutboundShipmentRequestOut)
async def get_outbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> OutboundShipmentRequestOut:
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
    return OutboundShipmentRequestOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        lines=[_line_out(ln, ln.product) for ln in r.lines],
    )


@router.get(
    "/{request_id}/movements",
    response_model=list[OutboundMovementOut],
)
async def list_outbound_movements(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[OutboundMovementOut]:
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
    movements = await svc.list_movements_for_outbound_request(
        session,
        user.tenant_id,
        request_id,
        seller_product_owner_id=seller_scope,
    )
    return [_movement_out(m) for m in movements]


@router.post(
    "/{request_id}/lines",
    response_model=OutboundShipmentLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_outbound_line(
    request_id: uuid.UUID,
    body: OutboundShipmentLineCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> OutboundShipmentLineOut:
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
            quantity=body.quantity,
            storage_location_id=body.storage_location_id,
            seller_product_owner_id=line_seller_scope,
        )
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    return _line_out(line, prod)


@router.post(
    "/{request_id}/lines/{line_id}/ship",
    response_model=OutboundShipmentRequestOut,
)
async def ship_outbound_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: OutboundShipmentLineShipBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OutboundShipmentRequestOut:
    try:
        r = await svc.ship_line(
            session,
            user.tenant_id,
            request_id,
            line_id,
            quantity=body.quantity,
        )
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return OutboundShipmentRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        lines=[_line_out(ln, ln.product) for ln in r2.lines],
    )


@router.patch(
    "/{request_id}/lines/{line_id}",
    response_model=OutboundShipmentLineOut,
)
async def patch_outbound_line_storage(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: OutboundShipmentLineStoragePatch,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OutboundShipmentLineOut:
    try:
        line = await svc.set_line_storage_location(
            session,
            user.tenant_id,
            request_id,
            line_id,
            storage_location_id=body.storage_location_id,
        )
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    await session.refresh(line, attribute_names=["storage_location"])
    return _line_out(line, prod)


@router.post("/{request_id}/submit", response_model=OutboundShipmentRequestOut)
async def submit_outbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OutboundShipmentRequestOut:
    try:
        r = await svc.submit_request(session, user.tenant_id, request_id)
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return OutboundShipmentRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        lines=[_line_out(ln, ln.product) for ln in r2.lines],
    )


@router.post("/{request_id}/post", response_model=OutboundShipmentRequestOut)
async def post_outbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OutboundShipmentRequestOut:
    try:
        r = await svc.post_request(session, user.tenant_id, request_id)
    except OutboundShipmentError as exc:
        raise _map_out_err(exc) from None
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return OutboundShipmentRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        lines=[_line_out(ln, ln.product) for ln in r2.lines],
    )
