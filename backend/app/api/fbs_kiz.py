from __future__ import annotations

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_fbs_operator_access
from app.api.fbs_errors import envelope_from_exc
from app.db.session import get_db
from app.models.user import User
from app.services import fbs_kiz_service as kiz_svc

router = APIRouter(
    prefix="/operations/fbs-orders",
    tags=["operations"],
)


class FbsKizProductOut(BaseModel):
    name: str
    image_url: str | None
    barcode: str | None
    seller_article: str | None


class FbsKizCurrentOut(BaseModel):
    masked: str
    meta_status: str
    from_pool: bool


class FbsKizLookupOut(BaseModel):
    order_id: str
    wb_order_id: int
    product: FbsKizProductOut
    current_kiz: FbsKizCurrentOut | None
    needs_confirmation: bool
    can_bind: bool
    block_reason: str | None


class FbsKizValidateBody(BaseModel):
    order_id: uuid.UUID
    value: str = Field(max_length=512)


class FbsKizValidateOut(BaseModel):
    ok: bool
    hints: list[str]


class FbsKizCommitPairIn(BaseModel):
    order_id: uuid.UUID
    value: str = Field(max_length=512)
    confirmed: bool = False


class FbsKizCommitBody(BaseModel):
    pairs: list[FbsKizCommitPairIn] = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=128)


class FbsKizCommitRowOut(BaseModel):
    order_id: str
    status: str
    code: str
    message: str


def _raise_from_service(exc: kiz_svc.FbsKizError) -> None:
    detail = envelope_from_exc(exc)
    if exc.code == "sticker_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "order_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "kiz_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.code == "missing_marketplace_token":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if exc.code in {"not_a_kiz", "gs_separator_lost"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if exc.code == "order_frozen":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code in {
        "duplicate_kiz",
        "cross_seller_code",
        "code_product_mismatch",
        "needs_confirmation",
        "meta_validation_fail",
        "packaging_line_not_found",
        "sgtin_missing_gs",
    }:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if exc.code.startswith("wb_"):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


def _lookup_out(result: kiz_svc.FbsKizLookup) -> FbsKizLookupOut:
    return FbsKizLookupOut(
        order_id=str(result.order_id),
        wb_order_id=result.wb_order_id,
        product=FbsKizProductOut(
            name=result.product.name,
            image_url=result.product.image_url,
            barcode=result.product.barcode,
            seller_article=result.product.seller_article,
        ),
        current_kiz=(
            FbsKizCurrentOut(
                masked=result.current_kiz.masked,
                meta_status=result.current_kiz.meta_status,
                from_pool=result.current_kiz.from_pool,
            )
            if result.current_kiz is not None
            else None
        ),
        needs_confirmation=result.needs_confirmation,
        can_bind=result.can_bind,
        block_reason=result.block_reason,
    )


def _validate_out(result: kiz_svc.FbsKizValidateResult) -> FbsKizValidateOut:
    return FbsKizValidateOut(ok=result.ok, hints=result.hints)


def _commit_row_out(result: kiz_svc.FbsKizCommitRow) -> FbsKizCommitRowOut:
    return FbsKizCommitRowOut(
        order_id=str(result.order_id),
        status=result.status,
        code=result.code,
        message=result.message,
    )


@router.get("/kiz/lookup", response_model=FbsKizLookupOut)
async def lookup_fbs_order_by_sticker(
    supply_id: uuid.UUID,
    sticker: Annotated[str, Query(min_length=1, max_length=512)],
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsKizLookupOut:
    try:
        result = await kiz_svc.lookup_order_by_sticker(
            session,
            user.tenant_id,
            supply_id,
            sticker,
        )
    except kiz_svc.FbsKizError as exc:
        _raise_from_service(exc)
    return _lookup_out(result)


@router.post("/kiz/validate", response_model=FbsKizValidateOut)
async def validate_fbs_order_kiz(
    body: FbsKizValidateBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FbsKizValidateOut:
    try:
        result = await kiz_svc.validate_kiz_pair(
            session,
            user.tenant_id,
            body.order_id,
            body.value,
        )
    except kiz_svc.FbsKizError as exc:
        _raise_from_service(exc)
    return _validate_out(result)


@router.post("/kiz/commit", response_model=list[FbsKizCommitRowOut])
async def commit_fbs_order_kiz(
    body: FbsKizCommitBody,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[FbsKizCommitRowOut]:
    pairs = [
        kiz_svc.FbsKizCommitPair(
            order_id=item.order_id,
            value=item.value,
            confirmed=item.confirmed,
        )
        for item in body.pairs
    ]
    async with httpx.AsyncClient() as http_client:
        rows = await kiz_svc.commit_kiz_pairs(
            session,
            user.tenant_id,
            user.id,
            pairs,
            body.idempotency_key,
            http_client,
        )
    return [_commit_row_out(row) for row in rows]


@router.delete("/{order_id}/kiz", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fbs_order_kiz(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_fbs_operator_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        async with httpx.AsyncClient() as http_client:
            await kiz_svc.cancel_order_kiz(
                session,
                user.tenant_id,
                user.id,
                order_id,
                http_client,
            )
    except kiz_svc.FbsKizError as exc:
        _raise_from_service(exc)
