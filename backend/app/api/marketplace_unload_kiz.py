"""WMS-686: КИЗ на строках товара отгрузки FBO (подбор и упаковка — одни ручки)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_effective_seller_id, require_mp_shipments_access
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services import marketplace_unload_kiz_service as kiz_svc
from app.services import marketplace_unload_service as mu_svc
from app.services.marketplace_unload_kiz_service import KizItem, MarketplaceUnloadKizError
from app.services.marketplace_unload_service import MarketplaceUnloadError

router = APIRouter(
    prefix="/operations/marketplace-unload-requests/{request_id}",
    tags=["operations"],
)

_NOT_FOUND = {"not_found", "marking_code_not_found"}
_CONFLICT = {"not_editable", "mutation_payload_mismatch", "mutation_result_missing"}


class MarkingCodeScanBody(BaseModel):
    code: str = Field(min_length=1, max_length=512)
    product_id: uuid.UUID | None = None
    mutation_id: uuid.UUID | None = None


class MarkingCodeScanOut(BaseModel):
    marking_code_id: str
    cis_code: str
    product_id: str
    line_id: str
    already_linked: bool
    kiz_count: int
    picked_qty: int


class MarkingCodeItemOut(BaseModel):
    marking_code_id: str
    cis_code: str
    product_id: str | None
    line_id: str
    status: str
    intake_document_number: str | None
    linked_at: datetime | None
    has_label_artifact: bool


class MarkingCodeListOut(BaseModel):
    items: list[MarkingCodeItemOut]


class MarkingCodeRemoveOut(BaseModel):
    removed: bool


class MarkingCodeIssueBody(BaseModel):
    product_id: uuid.UUID
    quantity: int | None = Field(default=None, ge=1, le=1_000_000)
    mutation_id: uuid.UUID


class MarkingCodeIssueOut(BaseModel):
    items: list[MarkingCodeItemOut]
    shortage: int


def _http(exc: MarketplaceUnloadKizError) -> HTTPException:
    if exc.code in _NOT_FOUND:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code in _CONFLICT:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.code)


def _require_ff(user: User) -> None:
    """Запись КИЗ — только фулфилмент; селлер своей отгрузки читает."""
    if user.role == FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _item_out(item: KizItem) -> MarkingCodeItemOut:
    return MarkingCodeItemOut(
        marking_code_id=str(item.marking_code_id),
        cis_code=item.cis_code,
        product_id=str(item.product_id) if item.product_id is not None else None,
        line_id=str(item.line_id),
        status=item.status,
        intake_document_number=item.intake_document_number,
        linked_at=item.linked_at,
        has_label_artifact=item.has_label_artifact,
    )


@router.post("/marking-codes/scan", response_model=MarkingCodeScanOut)
async def scan_marking_code(
    request_id: uuid.UUID,
    body: MarkingCodeScanBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingCodeScanOut:
    _require_ff(user)
    try:
        result = await kiz_svc.link_marking_code(
            session,
            user.tenant_id,
            request_id,
            raw_code=body.code,
            product_id=body.product_id,
            actor_user_id=user.id,
        )
    except MarketplaceUnloadKizError as exc:
        await session.rollback()
        raise _http(exc) from None
    return MarkingCodeScanOut(
        marking_code_id=str(result.marking_code_id),
        cis_code=result.cis_code,
        product_id=str(result.product_id),
        line_id=str(result.line_id),
        already_linked=result.already_linked,
        kiz_count=result.kiz_count,
        picked_qty=result.picked_qty,
    )


@router.get("/marking-codes", response_model=MarkingCodeListOut)
async def list_marking_codes(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> MarkingCodeListOut:
    req = await mu_svc.get_request(session, user.tenant_id, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    try:
        mu_svc.assert_request_visible(user, req, effective_seller_id=effective_seller_id)
    except MarketplaceUnloadError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found") from None
    try:
        items = await kiz_svc.list_marking_codes(session, user.tenant_id, request_id)
    except MarketplaceUnloadKizError as exc:
        raise _http(exc) from None
    return MarkingCodeListOut(items=[_item_out(item) for item in items])


@router.delete("/marking-codes/{marking_code_id}", response_model=MarkingCodeRemoveOut)
async def remove_marking_code(
    request_id: uuid.UUID,
    marking_code_id: uuid.UUID,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingCodeRemoveOut:
    _require_ff(user)
    try:
        removed = await kiz_svc.remove_marking_code(
            session, user.tenant_id, request_id, marking_code_id
        )
    except MarketplaceUnloadKizError as exc:
        await session.rollback()
        raise _http(exc) from None
    return MarkingCodeRemoveOut(removed=removed)


@router.post("/marking-codes/issue", response_model=MarkingCodeIssueOut)
async def issue_marking_codes(
    request_id: uuid.UUID,
    body: MarkingCodeIssueBody,
    user: Annotated[User, Depends(require_mp_shipments_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingCodeIssueOut:
    _require_ff(user)
    try:
        result = await kiz_svc.issue_marking_codes(
            session,
            user.tenant_id,
            request_id,
            product_id=body.product_id,
            quantity=body.quantity,
            mutation_id=body.mutation_id,
            actor_user_id=user.id,
        )
    except MarketplaceUnloadKizError as exc:
        await session.rollback()
        raise _http(exc) from None
    return MarkingCodeIssueOut(
        items=[_item_out(item) for item in result.items],
        shortage=result.shortage,
    )
