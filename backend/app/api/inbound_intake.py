from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin, seller_line_product_scope
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.inbound_intake import InboundIntakeLine
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.user import User
from app.services import inbound_intake_service as svc
from app.services import inventory_service as inv_svc
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


class InboundIntakeLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    expected_qty: int
    actual_qty: int | None
    posted_qty: int
    storage_location_id: str | None
    storage_location_code: str | None


class InboundIntakeRequestSummaryOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    line_count: int
    planned_delivery_date: str | None = None
    has_discrepancy: bool = False
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str


class InboundIntakeRequestOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    planned_delivery_date: str | None = None
    has_discrepancy: bool = False
    lines: list[InboundIntakeLineOut]


class InventoryMovementOut(BaseModel):
    id: str
    product_id: str
    storage_location_id: str
    quantity_delta: int
    movement_type: str
    inbound_intake_line_id: str | None
    created_at: str


def _line_out_from_orm(line: InboundIntakeLine, product: Product) -> InboundIntakeLineOut:
    loc = line.storage_location
    return InboundIntakeLineOut(
        id=str(line.id),
        product_id=str(line.product_id),
        sku_code=product.sku_code,
        product_name=product.name,
        expected_qty=line.expected_qty,
        actual_qty=line.actual_qty,
        posted_qty=line.posted_qty,
        storage_location_id=str(line.storage_location_id)
        if line.storage_location_id
        else None,
        storage_location_code=loc.code if loc is not None else None,
    )


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
            warehouse_id=str(r.warehouse_id),
            status=r.status,
            line_count=len(r.lines),
            planned_delivery_date=r.planned_delivery_date.isoformat()
            if r.planned_delivery_date is not None
            else None,
            has_discrepancy=bool(getattr(r, "has_discrepancy", False)),
            seller_id=str(r.seller_id) if r.seller_id is not None else None,
            seller_name=r.seller.name if r.seller is not None else None,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.post("", response_model=InboundIntakeRequestOut, status_code=status.HTTP_201_CREATED)
async def create_inbound_request(
    body: InboundIntakeRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
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
    return InboundIntakeRequestOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        planned_delivery_date=r.planned_delivery_date.isoformat()
        if r.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r, "has_discrepancy", False)),
        lines=[],
    )


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
        lines_out.append(_line_out_from_orm(ln, p))
    return InboundIntakeRequestOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        planned_delivery_date=r.planned_delivery_date.isoformat()
        if r.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r, "has_discrepancy", False)),
        lines=lines_out,
    )


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
    try:
        r = await svc.patch_request_planned_delivery(
            session,
            user.tenant_id,
            request_id,
            planned_delivery_date=body.planned_delivery_date,
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
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


@router.post("/{request_id}/primary-accept", response_model=InboundIntakeRequestOut)
async def primary_accept_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.primary_accept_request(session, user.tenant_id, request_id)
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
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


@router.patch(
    "/{request_id}/lines/{line_id}/actual",
    response_model=InboundIntakeLineOut,
)
async def patch_inbound_line_actual(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineActualPatch,
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
        if exc.code == "not_verifying":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_verifying",
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
    return _line_out_from_orm(line, prod)


@router.post("/{request_id}/verify", response_model=InboundIntakeRequestOut)
async def complete_inbound_verification(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.complete_verification(session, user.tenant_id, request_id)
    except InboundIntakeError as exc:
        if exc.code == "request_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="request_not_found",
            ) from None
        if exc.code == "not_verifying":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="not_verifying",
            ) from None
        if exc.code == "actual_missing":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="actual_missing",
            ) from None
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


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
    return _line_out_from_orm(line, prod)


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
    return _line_out_from_orm(line, prod)


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
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
    return _line_out_from_orm(line, prod)


@router.post(
    "/{request_id}/lines/{line_id}/receive",
    response_model=InboundIntakeRequestOut,
)
async def receive_inbound_line(
    request_id: uuid.UUID,
    line_id: uuid.UUID,
    body: InboundIntakeLineReceiveBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


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
        raise
    r2 = await svc.get_request(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request_missing",
        )
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


@router.post("/{request_id}/post", response_model=InboundIntakeRequestOut)
async def post_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
    return InboundIntakeRequestOut(
        id=str(r2.id),
        warehouse_id=str(r2.warehouse_id),
        status=r2.status,
        planned_delivery_date=r2.planned_delivery_date.isoformat()
        if r2.planned_delivery_date is not None
        else None,
        has_discrepancy=bool(getattr(r2, "has_discrepancy", False)),
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )
