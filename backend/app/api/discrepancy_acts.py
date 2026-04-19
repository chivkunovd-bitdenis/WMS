from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fulfillment_admin
from app.db.session import get_db
from app.models.discrepancy_act import DiscrepancyAct, DiscrepancyActLine
from app.models.seller import Seller
from app.models.user import User
from app.services import discrepancy_act_service as svc
from app.services.discrepancy_act_service import DiscrepancyActError

router = APIRouter(
    prefix="/operations/discrepancy-acts",
    tags=["operations"],
)


class DiscrepancyActCreate(BaseModel):
    inbound_intake_request_id: uuid.UUID | None = None
    seller_id: uuid.UUID | None = None


class DiscrepancyActLineCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1, le=1_000_000_000)
    inbound_intake_line_id: uuid.UUID | None = None


class DiscrepancyActLineOut(BaseModel):
    id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    inbound_intake_line_id: str | None = None


class DiscrepancyActSummaryOut(BaseModel):
    id: str
    status: str
    line_count: int = Field(default=0, ge=0)
    inbound_intake_request_id: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str


class DiscrepancyActDetailOut(BaseModel):
    id: str
    status: str
    inbound_intake_request_id: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    created_at: str
    lines: list[DiscrepancyActLineOut]


def _line_out(ln: DiscrepancyActLine) -> DiscrepancyActLineOut:
    p = ln.product
    return DiscrepancyActLineOut(
        id=str(ln.id),
        product_id=str(ln.product_id),
        sku_code=p.sku_code,
        product_name=p.name,
        quantity=ln.quantity,
        inbound_intake_line_id=str(ln.inbound_intake_line_id)
        if ln.inbound_intake_line_id is not None
        else None,
    )


def _summary_out(r: DiscrepancyAct, *, seller_name: str | None) -> DiscrepancyActSummaryOut:
    return DiscrepancyActSummaryOut(
        id=str(r.id),
        status=r.status,
        line_count=len(r.lines),
        inbound_intake_request_id=str(r.inbound_intake_request_id)
        if r.inbound_intake_request_id is not None
        else None,
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        created_at=r.created_at.isoformat(),
    )


def _detail_out(r: DiscrepancyAct, *, seller_name: str | None) -> DiscrepancyActDetailOut:
    return DiscrepancyActDetailOut(
        id=str(r.id),
        status=r.status,
        inbound_intake_request_id=str(r.inbound_intake_request_id)
        if r.inbound_intake_request_id is not None
        else None,
        seller_id=str(r.seller_id) if r.seller_id is not None else None,
        seller_name=seller_name,
        created_at=r.created_at.isoformat(),
        lines=[_line_out(ln) for ln in r.lines],
    )


def _map_da_err(exc: DiscrepancyActError) -> HTTPException:
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
    if exc.code in ("inbound_link_required", "product_mismatch"):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        )
    if exc.code == "inbound_line_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="inbound_line_not_found",
        )
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=exc.code)


@router.get("", response_model=list[DiscrepancyActSummaryOut])
async def list_discrepancy_acts(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DiscrepancyActSummaryOut]:
    rows = await svc.list_acts(session, user.tenant_id)
    return [
        _summary_out(
            r,
            seller_name=r.seller.name if r.seller is not None else None,
        )
        for r in rows
    ]


@router.get("/{act_id}", response_model=DiscrepancyActDetailOut)
async def get_discrepancy_act(
    act_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DiscrepancyActDetailOut:
    r = await svc.get_act(session, user.tenant_id, act_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _detail_out(
        r,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.post(
    "",
    response_model=DiscrepancyActSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_discrepancy_act(
    body: DiscrepancyActCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DiscrepancyActSummaryOut:
    try:
        r = await svc.create_act(
            session,
            user.tenant_id,
            inbound_intake_request_id=body.inbound_intake_request_id,
            seller_id=body.seller_id,
        )
    except DiscrepancyActError as exc:
        if exc.code == "inbound_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="inbound_not_found",
            ) from None
        if exc.code == "seller_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            ) from None
        raise
    r2 = await svc.get_act(session, user.tenant_id, r.id)
    if r2 is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="act_missing_after_create",
        )
    seller_name: str | None = None
    if r2.seller_id is not None:
        sl = await session.get(Seller, r2.seller_id)
        seller_name = sl.name if sl is not None else None
    return _summary_out(r2, seller_name=seller_name)


@router.post(
    "/{act_id}/lines",
    response_model=DiscrepancyActLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_discrepancy_act_line(
    act_id: uuid.UUID,
    body: DiscrepancyActLineCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DiscrepancyActLineOut:
    try:
        line = await svc.add_line(
            session,
            user.tenant_id,
            act_id,
            product_id=body.product_id,
            quantity=body.quantity,
            inbound_intake_line_id=body.inbound_intake_line_id,
        )
    except DiscrepancyActError as exc:
        raise _map_da_err(exc) from None
    return _line_out(line)


@router.post(
    "/{act_id}/submit",
    response_model=DiscrepancyActDetailOut,
)
async def submit_discrepancy_act(
    act_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DiscrepancyActDetailOut:
    try:
        await svc.submit_act(session, user.tenant_id, act_id)
    except DiscrepancyActError as exc:
        raise _map_da_err(exc) from None
    r = await svc.get_act(session, user.tenant_id, act_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return _detail_out(
        r,
        seller_name=r.seller.name if r.seller is not None else None,
    )


@router.delete(
    "/{act_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_discrepancy_act_line(
    act_id: uuid.UUID,
    line_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await svc.delete_line(session, user.tenant_id, act_id, line_id)
    except DiscrepancyActError as exc:
        raise _map_da_err(exc) from None
