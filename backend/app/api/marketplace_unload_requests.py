from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.seller import Seller
from app.models.user import User
from app.services import marketplace_unload_service as svc
from app.services.catalog_service import get_warehouse
from app.services.marketplace_unload_service import MarketplaceUnloadError

router = APIRouter(
    prefix="/operations/marketplace-unload-requests",
    tags=["operations"],
)


class MarketplaceUnloadRequestCreate(BaseModel):
    warehouse_id: uuid.UUID
    seller_id: uuid.UUID | None = None


class MarketplaceUnloadLineCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)


class MarketplaceUnloadLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int


class MarketplaceUnloadRequestSummaryOut(BaseModel):
    id: str
    warehouse_id: str
    warehouse_name: str
    status: str
    line_count: int = Field(default=0, ge=0)
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str


class MarketplaceUnloadRequestDetailOut(BaseModel):
    id: str
    warehouse_id: str
    warehouse_name: str
    status: str
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str
    lines: list[MarketplaceUnloadLineOut]


def _line_out(ln: MarketplaceUnloadLine) -> MarketplaceUnloadLineOut:
    p = ln.product
    return MarketplaceUnloadLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        quantity=ln.quantity,
    )


def _summary_out(
    r: MarketplaceUnloadRequest,
    *,
    warehouse_name: str,
    seller_name: str | None,
) -> MarketplaceUnloadRequestSummaryOut:
    return MarketplaceUnloadRequestSummaryOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        warehouse_name=warehouse_name,
        status=r.status,
        line_count=len(r.lines),
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        created_at=r.created_at.isoformat(),
    )


def _detail_out(
    r: MarketplaceUnloadRequest,
    *,
    warehouse_name: str,
    seller_name: str | None,
) -> MarketplaceUnloadRequestDetailOut:
    return MarketplaceUnloadRequestDetailOut(
        id=str(r.id),
        warehouse_id=str(r.warehouse_id),
        warehouse_name=warehouse_name,
        status=r.status,
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        created_at=r.created_at.isoformat(),
        lines=[_line_out(ln) for ln in r.lines],
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
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.get("", response_model=list[MarketplaceUnloadRequestSummaryOut])
async def list_marketplace_unloads(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MarketplaceUnloadRequestSummaryOut]:
    rows = await svc.list_requests(session, user.tenant_id)
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
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestDetailOut:
    r = await svc.get_request(session, user.tenant_id, request_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _detail_out(
        r,
        warehouse_name=r.warehouse.name,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.post(
    "",
    response_model=MarketplaceUnloadRequestSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_marketplace_unload(
    body: MarketplaceUnloadRequestCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestSummaryOut:
    try:
        r = await svc.create_request(
            session,
            user.tenant_id,
            warehouse_id=body.warehouse_id,
            seller_id=body.seller_id,
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
        raise
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
    "/{request_id}/lines",
    response_model=MarketplaceUnloadLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_marketplace_unload_line(
    request_id: uuid.UUID,
    body: MarketplaceUnloadLineCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadLineOut:
    try:
        line = await svc.add_line(
            session,
            user.tenant_id,
            request_id,
            product_id=body.product_id,
            quantity=body.quantity,
        )
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
    return _line_out(line)


@router.post(
    "/{request_id}/submit",
    response_model=MarketplaceUnloadRequestDetailOut,
)
async def submit_marketplace_unload(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarketplaceUnloadRequestDetailOut:
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
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await svc.delete_line(session, user.tenant_id, request_id, line_id)
    except MarketplaceUnloadError as exc:
        raise _map_mu_err(exc) from None
