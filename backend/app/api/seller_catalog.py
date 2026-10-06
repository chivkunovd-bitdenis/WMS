"""WMS-548 D2: seller-facing catalog page and "add to fulfillment" action.

Separate router (prefix ``/seller-catalog``) rather than new routes on
``app/api/products.py`` — that file is being edited by a sibling task in the
same package (WMS-490/491) and its own ``/products/{product_id}/...`` routes
are out of scope here; see docs/requirements/WMS-548.md section 7 for the
full contract shared with the frontend pieces (D4, D5).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import assert_seller_permission, get_current_user, get_effective_seller_id
from app.api.products import MarketplaceProductBindingOut
from app.core.roles import FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.seller_fulfillment_catalog_service import (
    ADD_TO_FULFILLMENT_MAX_IDS,
    add_cards_to_fulfillment,
    list_seller_catalog_keys,
    list_seller_catalog_page,
)
from app.services.seller_shop_service import user_can_manage_seller_shops
from app.services.seller_staff_permissions_service import PERM_PRODUCTS

router = APIRouter(prefix="/seller-catalog", tags=["seller-catalog"])


async def _seller_catalog_scope(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> uuid.UUID:
    """Same access rule as GET /products/wb-catalog: seller role, «Товары», own shop."""
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if effective_seller_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
    if not user_can_manage_seller_shops(user):
        if user.seller_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
        return user.seller_id
    return effective_seller_id


class SellerCatalogItemOut(BaseModel):
    key: str
    on_fulfillment: bool
    marketplace: str

    # Товар на ФФ: поля сегодняшней строки /products/wb-catalog.
    id: str | None = None
    name: str | None = None
    sku_code: str | None = None
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    ozon_sku: str | None = None
    ozon_offer_id: str | None = None
    wb_connected: bool = False
    ozon_connected: bool = False
    wb_subject_name: str | None = None
    wb_primary_image_url: str | None = None
    marketplace_bindings: list[MarketplaceProductBindingOut] = Field(default_factory=list)
    wb_barcodes: list[str] = Field(default_factory=list)
    wb_primary_barcode: str | None = None
    wb_size: str | None = None
    wb_color: str | None = None
    wb_brand: str | None = None
    wb_composition: str | None = None
    packaging_instructions: str | None = None
    country_of_origin_iso_code: str | None = None
    requires_honest_sign: bool = False
    fbs_stock_sync_enabled: bool = False
    fbs_stock_limit: int | None = None
    fbs_published_amount: int | None = None
    fbs_sync_status: str | None = None
    has_packaging_instructions: bool = False

    # Карточка не на ФФ.
    nm_id: int | None = None
    ozon_product_id: str | None = None
    vendor_code: str | None = None
    photo_url: str | None = None
    barcodes: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    category: str | None = None


class SellerCatalogPageOut(BaseModel):
    items: list[SellerCatalogItemOut]
    total: int
    scope_total: int
    limit: int
    offset: int
    categories: list[str]


class AddToFulfillmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wb_nm_ids: list[int] = Field(default_factory=list)
    ozon_product_ids: list[str] = Field(default_factory=list)


class AddToFulfillmentEntryOut(BaseModel):
    marketplace: str
    id: str
    vendor_code: str | None = None
    products_added: int = 0


class AddToFulfillmentSkippedOut(BaseModel):
    marketplace: str
    id: str
    vendor_code: str | None = None
    reason: str


class AddToFulfillmentOut(BaseModel):
    added: list[AddToFulfillmentEntryOut]
    skipped: list[AddToFulfillmentSkippedOut]


@router.get("/page", response_model=SellerCatalogPageOut)
async def get_seller_catalog_page(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID, Depends(_seller_catalog_scope)],
    search: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[str | None, Query(max_length=255)] = None,
    article: Annotated[str | None, Query(max_length=255)] = None,
    size: Annotated[str | None, Query(max_length=255)] = None,
    stock_only: bool = False,
    group_by: Annotated[Literal["category_article_size"] | None, Query()] = None,
    on_fulfillment: Annotated[Literal["all", "yes", "no"], Query()] = "all",
    marketplace: Annotated[Literal["wildberries", "ozon"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SellerCatalogPageOut:
    items, total, scope_total, categories = await list_seller_catalog_page(
        session,
        user.tenant_id,
        seller_id,
        search=search,
        category=category,
        article=article,
        size=size,
        stock_only=stock_only,
        group_by=group_by,
        on_fulfillment=on_fulfillment,
        marketplace=marketplace,
        limit=limit,
        offset=offset,
    )
    return SellerCatalogPageOut(
        items=[SellerCatalogItemOut(**item) for item in items],
        total=total,
        scope_total=scope_total,
        limit=limit,
        offset=offset,
        categories=categories,
    )


@router.get("/keys", response_model=list[str])
async def get_seller_catalog_keys(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID, Depends(_seller_catalog_scope)],
    search: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[str | None, Query(max_length=255)] = None,
    article: Annotated[str | None, Query(max_length=255)] = None,
    size: Annotated[str | None, Query(max_length=255)] = None,
    stock_only: bool = False,
    group_by: Annotated[Literal["category_article_size"] | None, Query()] = None,
    on_fulfillment: Annotated[Literal["all", "yes", "no"], Query()] = "all",
    marketplace: Annotated[Literal["wildberries", "ozon"] | None, Query()] = None,
) -> list[str]:
    return await list_seller_catalog_keys(
        session,
        user.tenant_id,
        seller_id,
        search=search,
        category=category,
        article=article,
        size=size,
        stock_only=stock_only,
        group_by=group_by,
        on_fulfillment=on_fulfillment,
        marketplace=marketplace,
    )


@router.post("/add-to-fulfillment", response_model=AddToFulfillmentOut)
async def post_add_to_fulfillment(
    body: AddToFulfillmentBody,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    seller_id: Annotated[uuid.UUID, Depends(_seller_catalog_scope)],
) -> AddToFulfillmentOut:
    total_ids = len(set(body.wb_nm_ids)) + len(set(body.ozon_product_ids))
    if total_ids > ADD_TO_FULFILLMENT_MAX_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="too_many_ids"
        )
    added, skipped = await add_cards_to_fulfillment(
        session,
        user.tenant_id,
        seller_id,
        wb_nm_ids=body.wb_nm_ids,
        ozon_product_ids=body.ozon_product_ids,
    )
    return AddToFulfillmentOut(
        added=[AddToFulfillmentEntryOut(**a) for a in added],
        skipped=[AddToFulfillmentSkippedOut(**s) for s in skipped],
    )
