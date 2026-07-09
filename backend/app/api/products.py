from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.box_import_api_shared import read_xlsx_upload
from app.api.deps import (
    get_current_user,
    get_effective_seller_id,
    require_fulfillment_admin,
    seller_line_product_scope,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import (
    CatalogError,
    create_product,
    get_product,
    list_products,
    update_packaging_instructions,
    volume_liters_from_mm,
)
from app.services.product_tz_import_service import (
    ProductTzImportError,
    apply_product_tz_import,
    build_product_tz_preview,
)
from app.services.seller_shop_service import user_can_manage_seller_shops
from app.services.seller_wb_catalog_service import (
    list_ff_catalog_rows,
    list_linked_wb_catalog_rows,
    list_seller_wb_catalog_rows,
)

router = APIRouter(prefix="/products", tags=["products"])

_seller_id_query = Query(default=None)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku_code: str = Field(min_length=1, max_length=128)
    length_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    width_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    height_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    seller_id: uuid.UUID | None = None
    wb_barcode: str | None = Field(default=None, max_length=64)
    wb_size: str | None = Field(default=None, max_length=64)
    wb_vendor_code: str | None = Field(default=None, max_length=255)
    packaging_instructions: str | None = Field(default=None, max_length=8000)
    requires_honest_sign: bool = False


class SellerWbCatalogOut(BaseModel):
    """Product row for seller UI: WB subject, first photo, barcodes (ШК) from card JSON."""

    id: str
    name: str
    sku_code: str
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    wb_subject_name: str | None = None
    wb_primary_image_url: str | None = None
    wb_barcodes: list[str]
    wb_primary_barcode: str | None = None
    wb_size: str | None = None
    wb_color: str | None = None
    wb_brand: str | None = None
    wb_composition: str | None = None
    packaging_instructions: str | None = None
    requires_honest_sign: bool = False
    has_packaging_instructions: bool = False


class FfCatalogOut(BaseModel):
    """FF warehouse catalog row: tenant products enriched from WB cards."""

    id: str
    seller_id: str | None = None
    seller_name: str | None = None
    name: str
    sku_code: str
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    wb_subject_name: str | None = None
    wb_primary_image_url: str | None = None
    wb_barcodes: list[str]
    wb_primary_barcode: str | None = None
    wb_size: str | None = None
    wb_color: str | None = None
    wb_brand: str | None = None
    wb_composition: str | None = None
    packaging_instructions: str | None = None
    requires_honest_sign: bool = False
    has_packaging_instructions: bool = False
    is_manual: bool = False


class ProductOut(BaseModel):
    id: str
    name: str
    sku_code: str
    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    seller_id: str | None
    seller_name: str | None
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    wb_barcode: str | None = None
    wb_size: str | None = None
    packaging_instructions: str | None = None
    requires_honest_sign: bool = False
    is_manual: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def volume_liters(self) -> float | None:
        return volume_liters_from_mm(self.length_mm, self.width_mm, self.height_mm)


class ProductTzRowPreviewOut(BaseModel):
    row: int
    vendor_article: str | None = None
    size: str | None = None
    barcode: str | None = None
    name: str
    sku_code: str
    packaging_instructions: str | None = None
    action: Literal["create", "update", "skip", "error"]
    product_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProductTzRowErrorOut(BaseModel):
    row: int
    barcode: str | None = None
    code: str
    message: str


class ProductTzPreviewSummaryOut(BaseModel):
    total: int
    create_count: int
    update_count: int
    skip_count: int
    error_count: int


class ProductTzImportPreviewOut(BaseModel):
    sheet_name: str
    rows: list[ProductTzRowPreviewOut]
    errors: list[ProductTzRowErrorOut]
    summary: ProductTzPreviewSummaryOut


class ProductTzImportApplyOut(BaseModel):
    created_count: int
    updated_count: int
    skipped_count: int
    product_ids: list[str]
    summary: ProductTzPreviewSummaryOut
    errors: list[ProductTzRowErrorOut] = Field(default_factory=list)


class PackagingInstructionsPatch(BaseModel):
    packaging_instructions: str | None = Field(default=None, max_length=8000)
    requires_honest_sign: bool | None = None


def _product_out(p: object) -> ProductOut:
    from app.models.product import Product

    assert isinstance(p, Product)
    return ProductOut(
        id=str(p.id),
        name=p.name,
        sku_code=p.sku_code,
        length_mm=p.length_mm,
        width_mm=p.width_mm,
        height_mm=p.height_mm,
        seller_id=str(p.seller_id) if p.seller_id else None,
        seller_name=p.seller.name if p.seller is not None else None,
        wb_nm_id=int(p.wb_nm_id) if p.wb_nm_id is not None else None,
        wb_vendor_code=p.wb_vendor_code,
        wb_barcode=p.wb_barcode,
        wb_size=p.wb_size,
        packaging_instructions=p.packaging_instructions,
        requires_honest_sign=bool(p.requires_honest_sign),
        # Manual until WB sync/link sets nmID on same barcode.
        is_manual=p.wb_nm_id is None,
    )


def _http_from_tz_import_error(exc: ProductTzImportError) -> HTTPException:
    code = exc.code
    if code in {
        "unsupported_file_type",
        "empty_file",
        "missing_column",
        "missing_sheet",
        "row_errors",
    }:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": code, "message": exc.message},
        )
    if code == "seller_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": exc.message},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": exc.message},
    )


@router.get("", response_model=list[ProductOut])
async def get_products(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[ProductOut]:
    rows = await list_products(session, user.tenant_id, seller_id=seller_scope)
    return [_product_out(p) for p in rows]


@router.get("/wb-catalog", response_model=list[SellerWbCatalogOut])
async def get_seller_wb_catalog(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[SellerWbCatalogOut]:
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    if effective_seller_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="seller_not_linked",
        )
    catalog_seller_id = effective_seller_id
    if not user_can_manage_seller_shops(user):
        if user.seller_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="seller_not_linked",
            )
        catalog_seller_id = user.seller_id
    rows = await list_seller_wb_catalog_rows(session, user.tenant_id, catalog_seller_id)
    return [
        SellerWbCatalogOut(
            **r.as_dict(),
            has_packaging_instructions=bool((r.packaging_instructions or "").strip()),
        )
        for r in rows
    ]


@router.get("/linked-wb-catalog", response_model=list[FfCatalogOut])
async def get_linked_wb_catalog(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
) -> list[FfCatalogOut]:
    """WB enrichment for all products (barcodes/photo) — including before first stock movement."""
    rows = await list_linked_wb_catalog_rows(session, user.tenant_id, seller_id=seller_id)
    return [
        FfCatalogOut(
            **r.as_dict(),
            has_packaging_instructions=bool((r.packaging_instructions or "").strip()),
        )
        for r in rows
    ]


@router.get("/ff-catalog", response_model=list[FfCatalogOut])
async def get_ff_catalog(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
) -> list[FfCatalogOut]:
    rows = await list_ff_catalog_rows(session, user.tenant_id, seller_id=seller_id)
    return [
        FfCatalogOut(
            **r.as_dict(),
            has_packaging_instructions=bool((r.packaging_instructions or "").strip()),
        )
        for r in rows
    ]


@router.post("", response_model=ProductOut)
async def post_product(
    body: ProductCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProductOut:
    try:
        p = await create_product(
            session,
            user.tenant_id,
            name=body.name,
            sku_code=body.sku_code,
            length_mm=body.length_mm,
            width_mm=body.width_mm,
            height_mm=body.height_mm,
            seller_id=body.seller_id,
            wb_barcode=body.wb_barcode,
            wb_size=body.wb_size,
            wb_vendor_code=body.wb_vendor_code,
            packaging_instructions=body.packaging_instructions,
            requires_honest_sign=body.requires_honest_sign,
        )
    except CatalogError as exc:
        if exc.code == "invalid_dimensions":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_dimensions",
            ) from None
        if exc.code in {"sku_taken", "barcode_taken"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        if exc.code == "seller_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            ) from None
        raise
    await session.refresh(p, attribute_names=["seller"])
    return _product_out(p)


def _tz_preview_out(result: object) -> ProductTzImportPreviewOut:
    from app.services.product_tz_import_service import ProductTzPreviewResult

    assert isinstance(result, ProductTzPreviewResult)
    return ProductTzImportPreviewOut(
        sheet_name=result.sheet_name,
        rows=[
            ProductTzRowPreviewOut(
                row=row.row,
                vendor_article=row.vendor_article,
                size=row.size,
                barcode=row.barcode,
                name=row.name,
                sku_code=row.sku_code,
                packaging_instructions=row.packaging_instructions,
                action=row.action,
                product_id=str(row.product_id) if row.product_id else None,
                error_code=row.error_code,
                error_message=row.error_message,
            )
            for row in result.rows
        ],
        errors=[
            ProductTzRowErrorOut(
                row=err.row,
                barcode=err.barcode,
                code=err.code,
                message=err.message,
            )
            for err in result.errors
        ],
        summary=ProductTzPreviewSummaryOut(
            total=result.summary.total,
            create_count=result.summary.create_count,
            update_count=result.summary.update_count,
            skip_count=result.summary.skip_count,
            error_count=result.summary.error_count,
        ),
    )


@router.post("/import-tz/preview", response_model=ProductTzImportPreviewOut)
async def post_product_tz_import_preview(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> ProductTzImportPreviewOut:
    filename, content = await read_xlsx_upload(file)
    try:
        result = await build_product_tz_preview(
            session,
            user.tenant_id,
            seller_id=seller_id,
            content=content,
            filename=filename,
        )
    except ProductTzImportError as exc:
        raise _http_from_tz_import_error(exc) from None
    return _tz_preview_out(result)


@router.post("/import-tz/apply", response_model=ProductTzImportApplyOut)
async def post_product_tz_import_apply(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    ignore_errors: Annotated[bool, Form()] = False,
) -> ProductTzImportApplyOut:
    filename, content = await read_xlsx_upload(file)
    try:
        result = await apply_product_tz_import(
            session,
            user.tenant_id,
            seller_id=seller_id,
            content=content,
            filename=filename,
            ignore_errors=ignore_errors,
        )
    except ProductTzImportError as exc:
        raise _http_from_tz_import_error(exc) from None
    return ProductTzImportApplyOut(
        created_count=result.created_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
        product_ids=[str(pid) for pid in result.product_ids],
        summary=ProductTzPreviewSummaryOut(
            total=result.summary.total,
            create_count=result.summary.create_count,
            update_count=result.summary.update_count,
            skip_count=result.summary.skip_count,
            error_count=result.summary.error_count,
        ),
        errors=[
            ProductTzRowErrorOut(
                row=err.row,
                barcode=err.barcode,
                code=err.code,
                message=err.message,
            )
            for err in result.errors
        ],
    )


@router.patch("/{product_id}/packaging-instructions", response_model=ProductOut)
async def patch_product_packaging_instructions(
    product_id: uuid.UUID,
    body: PackagingInstructionsPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductOut:
    p = await get_product(session, user.tenant_id, product_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    if user.role == FULFILLMENT_SELLER:
        owner_id = user.seller_id
        if user_can_manage_seller_shops(user) and effective_seller_id is not None:
            owner_id = effective_seller_id
        if owner_id is None or p.seller_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        updated = await update_packaging_instructions(
            session,
            user.tenant_id,
            product_id,
            packaging_instructions=body.packaging_instructions,
            requires_honest_sign=body.requires_honest_sign,
        )
    except CatalogError as exc:
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from None
        raise
    return _product_out(updated)
