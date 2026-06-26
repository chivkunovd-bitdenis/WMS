from __future__ import annotations

import json
import os
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
from app.services.catalog_service import get_product

router = APIRouter(
    prefix="/operations/marking-codes",
    tags=["operations"],
)

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_E2E_SCHEMA = os.environ.get("WMS_AUTO_CREATE_SCHEMA") == "1"


class MarkingImportSkipOut(BaseModel):
    reason: str
    count: int


class PoolImportResultOut(BaseModel):
    pool_id: str
    gtin: str
    title: str
    accepted: int
    duplicates: int
    invalid: int


class MarkingImportOut(BaseModel):
    import_id: str
    document_number: str
    accepted_count: int
    skipped_count: int
    skip_reasons: list[MarkingImportSkipOut]
    pools: list[PoolImportResultOut]


class MarkingInventoryRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    requires_honest_sign: bool
    available_count: int
    printed_count: int


class MarkingInventoryOut(BaseModel):
    rows: list[MarkingInventoryRowOut]
    unlinked_available_count: int


class ProductMarkingCodeOut(BaseModel):
    id: str
    cis_code: str
    status: str
    created_at: str


class PrintMarkingCodesIn(BaseModel):
    duplicate_copies: int = Field(default=2, ge=1, le=2)
    reprint: bool = False


class PrintMarkingCodesOut(BaseModel):
    packaging_task_line_id: str
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]


class PoolProductOut(BaseModel):
    id: str
    sku_code: str
    name: str


class SetPoolProductsIn(BaseModel):
    product_ids: list[uuid.UUID] = Field(default_factory=list)


class PoolProductsOut(BaseModel):
    pool_id: str
    products: list[PoolProductOut]


class E2eCreatePoolIn(BaseModel):
    seller_id: uuid.UUID | None = None
    gtin: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=512)


class E2eCreatePoolOut(BaseModel):
    pool_id: str


def _http_from_mc_error(exc: mc_svc.MarkingCodeServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code in ("seller_not_found", "line_not_found", "product_not_found", "pool_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    if code in ("product_seller_mismatch", "product_id_required"):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code == "unsupported_file_type":
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    return HTTPException(status_code=status_code, detail=code)


def _pool_products_out(result: mc_svc.PoolProductsResult) -> PoolProductsOut:
    return PoolProductsOut(
        pool_id=str(result.pool_id),
        products=[
            PoolProductOut(id=str(p.id), sku_code=p.sku_code, name=p.name)
            for p in result.products
        ],
    )


async def _assert_pool_access(
    user: User,
    pool_seller_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> None:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        if pool_seller_id != effective_seller_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


@router.post("/import", response_model=MarkingImportOut)
async def import_marking_codes(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    files: Annotated[list[UploadFile], File(...)],
    pools_json: Annotated[str, Form(...)],
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

    try:
        raw_specs = json.loads(pools_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_pools_json",
        ) from exc
    if not isinstance(raw_specs, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_pools_json",
        )
    pool_specs: list[mc_svc.PoolImportSpec] = []
    for item in raw_specs:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_pools_json",
            )
        title = str(item.get("title", "")).strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="pool_title_required",
            )
        raw_product_ids = item.get("product_ids") or []
        if not isinstance(raw_product_ids, list):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_pools_json",
            )
        product_ids = [uuid.UUID(str(pid)) for pid in raw_product_ids]
        gtin_raw = item.get("gtin")
        gtin = str(gtin_raw).strip() if gtin_raw else None
        pool_specs.append(
            mc_svc.PoolImportSpec(title=title, product_ids=product_ids, gtin=gtin or None)
        )

    file_payloads: list[tuple[str, bytes]] = []
    for upload in files:
        filename = (upload.filename or "upload").strip() or "upload"
        content = await upload.read(_MAX_UPLOAD_BYTES + 1)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="file_too_large",
            )
        file_payloads.append((filename, content))

    try:
        result = await mc_svc.import_marking_codes(
            session,
            user.tenant_id,
            target_seller_id,
            files=file_payloads,
            pool_specs=pool_specs,
            uploaded_by_user_id=user.id,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return MarkingImportOut(
        import_id=str(result.import_id),
        document_number=result.document_number,
        accepted_count=result.accepted_count,
        skipped_count=result.skipped_count,
        skip_reasons=[
            MarkingImportSkipOut(reason=r.reason, count=r.count) for r in result.skip_reasons
        ],
        pools=[
            PoolImportResultOut(
                pool_id=str(p.pool_id),
                gtin=p.gtin,
                title=p.title,
                accepted=p.accepted,
                duplicates=p.duplicates,
                invalid=p.invalid,
            )
            for p in result.pools
        ],
    )


@router.put("/pools/{pool_id}/products", response_model=PoolProductsOut)
async def set_pool_products(
    pool_id: uuid.UUID,
    body: SetPoolProductsIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PoolProductsOut:
    from app.models.marking_code import MarkingPool

    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await _assert_pool_access(user, pool.seller_id, effective_seller_id)
    try:
        result = await mc_svc.set_pool_products(
            session,
            user.tenant_id,
            pool_id,
            body.product_ids,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return _pool_products_out(result)


if _E2E_SCHEMA:

    @router.post("/_e2e/pools", response_model=E2eCreatePoolOut)
    async def e2e_create_marking_pool(
        body: E2eCreatePoolIn,
        user: Annotated[User, Depends(get_current_user)],
        session: Annotated[AsyncSession, Depends(get_db)],
        effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    ) -> E2eCreatePoolOut:
        if user.role == FULFILLMENT_SELLER:
            if effective_seller_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="seller_not_linked",
                )
            target_seller_id = effective_seller_id
        elif user.role == FULFILLMENT_ADMIN:
            if body.seller_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="seller_id_required",
                )
            target_seller_id = body.seller_id
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        try:
            pool = await mc_svc.create_marking_pool(
                session,
                user.tenant_id,
                target_seller_id,
                gtin=body.gtin,
                title=body.title,
            )
        except mc_svc.MarkingCodeServiceError as exc:
            raise _http_from_mc_error(exc) from exc
        return E2eCreatePoolOut(pool_id=str(pool.id))


@router.get("/inventory", response_model=MarkingInventoryOut)
async def get_marking_inventory(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> MarkingInventoryOut:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        scope_seller: uuid.UUID | None = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        scope_seller = seller_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    result = await mc_svc.list_inventory(session, user.tenant_id, seller_id=scope_seller)
    return MarkingInventoryOut(
        rows=[
            MarkingInventoryRowOut(
                product_id=str(r.product_id),
                sku_code=r.sku_code,
                product_name=r.product_name,
                requires_honest_sign=r.requires_honest_sign,
                available_count=r.available_count,
                printed_count=r.printed_count,
            )
            for r in result.rows
        ],
        unlinked_available_count=result.unlinked_available_count,
    )


@router.get("/products/{product_id}/codes", response_model=list[ProductMarkingCodeOut])
async def list_product_marking_codes(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[ProductMarkingCodeOut]:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        product = await get_product(session, user.tenant_id, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
        if product.seller_id != effective_seller_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    try:
        rows = await mc_svc.list_product_codes(session, user.tenant_id, product_id)
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return [
        ProductMarkingCodeOut(
            id=str(r.id),
            cis_code=r.cis_code,
            status=r.status,
            created_at=r.created_at.isoformat(),
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
