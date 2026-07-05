from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
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
from app.models.print_template import USER_LAST_LAYOUT_NAME
from app.models.product import Product
from app.models.user import User
from app.services import marking_code_service as mc_svc
from app.services import print_template_service as pt_svc
from app.services.catalog_service import get_product
from app.services.marking_label_artifact_service import pdf_bytes_to_png

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


class SharedBasketInventoryOut(BaseModel):
    pool_id: str
    gtin: str
    title: str
    available: int
    products_count: int


class MarkingInventoryRowOut(BaseModel):
    product_id: str
    sku_code: str
    product_name: str
    requires_honest_sign: bool
    available_count: int
    printed_count: int
    personal_available: int
    shared_baskets: list[SharedBasketInventoryOut]


class MarkingInventoryOut(BaseModel):
    rows: list[MarkingInventoryRowOut]
    unlinked_available_count: int


class MarkingOverviewProductOut(BaseModel):
    id: str
    sku_code: str
    name: str
    requires_honest_sign: bool


class PersonalPoolOut(BaseModel):
    pool_id: str
    gtin: str
    title: str
    available: int
    printed: int
    loaded: int


class SharedBasketOverviewOut(BaseModel):
    pool_id: str
    gtin: str
    title: str
    available: int
    products_count: int


class ProductMarkingOverviewOut(BaseModel):
    product: MarkingOverviewProductOut
    personal_pools: list[PersonalPoolOut]
    shared_baskets: list[SharedBasketOverviewOut]


class ProductMarkingCodeOut(BaseModel):
    id: str
    cis_code: str
    status: str
    created_at: str
    has_label_artifact: bool = False


class PrintedCodeOut(BaseModel):
    id: str
    cis_code: str
    has_label_artifact: bool


class PrintMarkingCodesIn(BaseModel):
    layout_json: PrintLayoutOut | None = None
    copies: int | None = Field(default=None, ge=1, le=10)
    allow_partial: bool = False
    reprint: bool = False
    code_ids: list[uuid.UUID] | None = None
    duplicate_copies: int | None = Field(default=None, ge=1, le=2)


class PrintProductMarkingIn(BaseModel):
    quantity: int = Field(ge=1)
    layout_json: PrintLayoutOut | None = None
    allow_partial: bool = False
    duplicate_copies: int | None = Field(default=None, ge=1, le=2)


class PrintMarkingCodesOut(BaseModel):
    packaging_task_line_id: str
    quantity: int
    duplicate_copies: int
    is_reprint: bool
    codes: list[str]
    layout: PrintLayoutOut
    shortage: int | None = None
    printed_codes: list[PrintedCodeOut] = Field(default_factory=list)


class ScanPrintMarkingIn(BaseModel):
    packaging_task_id: uuid.UUID
    product_barcode: str = Field(min_length=1, max_length=128)


class VerifyPairIn(BaseModel):
    cis_a: str = Field(min_length=1, max_length=512)
    cis_b: str = Field(min_length=1, max_length=512)


class VerifyPairOut(BaseModel):
    match: bool
    applied: bool
    code_id: str | None = None


class PendingMarkingLineOut(BaseModel):
    packaging_task_id: str
    packaging_task_line_id: str
    document_number: str | None
    warehouse_id: str
    seller_id: str | None
    product_id: str
    sku_code: str
    product_name: str
    storage_location_code: str
    qty_need: int
    qty_marking_printed: int
    qty_remaining: int
    marking_available_count: int


class PendingMarkingOut(BaseModel):
    rows: list[PendingMarkingLineOut]
    total: int


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
    is_shared: bool
    linked_products_count: int
    available: int
    reserved: int
    printed: int
    defective: int
    forecast_days: float | None
    low_stock_threshold: int | None = None
    forecast_days_threshold: int | None = None
    consumption_7d: int = 0
    loaded: int = 0
    used: int = 0


class PoolThresholdIn(BaseModel):
    low_stock_threshold: int | None = None
    forecast_days_threshold: int | None = None


class PoolImportBatchOut(BaseModel):
    import_id: str
    document_number: str | None
    filename: str
    accepted_count: int
    created_at: str


class PoolDetailOut(PoolListItemOut):
    seller_id: str
    shared_with: list[PoolProductOut]
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
    cis_masked: str | None = None
    pool_title: str | None
    gtin: str | None
    product_name: str | None
    product_sku: str | None
    seller_name: str | None
    document_number: str | None
    actor_email: str | None
    aggregated_count: int | None = None


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
    user_id: str | None
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


def _print_marking_codes_out(result: mc_svc.PrintMarkingCodesResult) -> PrintMarkingCodesOut:
    return PrintMarkingCodesOut(
        packaging_task_line_id=str(result.packaging_task_line_id),
        quantity=result.quantity,
        duplicate_copies=result.duplicate_copies,
        is_reprint=result.is_reprint,
        codes=result.codes,
        layout=_layout_out(result.layout),
        shortage=result.shortage,
        printed_codes=[
            PrintedCodeOut(
                id=str(row.id),
                cis_code=row.cis_code,
                has_label_artifact=row.has_label_artifact,
            )
            for row in result.printed_codes
        ],
    )


def _print_template_out(row: pt_svc.PrintTemplateRow) -> PrintTemplateOut:
    display_name = row.name
    if display_name == USER_LAST_LAYOUT_NAME:
        display_name = "Последняя раскладка"
    return PrintTemplateOut(
        id=str(row.id) if row.id is not None else None,
        seller_id=str(row.seller_id) if row.seller_id is not None else None,
        product_id=str(row.product_id) if row.product_id is not None else None,
        user_id=str(row.user_id) if row.user_id is not None else None,
        name=display_name,
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
        "reprint_request_not_found",
    )
    if code in not_found_codes:
        status_code = status.HTTP_404_NOT_FOUND
    if code in ("product_seller_mismatch", "product_id_required"):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if code == "unsupported_file_type":
        status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    if code in ("task_not_active",):
        status_code = status.HTTP_409_CONFLICT
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


def _shared_basket_inventory_out(row: mc_svc.SharedBasketRow) -> SharedBasketInventoryOut:
    return SharedBasketInventoryOut(
        pool_id=str(row.pool_id),
        gtin=row.gtin,
        title=row.title,
        available=row.available,
        products_count=row.products_count,
    )


async def _assert_product_marking_access(
    user: User,
    product: Product,
    effective_seller_id: uuid.UUID | None,
) -> None:
    if user.role == FULFILLMENT_SELLER:
        if effective_seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        if product.seller_id != effective_seller_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _product_marking_overview_out(
    product: Product,
    pools: list[mc_svc.PoolListRow],
) -> ProductMarkingOverviewOut:
    product_id = product.id
    personal_pools: list[PersonalPoolOut] = []
    shared_baskets: list[SharedBasketOverviewOut] = []
    for pool in pools:
        linked_ids = [p.id for p in pool.products]
        if product_id not in linked_ids:
            continue
        if len(linked_ids) == 1:
            personal_pools.append(
                PersonalPoolOut(
                    pool_id=str(pool.id),
                    gtin=pool.gtin,
                    title=pool.title,
                    available=pool.available,
                    printed=pool.printed,
                    loaded=pool.loaded,
                )
            )
        elif len(linked_ids) >= 2:
            shared_baskets.append(
                SharedBasketOverviewOut(
                    pool_id=str(pool.id),
                    gtin=pool.gtin,
                    title=pool.title,
                    available=pool.available,
                    products_count=len(linked_ids),
                )
            )
    personal_pools.sort(key=lambda p: p.title)
    shared_baskets.sort(key=lambda b: b.title)
    return ProductMarkingOverviewOut(
        product=MarkingOverviewProductOut(
            id=str(product.id),
            sku_code=product.sku_code,
            name=product.name,
            requires_honest_sign=bool(product.requires_honest_sign),
        ),
        personal_pools=personal_pools,
        shared_baskets=shared_baskets,
    )


def _pool_product_out(product: mc_svc.PoolProductRow) -> PoolProductOut:
    return PoolProductOut(id=str(product.id), sku_code=product.sku_code, name=product.name)


def _pool_list_item_out(row: mc_svc.PoolListRow) -> PoolListItemOut:
    return PoolListItemOut(
        id=str(row.id),
        title=row.title,
        gtin=row.gtin,
        products=[_pool_product_out(p) for p in row.products],
        is_shared=row.is_shared,
        linked_products_count=row.linked_products_count,
        available=row.available,
        reserved=row.reserved,
        printed=row.printed,
        defective=row.defective,
        forecast_days=row.forecast_days,
        low_stock_threshold=row.low_stock_threshold,
        forecast_days_threshold=row.forecast_days_threshold,
        consumption_7d=row.consumption_7d,
        loaded=row.loaded,
        used=row.used,
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


@router.put("/pools/{pool_id}/threshold", response_model=PoolListItemOut)
async def set_marking_pool_threshold(
    pool_id: uuid.UUID,
    body: PoolThresholdIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PoolListItemOut:
    from app.models.marking_code import MarkingPool

    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await _assert_pool_access(user, pool.seller_id, effective_seller_id)
    try:
        await mc_svc.set_pool_threshold(
            session,
            user.tenant_id,
            pool_id,
            low_stock_threshold=body.low_stock_threshold,
            forecast_days_threshold=body.forecast_days_threshold,
        )
        rows = await mc_svc.list_pools(
            session, user.tenant_id, seller_id=pool.seller_id
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    row = next((r for r in rows if r.id == pool_id), None)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    return _pool_list_item_out(row)


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
        products=[_pool_product_out(p) for p in detail.products],
        is_shared=detail.is_shared,
        linked_products_count=detail.linked_products_count,
        shared_with=[_pool_product_out(p) for p in detail.products],
        available=detail.available,
        reserved=detail.reserved,
        printed=detail.printed,
        defective=detail.defective,
        forecast_days=detail.forecast_days,
        low_stock_threshold=detail.low_stock_threshold,
        forecast_days_threshold=detail.forecast_days_threshold,
        consumption_7d=detail.consumption_7d,
        loaded=detail.loaded,
        used=detail.used,
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
    code_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[PoolCodeOut]:
    from app.models.marking_code import MarkingPool

    pool = await session.get(MarkingPool, pool_id)
    if pool is None or pool.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pool_not_found")
    await _assert_pool_access(user, pool.seller_id, effective_seller_id)
    try:
        rows = await mc_svc.list_pool_codes(
            session, user.tenant_id, pool_id, status=code_status
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
    cis_mask: Annotated[str | None, Query()] = None,
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
        cis_mask=cis_mask,
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
                aggregated_count=r.aggregated_count,
            )
            for r in page.rows
        ],
    )


@router.get("/ledger/export")
async def export_marking_ledger(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    pool_id: Annotated[uuid.UUID | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    document: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    cis_mask: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
) -> Response:
    scope = _resolve_marking_seller_scope(user, effective_seller_id, seller_id)
    try:
        csv_text = await mc_svc.export_ledger_csv(
            session,
            user.tenant_id,
            seller_id=scope,
            pool_id=pool_id,
            product_id=product_id,
            document_number=document,
            event_type=event_type,
            cis_mask=cis_mask,
            date_from=date_from,
            date_to=date_to,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return Response(
        content=("\ufeff" + csv_text).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ledger-export.csv"'},
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
                personal_available=r.personal_available,
                shared_baskets=[_shared_basket_inventory_out(b) for b in r.shared_baskets],
            )
            for r in result.rows
        ],
        unlinked_available_count=result.unlinked_available_count,
    )


@router.get(
    "/products/{product_id}/marking-overview",
    response_model=ProductMarkingOverviewOut,
)
async def get_product_marking_overview(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductMarkingOverviewOut:
    product = await get_product(session, user.tenant_id, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    await _assert_product_marking_access(user, product, effective_seller_id)
    pools = await mc_svc.list_pools(session, user.tenant_id, seller_id=product.seller_id)
    return _product_marking_overview_out(product, pools)


@router.get("/products/{product_id}/codes", response_model=list[ProductMarkingCodeOut])
async def list_product_marking_codes(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[ProductMarkingCodeOut]:
    product = await get_product(session, user.tenant_id, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    await _assert_product_marking_access(user, product, effective_seller_id)

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
            has_label_artifact=r.has_label_artifact,
        )
        for r in rows
    ]


@router.post(
    "/products/{product_id}/print",
    response_model=PrintMarkingCodesOut,
)
async def print_product_marking_codes(
    product_id: uuid.UUID,
    body: PrintProductMarkingIn,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> PrintMarkingCodesOut:
    product = await get_product(session, user.tenant_id, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    await _assert_product_marking_access(user, product, effective_seller_id)

    layout_payload: dict[str, object] | None = None
    if body.layout_json is not None:
        layout_payload = _layout_in_to_dict(body.layout_json)
    try:
        result = await mc_svc.print_codes_for_product(
            session,
            user.tenant_id,
            product_id,
            acting_user_id=user.id,
            quantity=body.quantity,
            layout=layout_payload,
            allow_partial=body.allow_partial,
            duplicate_copies=body.duplicate_copies,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    if result.quantity > 0 and layout_payload is not None:
        try:
            await pt_svc.save_user_last_print_layout(
                session,
                user.tenant_id,
                user.id,
                layout_payload,
            )
        except pt_svc.PrintTemplateServiceError as exc:
            raise _http_from_pt_error(exc) from exc
    return _print_marking_codes_out(result)


@router.get("/codes/{code_id}/label-artifact")
async def get_marking_code_label_artifact(
    code_id: uuid.UUID,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    format: Annotated[str, Query(pattern="^(pdf|png)$")] = "png",
) -> Response:
    from app.models.marking_code import MarkingCode

    code = await session.get(MarkingCode, code_id)
    if code is None or code.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="code_not_found")
    pdf_bytes = code.label_artifact_pdf
    if not pdf_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="label_artifact_missing")
    if format == "pdf":
        return Response(content=pdf_bytes, media_type="application/pdf")
    try:
        png_bytes = pdf_bytes_to_png(pdf_bytes)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="label_artifact_render_failed",
        ) from exc
    return Response(content=png_bytes, media_type="image/png")


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
        scope_seller_id: uuid.UUID | None = effective_seller_id
    elif user.role == FULFILLMENT_ADMIN:
        scope_seller_id = seller_id
    else:
        scope_seller_id = seller_id
    try:
        row = await pt_svc.resolve_default_print_template(
            session,
            user.tenant_id,
            user_id=user.id,
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
        user_id=user.id,
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
        target_seller_id: uuid.UUID | None = effective_seller_id
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
            user_id=user.id,
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


# BACKEND-01 / T-A6 (ORD-44): scan-print, print-all, verify-pair — UI removed in PACK-01..03.
# No frontend callers after CZ UX fixes; scheduled for removal (MASTER_BACKLOG_RU.md T-A6).


@router.post(
    "/scan-print",
    response_model=PrintMarkingCodesOut,
    deprecated=True,
    summary=(
        "Deprecated (T-A6): scan-to-print removed from packaging UI; "
        "use POST .../packaging-lines/{line_id}/print"
    ),
)
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
    return _print_marking_codes_out(result)


@router.post(
    "/verify-pair",
    response_model=VerifyPairOut,
    deprecated=True,
    summary="Deprecated (T-A6): pair verification panel removed from packaging UI",
)
async def verify_marking_pair(
    body: VerifyPairIn,
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> VerifyPairOut:
    try:
        result = await mc_svc.verify_pair_and_apply(
            session,
            user.tenant_id,
            cis_a=body.cis_a,
            cis_b=body.cis_b,
            acting_user_id=user.id,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return VerifyPairOut(
        match=result.match,
        applied=result.applied,
        code_id=str(result.code_id) if result.code_id else None,
    )


@router.get("/pending-marking", response_model=PendingMarkingOut)
async def list_pending_marking(
    user: Annotated[User, Depends(require_packaging_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    warehouse_id: Annotated[uuid.UUID | None, Query()] = None,
    seller_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PendingMarkingOut:
    rows, total = await mc_svc.list_pending_marking_lines(
        session,
        user.tenant_id,
        warehouse_id=warehouse_id,
        seller_id=seller_id,
        limit=limit,
        offset=offset,
    )
    return PendingMarkingOut(
        total=total,
        rows=[
            PendingMarkingLineOut(
                packaging_task_id=str(row.packaging_task_id),
                packaging_task_line_id=str(row.packaging_task_line_id),
                document_number=row.document_number,
                warehouse_id=str(row.warehouse_id),
                seller_id=str(row.seller_id) if row.seller_id else None,
                product_id=str(row.product_id),
                sku_code=row.sku_code,
                product_name=row.product_name,
                storage_location_code=row.storage_location_code,
                qty_need=row.qty_need,
                qty_marking_printed=row.qty_marking_printed,
                qty_remaining=row.qty_remaining,
                marking_available_count=row.marking_available_count,
            )
            for row in rows
        ],
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
            reprint_code_ids=body.code_ids,
            duplicate_copies=legacy_copies,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    except pt_svc.PrintTemplateServiceError as exc:
        raise _http_from_pt_error(exc) from exc
    if result.quantity > 0 and layout_payload is not None and not body.reprint:
        try:
            await pt_svc.save_user_last_print_layout(
                session,
                user.tenant_id,
                user.id,
                layout_payload,
            )
        except pt_svc.PrintTemplateServiceError as exc:
            raise _http_from_pt_error(exc) from exc
    return _print_marking_codes_out(result)


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
    deprecated=True,
    summary=(
        "Deprecated (T-A6): bulk print-all removed from packaging UI; "
        "use POST .../packaging-lines/{line_id}/print per line"
    ),
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
    packaging_task_id: str
    pool_id: str | None = None


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
                packaging_task_id=str(row.packaging_task_id),
                pool_id=str(row.pool_id) if row.pool_id else None,
            )
            for row in rows
        ]
    )


class ReprintRejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=512)


class ReprintResolutionOut(BaseModel):
    request_id: str
    status: str
    code_id: str
    replacement_code_id: str | None = None
    cis_code: str | None = None


def _resolution_out(result: mc_svc.ReprintResolutionResult) -> ReprintResolutionOut:
    return ReprintResolutionOut(
        request_id=str(result.request_id),
        status=result.status,
        code_id=str(result.code_id),
        replacement_code_id=(
            str(result.replacement_code_id) if result.replacement_code_id else None
        ),
        cis_code=result.cis_code,
    )


@router.post("/reprint-requests/{request_id}/approve-reprint", response_model=ReprintResolutionOut)
async def approve_marking_reprint(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_shift_lead)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReprintResolutionOut:
    try:
        result = await mc_svc.approve_reprint_request(
            session, user.tenant_id, request_id, resolved_by=user.id
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return _resolution_out(result)


@router.post("/reprint-requests/{request_id}/replace", response_model=ReprintResolutionOut)
async def replace_marking_reprint(
    request_id: uuid.UUID,
    user: Annotated[User, Depends(require_shift_lead)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReprintResolutionOut:
    try:
        result = await mc_svc.replace_reprint_request(
            session, user.tenant_id, request_id, resolved_by=user.id
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return _resolution_out(result)


@router.post("/reprint-requests/{request_id}/reject", response_model=ReprintResolutionOut)
async def reject_marking_reprint(
    request_id: uuid.UUID,
    body: ReprintRejectIn,
    user: Annotated[User, Depends(require_shift_lead)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReprintResolutionOut:
    try:
        result = await mc_svc.reject_reprint_request(
            session,
            user.tenant_id,
            request_id,
            resolved_by=user.id,
            reject_reason=body.reason,
        )
    except mc_svc.MarkingCodeServiceError as exc:
        raise _http_from_mc_error(exc) from exc
    return _resolution_out(result)
