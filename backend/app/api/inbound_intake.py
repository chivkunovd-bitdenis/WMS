from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.inbound_intake import InboundIntakeLine
from app.models.product import Product
from app.models.user import User
from app.services import inbound_intake_service as svc
from app.services.inbound_intake_service import InboundIntakeError

router = APIRouter(
    prefix="/operations/inbound-intake-requests",
    tags=["operations"],
)


class InboundIntakeRequestCreate(BaseModel):
    warehouse_id: uuid.UUID


class InboundIntakeLineCreate(BaseModel):
    product_id: uuid.UUID
    expected_qty: int = Field(ge=1, le=1_000_000_000)


class InboundIntakeLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    expected_qty: int


class InboundIntakeRequestSummaryOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    line_count: int


class InboundIntakeRequestOut(BaseModel):
    id: str
    warehouse_id: str
    status: str
    lines: list[InboundIntakeLineOut]


class InboundIntakePostBody(BaseModel):
    storage_location_id: uuid.UUID


def _line_out_from_orm(line: InboundIntakeLine, product: Product) -> InboundIntakeLineOut:
    return InboundIntakeLineOut(
        id=str(line.id),
        product_id=str(line.product_id),
        sku_code=product.sku_code,
        product_name=product.name,
        expected_qty=line.expected_qty,
    )


@router.get("", response_model=list[InboundIntakeRequestSummaryOut])
async def list_inbound_requests(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[InboundIntakeRequestSummaryOut]:
    rows = await svc.list_requests(session, user.tenant_id)
    return [
        InboundIntakeRequestSummaryOut(
            id=str(r.id),
            warehouse_id=str(r.warehouse_id),
            status=r.status,
            line_count=len(r.lines),
        )
        for r in rows
    ]


@router.post("", response_model=InboundIntakeRequestOut, status_code=status.HTTP_201_CREATED)
async def create_inbound_request(
    body: InboundIntakeRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.create_request(
            session, user.tenant_id, warehouse_id=body.warehouse_id
        )
    except InboundIntakeError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        raise
    return InboundIntakeRequestOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        status=r.status,
        lines=[],
    )


@router.get("/{request_id}", response_model=InboundIntakeRequestOut)
async def get_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    r = await svc.get_request(session, user.tenant_id, request_id)
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
        lines=lines_out,
    )


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
) -> InboundIntakeLineOut:
    try:
        line = await svc.add_line(
            session,
            user.tenant_id,
            request_id,
            product_id=body.product_id,
            expected_qty=body.expected_qty,
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_qty",
            ) from None
        if exc.code == "duplicate_line":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="duplicate_line",
            ) from None
        raise
    prod = await session.get(Product, line.product_id)
    if prod is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="product_missing",
        )
    return _line_out_from_orm(line, prod)


@router.post("/{request_id}/submit", response_model=InboundIntakeRequestOut)
async def submit_inbound_request(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.submit_request(session, user.tenant_id, request_id)
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
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )


@router.post("/{request_id}/post", response_model=InboundIntakeRequestOut)
async def post_inbound_request(
    request_id: uuid.UUID,
    body: InboundIntakePostBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InboundIntakeRequestOut:
    try:
        r = await svc.post_request(
            session,
            user.tenant_id,
            request_id,
            storage_location_id=body.storage_location_id,
        )
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
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
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
        lines=[_line_out_from_orm(ln, ln.product) for ln in r2.lines],
    )
