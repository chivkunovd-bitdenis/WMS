from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_effective_seller_id,
    require_packaging_access,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services import marking_code_service as mc_svc

router = APIRouter(
    prefix="/operations/marking-codes",
    tags=["operations"],
)

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class MarkingImportSkipOut(BaseModel):
    reason: str
    count: int


class MarkingImportOut(BaseModel):
    import_id: str
    accepted_count: int
    skipped_count: int
    skip_reasons: list[MarkingImportSkipOut]


class MarkingInventoryRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    requires_honest_sign: bool
    available_count: int
    printed_count: int


class PrintMarkingCodesIn(BaseModel):
    duplicate_copies: int = Field(default=2, ge=1, le=2)
    reprint: bool = False


class PrintMarkingCodesOut(BaseModel):
    packaging_task_line_id: str
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]


def _http_from_mc_error(exc: mc_svc.MarkingCodeServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code in ("seller_not_found", "line_not_found", "product_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    if code == "unsupported_file_type":
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return HTTPException(status_code=status_code, detail=code)


@router.post("/import", response_model=MarkingImportOut)
async def import_marking_codes(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    file: Annotated[UploadFile, File(...)],
    seller_id: Annotated[uuid.UUID | None, Form()] = None,
) -> MarkingImportOut:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        target_seller_id = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        if seller_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="seller_id_required",
            )
        target_seller_id = seller_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    filename = (file.filename or "upload").strip() or "upload"
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="file_too_large",
        )
    try:
        result = await mc_svc.import_marking_codes(
            session,
            user.tenant_id,
            target_seller_id,
            filename=filename,
            content=content,
            uploaded_by_user_id=user.id,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return MarkingImportOut(
        import_id=str(result.import_id),
        accepted_count=result.accepted_count,
        skipped_count=result.skipped_count,
        skip_reasons=[
            MarkingImportSkipOut(reason=r.reason, count=r.count) for r in result.skip_reasons
        ],
    )


@router.get("/inventory", response_model=list[MarkingInventoryRowOut])
async def get_marking_inventory(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[MarkingInventoryRowOut]:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        scope_seller: uuid.UUID | None = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        scope_seller = seller_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    rows = await mc_svc.list_inventory(session, user.tenant_id, seller_id=scope_seller)
    return [
        MarkingInventoryRowOut(
            product_id=str(r.product_id),
            sku_code=r.sku_code,
            product_name=r.product_name,
            requires_honest_sign=r.requires_honest_sign,
            available_count=r.available_count,
            printed_count=r.printed_count,
        )
        for r in rows
    ]


@router.post(
    "/packaging-lines/{line_id}/print",
    response_model=PrintMarkingCodesOut,
)
async def print_marking_codes_for_line(
    line_id: uuid.UUID,
    body: PrintMarkingCodesIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PrintMarkingCodesOut:
    try:
        result = await mc_svc.print_codes_for_packaging_line(
            session,
            user.tenant_id,
            line_id,
            acting_user_id=user.id,
            duplicate_copies=body.duplicate_copies,
            reprint=body.reprint,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return PrintMarkingCodesOut(
        packaging_task_line_id=str(result.packaging_task_line_id),
        quantity=result.quantity,
        duplicate_copies=result.duplicate_copies,
        is_reprint=result.is_reprint,
        codes=result.codes,
    )
