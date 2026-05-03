from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_fulfillment_admin, seller_line_product_scope
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import (
    CatalogError,
    create_product,
    list_products,
    volume_liters_from_mm,
)
from app.services.seller_wb_catalog_service import (
    list_ff_catalog_rows,
    list_seller_wb_catalog_rows,
)

router = APIRouter(prefix="/products", tags=["products"])

_seller_id_query = Query(default=None)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku_code: str = Field(min_length=1, max_length=128)
    length_mm: int = Field(ge=1, le=10_000_000)
    width_mm: int = Field(ge=1, le=10_000_000)
    height_mm: int = Field(ge=1, le=10_000_000)
    seller_id: uuid.UUID | None = None


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


class FfCatalogOut(BaseModel):
    """FF warehouse catalog row: only products with FF stock movements."""

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


class ProductOut(BaseModel):
    id: str
    name: str
    sku_code: str
    length_mm: int
    width_mm: int
    height_mm: int
    seller_id: str | None
    seller_name: str | None
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def volume_liters(self) -> float:
        return volume_liters_from_mm(self.length_mm, self.width_mm, self.height_mm)


@router.get("", response_model=list[ProductOut])
async def get_products(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[ProductOut]:
    rows = await list_products(session, user.tenant_id, seller_id=seller_scope)
    return [
        ProductOut(
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
        )
        for p in rows
    ]


@router.get("/wb-catalog", response_model=list[SellerWbCatalogOut])
async def get_seller_wb_catalog(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[SellerWbCatalogOut]:
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    if user.seller_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="seller_not_linked",
        )
    rows = await list_seller_wb_catalog_rows(session, user.tenant_id, user.seller_id)
    return [SellerWbCatalogOut(**r.as_dict()) for r in rows]


@router.get("/ff-catalog", response_model=list[FfCatalogOut])
async def get_ff_catalog(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
) -> list[FfCatalogOut]:
    rows = await list_ff_catalog_rows(session, user.tenant_id, seller_id=seller_id)
    return [FfCatalogOut(**r.as_dict()) for r in rows]


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
        )
    except CatalogError as exc:
        if exc.code == "invalid_dimensions":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_dimensions",
            ) from None
        if exc.code == "sku_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="sku_taken",
            ) from None
        if exc.code == "seller_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="seller_not_found",
            ) from None
        raise
    await session.refresh(p, attribute_names=["seller"])
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
    )
