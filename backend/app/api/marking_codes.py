from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_effective_seller_id,
    require_packaging_access,
    require_shift_lead,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services import marking_code_service as mc_svc
from app.services import print_template_service as pt_svc
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


class ImportPreviewGroupOut(BaseModel):
    gtin: str
    codes_count: int
    suggested_title: str


class MarkingImportPreviewOut(BaseModel):
    groups: list[ImportPreviewGroupOut]
    total_codes: int
    invalid_count: int
    duplicates_in_file: int


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
    layout_json: PrintLayoutOut | None = None
    copies: int | None = Field(default=None, ge=1, le=10)
    allow_partial: bool = False
    reprint: bool = False
    duplicate_copies: int | None = Field(default=None, ge=1, le=2)


class PrintMarkingCodesOut(BaseModel):
    packaging_task_line_id: str
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]
    layout: PrintLayoutOut
    shortage: int | None = None


class ScanPrintMarkingIn(BaseModel):
    packaging_task_id: uuid.UUID
    product_barcode: str = Field(min_length=1, max_length=128)


class PrintAllMarkingIn(BaseModel):
    layout_json: PrintLayoutOut | None = None
    allow_partial: bool = False
    dry_run: bool = False


class PrintAllLineOut(BaseModel):
    packaging_task_line_id: str
    product_id: str
    sku_code: str
    product_name: str
    quantity: int
    shortage: int
    codes: list[str]


class PrintAllMarkingOut(BaseModel):
    packaging_task_id: str
    quantity: int
    duplicate_copies: int
    codes: list[str]
    layout: PrintLayoutOut
    lines: list[PrintAllLineOut]
    dry_run: bool


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


class PoolListItemOut(BaseModel):
    id: str
    title: str
    gtin: str
    products: list[PoolProductOut]
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None = None


class PoolImportBatchOut(BaseModel):
    import_id: str
    document_number: str | None
    filename: str
    accepted_count: int
    created_at: str


class PoolDetailOut(PoolListItemOut):
    seller_id: str
    import_batches: list[PoolImportBatchOut]


class PoolCodeOut(BaseModel):
    id: str
    cis_masked: str
    status: str
    created_at: str
    printed_by: str | None
    document_number: str | None


class LedgerEventOut(BaseModel):
    id: str
    created_at: str
    event_type: str
    cis_masked: str
    pool_title: str | None
    gtin: str | None
    product_name: str | None
    product_sku: str | None
    seller_name: str | None
    document_number: str | None
    actor_email: str | None


class LedgerPageOut(BaseModel):
    rows: list[LedgerEventOut]
    total: int


class CodeHistoryEventOut(BaseModel):
    id: str
    created_at: str
    event_type: str
    document_number: str | None
    actor_email: str | None
    copies: int
    reason: str | None


class PrintLayoutUnitOut(BaseModel):
    block: str
    copies: int


class PrintLayoutOut(BaseModel):
    units: list[PrintLayoutUnitOut]


class PrintTemplateOut(BaseModel):
    id: str | None
    seller_id: str | None
    product_id: str | None
    name: str
    layout: PrintLayoutOut
    is_default: bool
    is_system: bool


class CreatePrintTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    layout: PrintLayoutOut
    seller_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    is_default: bool = False


class UpdatePrintTemplateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    layout: PrintLayoutOut | None = None
    is_default: bool | None = None


def _http_from_pt_error(exc: pt_svc.PrintTemplateServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code in ("template_not_found", "product_not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    return HTTPException(status_code=status_code, detail=code)


def _layout_out(layout: pt_svc.PrintLayout) -> PrintLayoutOut:
    return PrintLayoutOut(
        units=[PrintLayoutUnitOut(block=u.block, copies=u.copies) for u in layout.units],
    )


def _layout_in_to_dict(layout: PrintLayoutOut) -> dict[str, object]:
    return {"units": [{"block": u.block, "copies": u.copies} for u in layout.units]}


def _print_template_out(row: pt_svc.PrintTemplateRow) -> PrintTemplateOut:
    return PrintTemplateOut(
        id=str(row.id) if row.id is not None else None,
        seller_id=str(row.seller_id) if row.seller_id is not None else None,
        product_id=str(row.product_id) if row.product_id is not None else None,
        name=row.name,
        layout=_layout_out(row.layout),
        is_default=row.is_default,
        is_system=row.is_system,
    )


async def _assert_template_seller_access(
    user: User,
    template_seller_id: uuid.UUID | None,
    effective_seller_id: uuid.UUID | None,
) -> None:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        if template_seller_id is not None and template_seller_id != effective_seller_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _http_from_mc_error(exc: mc_svc.MarkingCodeServiceError) -> HTTPException:
    code = exc.code
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    not_found_codes = (
        "seller_not_found",
        "line_not_found",
        "product_not_found",
        "pool_not_found",
        "code_not_found",
        "task_not_found",
    )
    if code in not_found_codes:
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


def _resolve_marking_seller_scope(
    user: User,
    effective_seller_id: uuid.UUID | None,
    seller_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        return effective_seller_id
    if user.role == FULFILLMENT_ADMIN:
        return seller_id
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _pool_list_item_out(row: mc_svc.PoolListRow) -> PoolListItemOut:
    return PoolListItemOut(
        id=str(row.id),
        title=row.title,
        gtin=row.gtin,
        products=[
            PoolProductOut(id=str(p.id), sku_code=p.sku_code, name=p.name) for p in row.products
        ],
        available=row.available,
        reserved=row.reserved,
        printed=row.printed,
        defective=row.defective,
        forecast_days=row.forecast_days,
        low_stock_threshold=row.low_stock_threshold,
    )


@router.post("/import/preview", response_model=MarkingImportPreviewOut)
async def preview_marking_import(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    files: Annotated[list[UploadFile], File(...)],
    seller_id: Annotated[uuid.UUID | None, Form()] = None,
) -> MarkingImportPreviewOut:
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
        result = await mc_svc.preview_marking_import(
            session,
            user.tenant_id,
            target_seller_id,
            files=file_payloads,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return MarkingImportPreviewOut(
        groups=[
            ImportPreviewGroupOut(
                gtin=g.gtin,
                codes_count=g.codes_count,
                suggested_title=g.suggested_title,
            )
            for g in result.groups
        ],
        total_codes=result.total_codes,
        invalid_count=result.invalid_count,
        duplicates_in_file=result.duplicates_in_file,
    )


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


@router.get("/pools", response_model=list[PoolListItemOut])
async def list_marking_pools(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PoolListItemOut]:
    scope = _resolve_marking_seller_scope(user, effective_seller_id, seller_id)
    rows = await mc_svc.list_pools(session, user.tenant_id, seller_id=scope)
    return [_pool_list_item_out(r) for r in rows]


@router.get("/pools/{pool_id}", response_model=PoolDetailOut)
async def get_marking_pool(
    pool_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PoolDetailOut:
    from app.models.marking_code import MarkingPool

    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await _assert_pool_access(user, pool.seller_id, effective_seller_id)
    try:
        detail = await mc_svc.get_pool_detail(session, user.tenant_id, pool_id)
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return PoolDetailOut(
        id=str(detail.id),
        seller_id=str(detail.seller_id),
        title=detail.title,
        gtin=detail.gtin,
        products=[
            PoolProductOut(id=str(p.id), sku_code=p.sku_code, name=p.name) for p in detail.products
        ],
        available=detail.available,
        reserved=detail.reserved,
        printed=detail.printed,
        defective=detail.defective,
        forecast_days=detail.forecast_days,
        low_stock_threshold=detail.low_stock_threshold,
        import_batches=[
            PoolImportBatchOut(
                import_id=str(b.import_id),
                document_number=b.document_number,
                filename=b.filename,
                accepted_count=b.accepted_count,
                created_at=b.created_at.isoformat(),
            )
            for b in detail.import_batches
        ],
    )


@router.get("/pools/{pool_id}/codes", response_model=list[PoolCodeOut])
async def list_marking_pool_codes(
    pool_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    status: Annotated[str | None, Query()] = None,
) -> list[PoolCodeOut]:
    from app.models.marking_code import MarkingPool

    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await _assert_pool_access(user, pool.seller_id, effective_seller_id)
    try:
        rows = await mc_svc.list_pool_codes(
            session, user.tenant_id, pool_id, status=status
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return [
        PoolCodeOut(
            id=str(r.id),
            cis_masked=r.cis_masked,
            status=r.status,
            created_at=r.created_at.isoformat(),
            printed_by=r.printed_by,
            document_number=r.document_number,
        )
        for r in rows
    ]


@router.get("/ledger", response_model=LedgerPageOut)
async def list_marking_ledger(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    pool_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    document: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LedgerPageOut:
    scope = _resolve_marking_seller_scope(user, effective_seller_id, seller_id)
    page = await mc_svc.list_ledger(
        session,
        user.tenant_id,
        seller_id=scope,
        pool_id=pool_id,
        product_id=product_id,
        document_number=document,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return LedgerPageOut(
        total=page.total,
        rows=[
            LedgerEventOut(
                id=str(r.id),
                created_at=r.created_at.isoformat(),
                event_type=r.event_type,
                cis_masked=r.cis_masked,
                pool_title=r.pool_title,
                gtin=r.gtin,
                product_name=r.product_name,
                product_sku=r.product_sku,
                seller_name=r.seller_name,
                document_number=r.document_number,
                actor_email=r.actor_email,
            )
            for r in page.rows
        ],
    )


@router.get("/codes/{code_id}/history", response_model=list[CodeHistoryEventOut])
async def get_marking_code_history(
    code_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[CodeHistoryEventOut]:
    from app.models.marking_code import MarkingCode

    code = await session.get(MarkingCode, code_id)
    if code is None or code.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="code_not_found")
    await _assert_pool_access(user, code.seller_id, effective_seller_id)
    try:
        rows = await mc_svc.get_code_history(session, user.tenant_id, code_id)
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return [
        CodeHistoryEventOut(
            id=str(r.id),
            created_at=r.created_at.isoformat(),
            event_type=r.event_type,
            document_number=r.document_number,
            actor_email=r.actor_email,
            copies=r.copies,
            reason=r.reason,
        )
        for r in rows
    ]


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


@router.get("/print-templates/resolve", response_model=PrintTemplateOut)
async def resolve_print_template(
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
) -> PrintTemplateOut:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        scope_seller_id = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        scope_seller_id = seller_id
    else:
        scope_seller_id = seller_id
    try:
        row = await pt_svc.resolve_default_print_template(
            session,
            user.tenant_id,
            product_id=product_id,
            seller_id=scope_seller_id,
        )
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    return _print_template_out(row)


@router.get("/print-templates", response_model=list[PrintTemplateOut])
async def list_print_templates(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PrintTemplateOut]:
    scope = _resolve_marking_seller_scope(user, effective_seller_id, seller_id)
    rows = await pt_svc.list_print_templates(
        session,
        user.tenant_id,
        seller_id=scope,
        product_id=product_id,
    )
    return [_print_template_out(r) for r in rows]


@router.post(
    "/print-templates",
    response_model=PrintTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_print_template(
    body: CreatePrintTemplateIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PrintTemplateOut:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        target_seller_id = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        target_seller_id = body.seller_id
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        row = await pt_svc.create_print_template(
            session,
            user.tenant_id,
            name=body.name,
            layout=_layout_in_to_dict(body.layout),
            seller_id=target_seller_id,
            product_id=body.product_id,
            is_default=body.is_default,
        )
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    return _print_template_out(row)


@router.put("/print-templates/{template_id}", response_model=PrintTemplateOut)
async def update_print_template(
    template_id: uuid.UUID,
    body: UpdatePrintTemplateIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PrintTemplateOut:
    from app.models.print_template import PrintTemplate

    model = await session.get(PrintTemplate, template_id)
    if model is None or model.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template_not_found")
    await _assert_template_seller_access(user, model.seller_id, effective_seller_id)
    try:
        row = await pt_svc.update_print_template(
            session,
            user.tenant_id,
            template_id,
            name=body.name,
            layout=_layout_in_to_dict(body.layout) if body.layout is not None else None,
            is_default=body.is_default,
        )
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    return _print_template_out(row)


@router.delete("/print-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_print_template(
    template_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> None:
    from app.models.print_template import PrintTemplate

    model = await session.get(PrintTemplate, template_id)
    if model is None or model.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template_not_found")
    await _assert_template_seller_access(user, model.seller_id, effective_seller_id)
    try:
        await pt_svc.delete_print_template(session, user.tenant_id, template_id)
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc


@router.post("/scan-print", response_model=PrintMarkingCodesOut)
async def scan_print_marking_codes(
    body: ScanPrintMarkingIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PrintMarkingCodesOut:
    try:
        result = await mc_svc.scan_print_for_packaging_task(
            session,
            user.tenant_id,
            body.packaging_task_id,
            product_barcode=body.product_barcode,
            acting_user_id=user.id,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return PrintMarkingCodesOut(
        packaging_task_line_id=str(result.packaging_task_line_id),
        quantity=result.quantity,
        duplicate_copies=result.duplicate_copies,
        is_reprint=result.is_reprint,
        codes=result.codes,
        layout=_layout_out(result.layout),
        shortage=result.shortage,
    )


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
    layout_payload: dict[str, object] | None = None
    if body.layout_json is not None:
        layout_payload = _layout_in_to_dict(body.layout_json)
    legacy_copies = body.duplicate_copies
    if body.copies is not None:
        legacy_copies = body.copies
    try:
        result = await mc_svc.print_codes_for_packaging_line(
            session,
            user.tenant_id,
            line_id,
            acting_user_id=user.id,
            layout=layout_payload,
            allow_partial=body.allow_partial,
            reprint=body.reprint,
            duplicate_copies=legacy_copies,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    return PrintMarkingCodesOut(
        packaging_task_line_id=str(result.packaging_task_line_id),
        quantity=result.quantity,
        duplicate_copies=result.duplicate_copies,
        is_reprint=result.is_reprint,
        codes=result.codes,
        layout=_layout_out(result.layout),
        shortage=result.shortage,
    )


def _print_all_out(result: mc_svc.PrintAllMarkingCodesResult) -> PrintAllMarkingOut:
    return PrintAllMarkingOut(
        packaging_task_id=str(result.packaging_task_id),
        quantity=result.quantity,
        duplicate_copies=result.duplicate_copies,
        codes=result.codes,
        layout=_layout_out(result.layout),
        lines=[
            PrintAllLineOut(
                packaging_task_line_id=str(line.packaging_task_line_id),
                product_id=str(line.product_id),
                sku_code=line.sku_code,
                product_name=line.product_name,
                quantity=line.quantity,
                shortage=line.shortage,
                codes=line.codes,
            )
            for line in result.lines
        ],
        dry_run=result.dry_run,
    )


@router.post(
    "/packaging-tasks/{task_id}/print-all",
    response_model=PrintAllMarkingOut,
)
async def print_all_marking_codes_for_task(
    task_id: uuid.UUID,
    body: PrintAllMarkingIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PrintAllMarkingOut:
    layout_payload: dict[str, object] | None = None
    if body.layout_json is not None:
        layout_payload = _layout_in_to_dict(body.layout_json)
    try:
        result = await mc_svc.print_all_for_packaging_task(
            session,
            user.tenant_id,
            task_id,
            acting_user_id=user.id,
            layout=layout_payload,
            allow_partial=body.allow_partial,
            dry_run=body.dry_run,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    return _print_all_out(result)


class MarkingReprintRequestOut(BaseModel):
    id: str
    code_id: str
    status: str
    reason: str | None = None
    created_at: datetime
    requested_by_email: str
    product_name: str
    product_sku: str
    cis_masked: str
    document_number: str | None = None


class MarkingReprintRequestsOut(BaseModel):
    requests: list[MarkingReprintRequestOut]


class PrintedMarkingCodeOut(BaseModel):
    id: str
    cis_masked: str
    status: str


class PrintedMarkingCodesOut(BaseModel):
    codes: list[PrintedMarkingCodeOut]


class MarkingDefectIn(BaseModel):
    packaging_task_line_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=512)


class MarkingDefectOut(BaseModel):
    request_id: str
    code_id: str
    status: str


@router.get(
    "/packaging-task-lines/{line_id}/printed-codes",
    response_model=PrintedMarkingCodesOut,
)
async def list_printed_codes_for_line(
    line_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PrintedMarkingCodesOut:
    try:
        rows = await mc_svc.list_printed_codes_for_packaging_line(
            session, user.tenant_id, line_id
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return PrintedMarkingCodesOut(
        codes=[
            PrintedMarkingCodeOut(id=str(row.id), cis_masked=row.cis_masked, status=row.status)
            for row in rows
        ]
    )


@router.post("/codes/{code_id}/defect", response_model=MarkingDefectOut)
async def report_marking_code_defect(
    code_id: uuid.UUID,
    body: MarkingDefectIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingDefectOut:
    try:
        req = await mc_svc.create_defect_reprint_request(
            session,
            user.tenant_id,
            code_id,
            packaging_task_line_id=body.packaging_task_line_id,
            requested_by=user.id,
            reason=body.reason,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return MarkingDefectOut(
        request_id=str(req.id),
        code_id=str(req.code_id),
        status=req.status,
    )


@router.get("/reprint-requests", response_model=MarkingReprintRequestsOut)
async def list_marking_reprint_requests(
    user: Annotated[User, Depends(require_shift_lead)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MarkingReprintRequestsOut:
    rows = await mc_svc.list_pending_reprint_requests(session, user.tenant_id)
    return MarkingReprintRequestsOut(
        requests=[
            MarkingReprintRequestOut(
                id=str(row.id),
                code_id=str(row.code_id),
                status=row.status,
                reason=row.reason,
                created_at=row.created_at,
                requested_by_email=row.requested_by_email,
                product_name=row.product_name,
                product_sku=row.product_sku,
                cis_masked=row.cis_masked,
                document_number=row.document_number,
            )
            for row in rows
        ]
    )
