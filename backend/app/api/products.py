from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.box_import_api_shared import read_xlsx_upload
from app.api.deps import (
    assert_inventory_read_access,
    assert_product_catalog_read_access,
    assert_seller_permission,
    get_current_user,
    get_effective_seller_id,
    require_catalog_cells_read_access,
    require_fulfillment_admin,
    seller_line_product_scope,
)
from app.api.fbs_stock_rule_reset import router as fbs_stock_rule_reset_router
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER, FULFILLMENT_STAFF
from app.db.session import get_db
from app.models.marketplace_account import MarketplaceAccount
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller_wildberries_credentials import SellerWildberriesCredentials
from app.models.stock_direction import StockDirection
from app.models.user import User
from app.services import marking_code_service as mc_svc
from app.services.catalog_service import (
    SKIP as PATCH_SKIP,
)
from app.services.catalog_service import (
    CatalogError,
    _SkipSentinel,
    apply_products_fbs_stock_limit_from_balance,
    bulk_update_products_fbs_stock_sync,
    bulk_update_products_requires_honest_sign,
    create_product,
    get_product,
    list_ozon_product_links,
    list_product_dimension_events,
    list_products,
    restore_latest_wb_dimensions,
    update_ozon_product_link,
    update_packaging_instructions,
    update_product_container_volume,
    update_product_dimensions,
    update_product_fbs_stock_sync,
    volume_liters_from_mm,
)
from app.services.fbs_stock_rule_service import (
    FbsRule,
    FbsRuleView,
    FbsStockRuleError,
    get_rule_view,
    get_rule_views,
    set_rule_for_products,
)
from app.services.product_merge_service import (
    ProductMergeError,
    merge_products,
)
from app.services.product_tz_import_service import (
    ProductTzImportError,
    apply_product_tz_import,
    build_product_tz_preview,
    build_product_tz_template_xlsx,
)
from app.services.seller_shop_service import user_can_manage_seller_shops
from app.services.seller_staff_permissions_service import PERM_PRODUCTS
from app.services.seller_wb_catalog_service import (
    FfCatalogRow,
    list_ff_catalog_rows,
    list_linked_wb_catalog_page_rows,
    list_linked_wb_catalog_rows,
    list_seller_wb_catalog_rows,
)
from app.services.staff_permissions_service import (
    PERM_INVENTORY,
    PERM_RECEPTION,
    PERM_SHIFT_LEAD,
    get_staff_permissions,
)
from app.services.stock_direction_service import (
    StockDirectionError,
    create_stock_direction,
    delete_stock_direction,
    list_stock_directions,
    update_stock_direction,
)

router = APIRouter(prefix="/products", tags=["products"])

_seller_id_query = Query(default=None)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku_code: str = Field(min_length=1, max_length=128)
    length_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    width_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    height_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    weight_g: int | None = Field(default=None, ge=1, le=1_000_000_000)
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
    ozon_sku: str | None = None
    ozon_offer_id: str | None = None
    wb_connected: bool = False
    ozon_connected: bool = False
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
    fbs_stock_sync_enabled: bool = False
    fbs_stock_limit: int | None = None
    fbs_published_amount: int | None = None
    fbs_sync_status: str | None = None
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
    ozon_sku: str | None = None
    ozon_offer_id: str | None = None
    wb_subject_name: str | None = None
    wb_primary_image_url: str | None = None
    wb_barcodes: list[str]
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
    marking_available_count: int = 0
    is_manual: bool = False
    # Площадки товара: у озоновского — «ozon», у вайлдберрисовского — «wb», у
    # объединённой карточки оба сразу (WMS-348).
    marketplaces: list[str] = Field(default_factory=list)


class FfCatalogPageOut(BaseModel):
    items: list[FfCatalogOut]
    total: int
    scope_total: int
    limit: int
    offset: int
    categories: list[str]


class ProductOut(BaseModel):
    id: str
    name: str
    sku_code: str
    category: str | None = None
    length_mm: int | None = None
    width_mm: int | None = None
    height_mm: int | None = None
    weight_g: int | None = None
    seller_id: str | None
    seller_name: str | None
    wb_nm_id: int | None = None
    wb_vendor_code: str | None = None
    ozon_sku: str | None = None
    ozon_offer_id: str | None = None
    wb_barcode: str | None = None
    wb_size: str | None = None
    wb_country_of_origin: str | None = None
    country_of_origin_iso_code: str | None = None
    wb_shelf_life: str | None = None
    packaging_instructions: str | None = None
    requires_honest_sign: bool = False
    is_manual: bool = False
    volume_liters: float | None = None
    dimensions_source: str | None = None
    dimensions_updated_at: datetime | None = None
    dimensions_updated_by_user_id: str | None = None


class ProductTzRowPreviewOut(BaseModel):
    row: int
    wb_nm_id: int | None = None
    vendor_article: str | None = None
    size: str | None = None
    barcode: str | None = None
    name: str
    sku_code: str
    packaging_instructions: str | None = None
    declared_quantity: int | None = None
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
    declared_total: int


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
    added_quantity: int
    movement_count: int
    already_applied: bool
    warehouse_id: str | None = None


class PackagingInstructionsPatch(BaseModel):
    packaging_instructions: str | None = Field(default=None, max_length=8000)
    requires_honest_sign: bool | None = None
    country_of_origin_iso_code: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")


class ProductDimensionsPatch(BaseModel):
    length_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    width_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    height_mm: int | None = Field(default=None, ge=1, le=10_000_000)
    weight_g: int | None = Field(default=None, ge=1, le=1_000_000_000)


class ProductOzonLinkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ozon_sku: str | None = Field(default=None, max_length=255)
    ozon_offer_id: str | None = Field(default=None, max_length=255)


class ProductMergeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Ровно две карточки за раз — так поставил владелец. Ограничение стоит на
    # вводе, поэтому дальше по коду сторожить нечего.
    product_ids: list[uuid.UUID] = Field(min_length=2, max_length=2)


class ProductContainerDimensions(BaseModel):
    volume_liters: float = Field(gt=0, le=1_000_000)
    container_basis: str = Field(min_length=1, max_length=2000)


class ProductDimensionEventOut(BaseModel):
    id: str
    source: str
    created_at: datetime
    author_name: str | None
    length_mm: int | None
    width_mm: int | None
    height_mm: int | None
    weight_g: int | None
    volume_liters: float | None
    container_basis: str | None
    is_current: bool


def _dimension_event_out(
    event: object,
    *,
    author_name: str | None,
) -> ProductDimensionEventOut:
    from app.models.product_dimension_event import ProductDimensionEvent

    assert isinstance(event, ProductDimensionEvent)
    return ProductDimensionEventOut(
        id=str(event.id),
        source={"wb": "wildberries", "container_override": "container"}.get(
            event.source,
            event.source,
        ),
        created_at=event.observed_at,
        author_name=author_name,
        length_mm=event.length_mm,
        width_mm=event.width_mm,
        height_mm=event.height_mm,
        weight_g=event.weight_g,
        volume_liters=float(event.volume_liters) if event.volume_liters is not None else None,
        container_basis=event.container_basis,
        is_current=event.applied,
    )


class ProductHonestSignBulkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=10000)
    requires_honest_sign: bool = True


class ProductHonestSignBulkOut(BaseModel):
    updated_count: int


class ProductFbsStockSyncPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fbs_stock_sync_enabled: bool | None = None
    fbs_stock_limit: int | None = Field(default=None, ge=0)


class ProductFbsRuleBody(BaseModel):
    """Правило публикации остатка: доля свободного остатка, а не число штук."""

    model_config = ConfigDict(extra="forbid")

    publish: bool
    same_everywhere: bool
    percent: int = Field(ge=0, le=100)
    # Ключ — идентификатор склада в кабинете WB (он приходит числом, но в JSON
    # ключи объекта всегда строки).
    by_warehouse: dict[str, int] = Field(default_factory=dict)
    # Режим «остаток по штукам»: доля не применяется, числа задаются по складам.
    units_mode: bool = False
    # Сколько штук выделено на каждый склад WB. Ключ — тот же номер склада.
    units_by_warehouse: dict[str, int] = Field(default_factory=dict)


class ProductFbsRuleOut(ProductFbsRuleBody):
    """То же правило плюс три числа, из которых видно, откуда взялось количество.

    `published_now` считает сервер тем же кодом, что и публикация: если бы экран
    пересчитывал долю своей формулой, две формулы однажды разошлись бы.
    """

    free_stock: int
    on_hand: int
    reserved: int
    published_now: int
    # Сколько от квоты каждого склада ещё осталось. Именно это подставляется в
    # поля ввода: оператор правит числа, глядя на сегодняшний расклад.
    units_remaining_by_warehouse: dict[str, int] = Field(default_factory=dict)


FBS_RULE_BULK_READ_MAX_PRODUCTS = 200


class ProductsFbsRuleBulkReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(min_length=1)

    @field_validator("product_ids")
    @classmethod
    def validate_batch_size(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(value) > FBS_RULE_BULK_READ_MAX_PRODUCTS:
            raise ValueError(
                "За один запрос можно получить правила максимум "
                f"для {FBS_RULE_BULK_READ_MAX_PRODUCTS} товаров."
            )
        return value


class ProductFbsRuleBulkItemOut(ProductFbsRuleOut):
    product_id: str


class ProductsFbsRuleBulkReadOut(BaseModel):
    items: list[ProductFbsRuleBulkItemOut]


class ProductsFbsRuleBulkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID]
    rule: ProductFbsRuleBody


class ProductsFbsRuleBulkOut(BaseModel):
    updated_count: int


class ProductFbsStockSyncBulkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] | None = None
    fbs_stock_sync_enabled: bool
    fbs_stock_limit: int | None = Field(default=None, ge=0)


class ProductFbsStockSyncBulkOut(BaseModel):
    updated_count: int


class ProductFbsStockLimitFromBalanceBulkPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=10000)


class ProductFbsStockLimitFromBalanceUpdatedItem(BaseModel):
    product_id: str
    fbs_stock_limit: int
    reset_warehouses_count: int


class ProductFbsStockLimitFromBalanceSkippedItem(BaseModel):
    product_id: str
    reason: str


class ProductFbsStockLimitFromBalanceBulkOut(BaseModel):
    updated_count: int
    updated: list[ProductFbsStockLimitFromBalanceUpdatedItem]
    skipped: list[ProductFbsStockLimitFromBalanceSkippedItem]
    # Сколько товаров из updated получили сброшенную (обнулённую) разнарядку по
    # складам — фронту нужно отдельным числом для предупреждения оператору.
    pool_reset_products_count: int


class StockDirectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    comment: str | None = Field(default=None, max_length=2000)
    quantity: int = Field(ge=0)
    is_fbs: bool = False


class StockDirectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    comment: str | None = Field(default=None, max_length=2000)
    quantity: int | None = Field(default=None, ge=0)
    is_fbs: bool | None = None


class StockDirectionOut(BaseModel):
    id: str
    product_id: str
    name: str
    comment: str | None
    quantity: int
    is_fbs: bool
    created_at: str
    updated_at: str


def _product_out(
    p: object,
    *,
    ozon_sku: str | None = None,
    ozon_offer_id: str | None = None,
) -> ProductOut:
    from app.models.product import Product

    assert isinstance(p, Product)
    return ProductOut(
        id=str(p.id),
        name=p.name,
        sku_code=p.sku_code,
        category=p.category,
        length_mm=p.length_mm,
        width_mm=p.width_mm,
        height_mm=p.height_mm,
        weight_g=p.weight_g,
        seller_id=str(p.seller_id) if p.seller_id else None,
        seller_name=p.seller.name if p.seller is not None else None,
        wb_nm_id=int(p.wb_nm_id) if p.wb_nm_id is not None else None,
        wb_vendor_code=p.wb_vendor_code,
        ozon_sku=ozon_sku,
        ozon_offer_id=ozon_offer_id,
        wb_barcode=p.wb_barcode,
        wb_size=p.wb_size,
        wb_country_of_origin=p.wb_country_of_origin,
        country_of_origin_iso_code=p.country_of_origin_iso_code,
        wb_shelf_life=p.wb_shelf_life,
        packaging_instructions=p.packaging_instructions,
        requires_honest_sign=bool(p.requires_honest_sign),
        # Manual until WB sync/link sets nmID on same barcode.
        is_manual=p.wb_nm_id is None,
        volume_liters=(
            p.volume_liters
            if p.volume_liters is not None
            else volume_liters_from_mm(p.length_mm, p.width_mm, p.height_mm)
        ),
        dimensions_source=p.dimensions_source,
        dimensions_updated_at=p.dimensions_updated_at,
        dimensions_updated_by_user_id=(
            str(p.dimensions_updated_by_user_id)
            if p.dimensions_updated_by_user_id is not None
            else None
        ),
    )


def _stock_direction_out(direction: object) -> StockDirectionOut:
    from app.models.stock_direction import StockDirection

    assert isinstance(direction, StockDirection)
    return StockDirectionOut(
        id=str(direction.id),
        product_id=str(direction.product_id),
        name=direction.name,
        comment=direction.comment,
        quantity=int(direction.quantity),
        is_fbs=bool(direction.is_fbs),
        created_at=direction.created_at.isoformat(),
        updated_at=direction.updated_at.isoformat(),
    )


async def _product_seller_scope_for_write(
    user: User,
    session: AsyncSession,
    product_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> uuid.UUID | None:
    p = await get_product(session, user.tenant_id, product_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    if user.role == FULFILLMENT_ADMIN:
        return None
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    owner_id = user.seller_id
    if user_can_manage_seller_shops(user) and effective_seller_id is not None:
        owner_id = effective_seller_id
    if owner_id is None or p.seller_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return owner_id


def _http_from_stock_direction_error(exc: StockDirectionError) -> HTTPException:
    if exc.code in {"product_not_found", "direction_not_found"}:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.code)
    if exc.code == "forbidden":
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if exc.code in {
        "empty_name",
        "invalid_quantity",
        "directions_exceed_stock",
        "insufficient_fbs_pool",
    }:
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code)


def _http_from_tz_import_error(exc: ProductTzImportError) -> HTTPException:
    code = exc.code
    if code in {
        "unsupported_file_type",
        "empty_file",
        "missing_column",
        "row_errors",
        "warehouse_required",
        "warehouse_ambiguous",
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
    search: Annotated[str | None, Query()] = None,
    marketplace: Annotated[Literal["wildberries", "ozon"] | None, Query()] = None,
) -> list[ProductOut]:
    await assert_product_catalog_read_access(session, user)
    rows = await list_products(
        session,
        user.tenant_id,
        seller_id=seller_scope,
        search=search,
        marketplace=marketplace,
    )
    ozon_links = await list_ozon_product_links(session, user.tenant_id, {p.id for p in rows})
    return [
        _product_out(
            p,
            ozon_sku=ozon_links[p.id].external_sku if p.id in ozon_links else None,
            ozon_offer_id=ozon_links[p.id].external_offer_id if p.id in ozon_links else None,
        )
        for p in rows
    ]


@router.get("/categories", response_model=list[str])
async def get_product_categories(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_scope: Annotated[uuid.UUID | None, Depends(seller_line_product_scope)],
) -> list[str]:
    await assert_product_catalog_read_access(session, user)
    category = func.trim(Product.category)
    stmt = (
        select(category)
        .where(
            Product.tenant_id == user.tenant_id,
            Product.category.is_not(None),
            category != "",
        )
        .distinct()
        .order_by(category)
    )
    if seller_scope is not None:
        stmt = stmt.where(Product.seller_id == seller_scope)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/wb-catalog", response_model=list[SellerWbCatalogOut])
async def get_seller_wb_catalog(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
    search: Annotated[str | None, Query()] = None,
    # Потолок выдачи. По умолчанию его НЕТ: портал селлера грузит каталог целиком и
    # ищет на клиенте — с лимитом товар за границей выборки просто не находится.
    # Лимит имеет смысл только вместе с search, когда клиент ищет на сервере.
    limit: Annotated[int | None, Query(ge=1, le=20000)] = None,
) -> list[SellerWbCatalogOut]:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
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
    rows = await list_seller_wb_catalog_rows(
        session, user.tenant_id, catalog_seller_id, search=search, limit=limit
    )
    wb_connected = (
        await session.scalar(
            select(SellerWildberriesCredentials.seller_id).where(
                SellerWildberriesCredentials.seller_id == catalog_seller_id,
                SellerWildberriesCredentials.marketplace_token_encrypted.isnot(None),
            )
        )
        is not None
    )
    ozon_connected = (
        await session.scalar(
            select(MarketplaceAccount.id).where(
                MarketplaceAccount.tenant_id == user.tenant_id,
                MarketplaceAccount.seller_id == catalog_seller_id,
                MarketplaceAccount.marketplace == "ozon",
                MarketplaceAccount.account_slot == "primary",
                MarketplaceAccount.is_active.is_(True),
            )
        )
        is not None
    )
    return [
        SellerWbCatalogOut(
            **r.as_dict(),
            wb_connected=wb_connected,
            ozon_connected=ozon_connected,
            has_packaging_instructions=bool((r.packaging_instructions or "").strip()),
        )
        for r in rows
    ]


@router.get("/linked-wb-catalog", response_model=list[FfCatalogOut])
async def get_linked_wb_catalog(
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
    search: Annotated[str | None, Query()] = None,
    marketplace: Annotated[Literal["wildberries", "ozon"] | None, Query()] = None,
) -> list[FfCatalogOut]:
    """WB enrichment for all products (barcodes/photo) — including before first stock movement."""
    rows = await list_linked_wb_catalog_rows(
        session, user.tenant_id, seller_id=seller_id, search=search, marketplace=marketplace
    )
    return await _ff_catalog_out_rows(session, user.tenant_id, rows)


@router.get("/ff-catalog", response_model=list[FfCatalogOut])
async def get_ff_catalog(
    user: Annotated[User, Depends(require_catalog_cells_read_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
    search: Annotated[str | None, Query()] = None,
    marketplace: Annotated[Literal["wildberries", "ozon"] | None, Query()] = None,
) -> list[FfCatalogOut]:
    if seller_id is not None and user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    rows = await list_ff_catalog_rows(
        session, user.tenant_id, seller_id=seller_id, search=search, marketplace=marketplace
    )
    return await _ff_catalog_out_rows(session, user.tenant_id, rows)


@router.get("/ff-catalog-page", response_model=FfCatalogPageOut)
async def get_ff_catalog_page(
    user: Annotated[User, Depends(require_catalog_cells_read_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    seller_id: uuid.UUID | None = _seller_id_query,
    search: Annotated[str | None, Query(max_length=255)] = None,
    category: Annotated[str | None, Query(max_length=255)] = None,
    marketplace: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FfCatalogPageOut:
    rows, total, scope_total, categories = await list_linked_wb_catalog_page_rows(
        session,
        user.tenant_id,
        seller_id=seller_id,
        search=search,
        category=category,
        marketplace=marketplace,
        limit=limit,
        offset=offset,
    )
    return FfCatalogPageOut(
        items=await _ff_catalog_out_rows(session, user.tenant_id, rows),
        total=total,
        scope_total=scope_total,
        limit=limit,
        offset=offset,
        categories=categories,
    )


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
            weight_g=body.weight_g,
            seller_id=body.seller_id,
            wb_barcode=body.wb_barcode,
            wb_size=body.wb_size,
            wb_vendor_code=body.wb_vendor_code,
            packaging_instructions=body.packaging_instructions,
            requires_honest_sign=body.requires_honest_sign,
        )
    except CatalogError as exc:
        if exc.code in ("invalid_dimensions", "invalid_weight"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
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
    ozon_links = await list_ozon_product_links(session, user.tenant_id, {p.id})
    ozon_link = ozon_links.get(p.id)
    return _product_out(
        p,
        ozon_sku=ozon_link.external_sku if ozon_link is not None else None,
        ozon_offer_id=ozon_link.external_offer_id if ozon_link is not None else None,
    )


@router.patch("/{product_id}/ozon-link", response_model=ProductOut)
async def patch_product_ozon_link(
    product_id: uuid.UUID,
    body: ProductOzonLinkPatch,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProductOut:
    try:
        product = await update_ozon_product_link(
            session,
            user.tenant_id,
            product_id,
            ozon_sku=body.ozon_sku,
            ozon_offer_id=body.ozon_offer_id,
        )
    except CatalogError as exc:
        if exc.code == "product_not_found":
            raise HTTPException(status_code=404, detail=exc.code) from None
        if exc.code in {"ozon_link_requires_seller", "ozon_link_required"}:
            raise HTTPException(status_code=422, detail=exc.code) from None
        if exc.code == "ozon_sku_taken":
            raise HTTPException(status_code=409, detail=exc.code) from None
        raise
    link = (await list_ozon_product_links(session, user.tenant_id, {product.id})).get(product.id)
    return _product_out(
        product,
        ozon_sku=link.external_sku if link is not None else None,
        ozon_offer_id=link.external_offer_id if link is not None else None,
    )


@router.post("/merge", response_model=ProductOut)
async def post_products_merge(
    body: ProductMergeBody,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProductOut:
    """Объединить две карточки одного товара в одну (WMS-349).

    Возвращает карточку, которая осталась: оператор сразу видит в ответе,
    под каким артикулом товар теперь живёт.
    """
    try:
        product = await merge_products(session, user.tenant_id, body.product_ids)
    except ProductMergeError as exc:
        if exc.code == "product_not_found":
            raise HTTPException(status_code=404, detail=exc.code) from None
        if exc.code == "merge_conflict":
            raise HTTPException(status_code=409, detail=exc.code) from None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.code
        ) from None
    link = (await list_ozon_product_links(session, user.tenant_id, {product.id})).get(product.id)
    return _product_out(
        product,
        ozon_sku=link.external_sku if link is not None else None,
        ozon_offer_id=link.external_offer_id if link is not None else None,
    )


def _tz_preview_out(result: object) -> ProductTzImportPreviewOut:
    from app.services.product_tz_import_service import ProductTzPreviewResult

    assert isinstance(result, ProductTzPreviewResult)
    return ProductTzImportPreviewOut(
        sheet_name=result.sheet_name,
        rows=[
            ProductTzRowPreviewOut(
                row=row.row,
                wb_nm_id=row.wb_nm_id,
                vendor_article=row.vendor_article,
                size=row.size,
                barcode=row.barcode,
                name=row.name,
                sku_code=row.sku_code,
                packaging_instructions=row.packaging_instructions,
                declared_quantity=row.declared_quantity,
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
            declared_total=result.summary.declared_total,
        ),
    )


async def _marketplaces_by_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: Sequence[FfCatalogRow],
) -> dict[uuid.UUID, list[str]]:
    """Площадки каждой строки каталога — тем же правилом, что и фильтр над таблицей.

    Правило «товар относится к площадке» уже сформулировано один раз, в
    ``marketplace_scope_condition``: озоновский — если есть живая привязка Ozon,
    вайлдберрисовский — если есть nmID, артикул продавца или живая привязка WB.
    Значок обязан отвечать ровно ему, иначе оператор отфильтрует каталог по
    Wildberries и увидит строки без вайлдберрисовского значка.

    Один запрос на страницу, а не по запросу на строку: в каталоге до двухсот
    строк за раз.
    """
    product_ids = {r.product_id for r in rows}
    if not product_ids:
        return {}
    links = await session.execute(
        select(ProductMarketplaceLink.product_id, ProductMarketplaceLink.marketplace).where(
            ProductMarketplaceLink.tenant_id == tenant_id,
            ProductMarketplaceLink.product_id.in_(product_ids),
            ProductMarketplaceLink.is_active.is_(True),
        )
    )
    linked: dict[uuid.UUID, set[str]] = {}
    for product_id, marketplace in links.all():
        linked.setdefault(product_id, set()).add(marketplace)
    result: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        markets = linked.get(row.product_id, set())
        badges: list[str] = []
        is_wb = (
            row.wb_nm_id is not None
            or row.wb_vendor_code is not None
            or bool(markets & {"wildberries", "wb"})
        )
        if is_wb:
            badges.append("wb")
        if "ozon" in markets:
            badges.append("ozon")
        result[row.product_id] = badges
    return result


async def _ff_catalog_out_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rows: Sequence[FfCatalogRow],
) -> list[FfCatalogOut]:
    counts = await mc_svc.count_available_for_products_batch(
        session,
        tenant_id,
        {r.product_id for r in rows},
    )
    marketplaces = await _marketplaces_by_product(session, tenant_id, rows)
    return [
        FfCatalogOut(
            **r.as_dict(),
            has_packaging_instructions=bool((r.packaging_instructions or "").strip()),
            marking_available_count=counts.get(r.product_id, 0),
            marketplaces=marketplaces.get(r.product_id, []),
        )
        for r in rows
    ]


@router.get("/import-tz/template")
async def get_product_tz_import_template(
    user: Annotated[User, Depends(require_fulfillment_admin)],
) -> StreamingResponse:
    del user
    content = build_product_tz_template_xlsx()
    headers = {"Content-Disposition": 'attachment; filename="wms-product-catalog-template.xlsx"'}
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
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
            declared_total=result.summary.declared_total,
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
        added_quantity=result.added_quantity,
        movement_count=result.movement_count,
        already_applied=result.already_applied,
        warehouse_id=str(result.warehouse_id) if result.warehouse_id else None,
    )


@router.patch("/requires-honest-sign/bulk", response_model=ProductHonestSignBulkOut)
async def patch_products_requires_honest_sign_bulk(
    body: ProductHonestSignBulkPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductHonestSignBulkOut:
    seller_scope: uuid.UUID | None = None
    if user.role == FULFILLMENT_SELLER:
        seller_scope = user.seller_id
        if user_can_manage_seller_shops(user) and effective_seller_id is not None:
            seller_scope = effective_seller_id
        if seller_scope is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    updated_count = await bulk_update_products_requires_honest_sign(
        session,
        user.tenant_id,
        product_ids=body.product_ids,
        requires_honest_sign=body.requires_honest_sign,
        seller_id=seller_scope,
    )
    return ProductHonestSignBulkOut(updated_count=updated_count)


@router.patch("/{product_id}/dimensions", response_model=ProductOut)
async def patch_product_dimensions(
    product_id: uuid.UUID,
    body: ProductDimensionsPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    p = await get_product(session, user.tenant_id, product_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    if user.role == FULFILLMENT_SELLER:
        owner_id = user.seller_id
        if user_can_manage_seller_shops(user) and effective_seller_id is not None:
            owner_id = effective_seller_id
        if owner_id is None or p.seller_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role == FULFILLMENT_STAFF:
        perms = await get_staff_permissions(session, user)
        if not (
            perms.has(PERM_RECEPTION) or perms.has(PERM_SHIFT_LEAD) or perms.has(PERM_INVENTORY)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        patch_fields = body.model_dump(exclude_unset=True)
        dimension_keys = {"length_mm", "width_mm", "height_mm"}
        touched_dimensions = bool(dimension_keys & patch_fields.keys())
        if touched_dimensions and not dimension_keys.issubset(patch_fields.keys()):
            raise CatalogError("invalid_dimensions")
        updated = await update_product_dimensions(
            session,
            user.tenant_id,
            product_id,
            length_mm=patch_fields.get("length_mm") if touched_dimensions else p.length_mm,
            width_mm=patch_fields.get("width_mm") if touched_dimensions else p.width_mm,
            height_mm=patch_fields.get("height_mm") if touched_dimensions else p.height_mm,
            weight_g=patch_fields.get("weight_g"),
            weight_g_set="weight_g" in patch_fields,
            author_user_id=user.id,
        )
    except CatalogError as exc:
        if exc.code in ("invalid_dimensions", "invalid_weight"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from None
        raise
    return _product_out(updated)


@router.get("/{product_id}/dimensions/history", response_model=list[ProductDimensionEventOut])
async def get_product_dimension_history(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProductDimensionEventOut]:
    await assert_inventory_read_access(session, user)
    try:
        product = await get_product(session, user.tenant_id, product_id)
        if product is None:
            raise CatalogError("product_not_found")
        seller_scope: uuid.UUID | None = None
        if user.role == FULFILLMENT_SELLER:
            seller_scope = user.seller_id
            if seller_scope is None or product.seller_id != seller_scope:
                raise CatalogError("product_not_found")
        events = await list_product_dimension_events(
            session,
            user.tenant_id,
            product_id,
            seller_id=seller_scope,
        )
    except CatalogError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from None
    author_ids = {event.author_user_id for event in events if event.author_user_id is not None}
    author_names: dict[uuid.UUID, str] = {}
    if author_ids:
        result = await session.execute(
            select(User.id, User.email).where(
                User.tenant_id == user.tenant_id,
                User.id.in_(author_ids),
            )
        )
        author_names = {author_id: author_email for author_id, author_email in result.tuples()}
    return [
        _dimension_event_out(
            event,
            author_name=(
                author_names.get(event.author_user_id) if event.author_user_id is not None else None
            ),
        )
        for event in events
    ]


@router.post("/{product_id}/dimensions/container", response_model=ProductOut)
async def post_product_container_dimensions(
    product_id: uuid.UUID,
    body: ProductContainerDimensions,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProductOut:
    if user.role != FULFILLMENT_ADMIN:
        await assert_inventory_read_access(session, user)
        if user.role != FULFILLMENT_STAFF:
            raise HTTPException(status_code=403, detail="forbidden")
        perms = await get_staff_permissions(session, user)
        if not perms.has(PERM_INVENTORY):
            raise HTTPException(status_code=403, detail="forbidden")
    try:
        product = await update_product_container_volume(
            session,
            user.tenant_id,
            product_id,
            volume_liters=body.volume_liters,
            container_basis=body.container_basis,
            author_user_id=user.id,
        )
    except CatalogError as exc:
        code = 404 if exc.code == "product_not_found" else 422
        raise HTTPException(status_code=code, detail=exc.code) from None
    return _product_out(product)


@router.post("/{product_id}/dimensions/restore-wb", response_model=ProductOut)
async def restore_product_wb_dimensions(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ProductOut:
    try:
        updated = await restore_latest_wb_dimensions(session, user.tenant_id, product_id)
    except CatalogError as exc:
        code = 404 if exc.code in ("product_not_found", "wb_dimensions_not_found") else 422
        raise HTTPException(status_code=code, detail=exc.code) from None
    return _product_out(updated)


@router.patch("/{product_id}/packaging-instructions", response_model=ProductOut)
async def patch_product_packaging_instructions(
    product_id: uuid.UUID,
    body: PackagingInstructionsPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
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
            country_of_origin_iso_code=body.country_of_origin_iso_code,
        )
    except CatalogError as exc:
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from None
        raise
    return _product_out(updated)


@router.get("/{product_id}/stock-directions", response_model=list[StockDirectionOut])
async def get_product_stock_directions(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> list[StockDirectionOut]:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    seller_scope = await _product_seller_scope_for_write(
        user,
        session,
        product_id,
        effective_seller_id,
    )
    try:
        directions = await list_stock_directions(
            session,
            user.tenant_id,
            product_id,
            seller_scope=seller_scope,
        )
    except StockDirectionError as exc:
        raise _http_from_stock_direction_error(exc) from None
    return [_stock_direction_out(direction) for direction in directions]


@router.post(
    "/{product_id}/stock-directions",
    response_model=StockDirectionOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_product_stock_direction(
    product_id: uuid.UUID,
    body: StockDirectionCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> StockDirectionOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    seller_scope = await _product_seller_scope_for_write(
        user,
        session,
        product_id,
        effective_seller_id,
    )
    try:
        direction = await create_stock_direction(
            session,
            user.tenant_id,
            product_id,
            name=body.name,
            comment=body.comment,
            quantity=body.quantity,
            is_fbs=body.is_fbs,
            seller_scope=seller_scope,
        )
    except StockDirectionError as exc:
        raise _http_from_stock_direction_error(exc) from None
    return _stock_direction_out(direction)


@router.patch("/stock-directions/{direction_id}", response_model=StockDirectionOut)
async def patch_product_stock_direction(
    direction_id: uuid.UUID,
    body: StockDirectionPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> StockDirectionOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    if not body.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="empty_patch",
        )
    direction = await session.get(StockDirection, direction_id)
    if direction is None or direction.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="direction_not_found")
    seller_scope = await _product_seller_scope_for_write(
        user,
        session,
        direction.product_id,
        effective_seller_id,
    )
    try:
        updated = await update_stock_direction(
            session,
            user.tenant_id,
            direction_id,
            name=body.name if "name" in body.model_fields_set else None,
            comment=body.comment,
            set_comment="comment" in body.model_fields_set,
            quantity=body.quantity if "quantity" in body.model_fields_set else None,
            is_fbs=body.is_fbs if "is_fbs" in body.model_fields_set else None,
            seller_scope=seller_scope,
        )
    except StockDirectionError as exc:
        raise _http_from_stock_direction_error(exc) from None
    return _stock_direction_out(updated)


@router.delete("/stock-directions/{direction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_stock_direction(
    direction_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> None:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    direction = await session.get(StockDirection, direction_id)
    if direction is None or direction.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="direction_not_found")
    seller_scope = await _product_seller_scope_for_write(
        user,
        session,
        direction.product_id,
        effective_seller_id,
    )
    try:
        await delete_stock_direction(
            session,
            user.tenant_id,
            direction_id,
            seller_scope=seller_scope,
        )
    except StockDirectionError as exc:
        raise _http_from_stock_direction_error(exc) from None


@router.patch("/{product_id}/fbs-stock-sync", response_model=ProductOut)
async def patch_product_fbs_stock_sync(
    product_id: uuid.UUID,
    body: ProductFbsStockSyncPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
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

    enabled_patch: bool | _SkipSentinel = PATCH_SKIP
    if "fbs_stock_sync_enabled" in body.model_fields_set:
        enabled_patch = bool(body.fbs_stock_sync_enabled)
    limit_patch: int | _SkipSentinel | None = PATCH_SKIP
    if "fbs_stock_limit" in body.model_fields_set:
        limit_patch = body.fbs_stock_limit

    try:
        updated = await update_product_fbs_stock_sync(
            session,
            user.tenant_id,
            product_id,
            fbs_stock_sync_enabled=enabled_patch,
            fbs_stock_limit=limit_patch,
        )
    except CatalogError as exc:
        if exc.code in {"empty_patch", "invalid_fbs_stock_limit"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        if exc.code == "product_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="product_not_found",
            ) from None
        raise
    return _product_out(updated)


def _rule_error_status(code: str) -> int:
    if code in {"product_not_found", "warehouse_not_found"}:
        return status.HTTP_404_NOT_FOUND
    return status.HTTP_422_UNPROCESSABLE_CONTENT


async def _assert_product_rule_access(
    session: AsyncSession,
    user: User,
    product_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> None:
    """Правило остатка правит фулфилмент или сам продавец — но только свой товар."""
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    product = await get_product(session, user.tenant_id, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    if user.role == FULFILLMENT_SELLER:
        owner_id = user.seller_id
        if user_can_manage_seller_shops(user) and effective_seller_id is not None:
            owner_id = effective_seller_id
        if owner_id is None or product.seller_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


async def _assert_products_rule_access(
    session: AsyncSession,
    user: User,
    product_ids: list[uuid.UUID],
    effective_seller_id: uuid.UUID | None,
) -> None:
    """Пакетная версия той же tenant/seller-проверки, что у одиночной ручки."""
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    rows = list(
        (
            await session.execute(
                select(Product.id, Product.seller_id).where(
                    Product.tenant_id == user.tenant_id,
                    Product.id.in_(product_ids),
                )
            )
        ).all()
    )
    if len({product_id for product_id, _seller_id in rows}) != len(product_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found"
        )
    if user.role == FULFILLMENT_SELLER:
        owner_id = user.seller_id
        if user_can_manage_seller_shops(user) and effective_seller_id is not None:
            owner_id = effective_seller_id
        if owner_id is None or any(seller_id != owner_id for _product_id, seller_id in rows):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    elif user.role != FULFILLMENT_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _rule_from_body(body: ProductFbsRuleBody) -> FbsRule:
    return FbsRule(
        publish=body.publish,
        same_everywhere=body.same_everywhere,
        percent=body.percent,
        by_warehouse={int(key): value for key, value in body.by_warehouse.items()},
        units_mode=body.units_mode,
        units_by_warehouse={
            int(key): value for key, value in body.units_by_warehouse.items()
        },
    )


def _rule_view_out(
    product_id: uuid.UUID, view: FbsRuleView
) -> ProductFbsRuleBulkItemOut:
    return ProductFbsRuleBulkItemOut(
        product_id=str(product_id),
        publish=view.rule.publish,
        same_everywhere=view.rule.same_everywhere,
        percent=view.rule.percent,
        by_warehouse={str(key): value for key, value in view.rule.by_warehouse.items()},
        units_mode=view.rule.units_mode,
        units_by_warehouse={
            str(key): value for key, value in view.rule.units_by_warehouse.items()
        },
        free_stock=view.free_stock,
        on_hand=view.on_hand,
        reserved=view.reserved,
        published_now=view.published_now,
        units_remaining_by_warehouse={
            str(key): value
            for key, value in view.units_remaining_by_warehouse.items()
        },
    )


@router.post("/fbs-rule/bulk", response_model=ProductsFbsRuleBulkReadOut)
async def post_products_fbs_rule_bulk_read(
    body: ProductsFbsRuleBulkReadBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductsFbsRuleBulkReadOut:
    """Вернуть до 200 FBS-правил одним запросом, сохранив порядок товаров."""
    product_ids = list(dict.fromkeys(body.product_ids))
    await _assert_products_rule_access(session, user, product_ids, effective_seller_id)
    try:
        views = await get_rule_views(session, user.tenant_id, product_ids)
    except FbsStockRuleError as exc:
        raise HTTPException(
            status_code=_rule_error_status(exc.code), detail=exc.message
        ) from None
    return ProductsFbsRuleBulkReadOut(
        items=[_rule_view_out(product_id, views[product_id]) for product_id in product_ids]
    )


@router.get("/{product_id}/fbs-rule", response_model=ProductFbsRuleOut)
async def get_product_fbs_rule(
    product_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductFbsRuleOut:
    await _assert_product_rule_access(session, user, product_id, effective_seller_id)
    try:
        view = await get_rule_view(session, user.tenant_id, product_id)
    except FbsStockRuleError as exc:
        raise HTTPException(
            status_code=_rule_error_status(exc.code), detail=exc.message
        ) from None
    return ProductFbsRuleOut(
        publish=view.rule.publish,
        same_everywhere=view.rule.same_everywhere,
        percent=view.rule.percent,
        by_warehouse={str(key): value for key, value in view.rule.by_warehouse.items()},
        units_mode=view.rule.units_mode,
        units_by_warehouse={
            str(key): value for key, value in view.rule.units_by_warehouse.items()
        },
        free_stock=view.free_stock,
        on_hand=view.on_hand,
        reserved=view.reserved,
        published_now=view.published_now,
        units_remaining_by_warehouse={
            str(key): value
            for key, value in view.units_remaining_by_warehouse.items()
        },
    )


@router.put("/{product_id}/fbs-rule", response_model=ProductFbsRuleOut)
async def put_product_fbs_rule(
    product_id: uuid.UUID,
    body: ProductFbsRuleBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductFbsRuleOut:
    await _assert_product_rule_access(session, user, product_id, effective_seller_id)
    try:
        await set_rule_for_products(
            session,
            user.tenant_id,
            [product_id],
            _rule_from_body(body),
            updated_by=user.id,
        )
    except FbsStockRuleError as exc:
        raise HTTPException(
            status_code=_rule_error_status(exc.code), detail=exc.message
        ) from None
    return await get_product_fbs_rule(product_id, user, session, effective_seller_id)


@router.put("/fbs-rule", response_model=ProductsFbsRuleBulkOut)
async def put_products_fbs_rule(
    body: ProductsFbsRuleBulkBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductsFbsRuleBulkOut:
    """Одна доля сразу на несколько товаров — но только внутри одного продавца."""
    for product_id in body.product_ids:
        await _assert_product_rule_access(session, user, product_id, effective_seller_id)
    try:
        await set_rule_for_products(
            session,
            user.tenant_id,
            list(body.product_ids),
            _rule_from_body(body.rule),
            updated_by=user.id,
        )
    except FbsStockRuleError as exc:
        raise HTTPException(
            status_code=_rule_error_status(exc.code), detail=exc.message
        ) from None
    return ProductsFbsRuleBulkOut(updated_count=len(body.product_ids))


@router.patch("/fbs-stock-sync/bulk", response_model=ProductFbsStockSyncBulkOut)
async def patch_products_fbs_stock_sync_bulk(
    body: ProductFbsStockSyncBulkPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductFbsStockSyncBulkOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    seller_scope = user.seller_id
    if user_can_manage_seller_shops(user) and effective_seller_id is not None:
        seller_scope = effective_seller_id
    if seller_scope is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")
    bulk_limit_patch: int | _SkipSentinel | None = PATCH_SKIP
    if "fbs_stock_limit" in body.model_fields_set:
        bulk_limit_patch = body.fbs_stock_limit
    try:
        updated_count = await bulk_update_products_fbs_stock_sync(
            session,
            user.tenant_id,
            seller_scope,
            product_ids=body.product_ids,
            fbs_stock_sync_enabled=body.fbs_stock_sync_enabled,
            fbs_stock_limit=bulk_limit_patch,
        )
    except CatalogError as exc:
        if exc.code == "invalid_fbs_stock_limit":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.code,
            ) from None
        raise
    return ProductFbsStockSyncBulkOut(updated_count=updated_count)


@router.patch(
    "/fbs-stock-limit/from-balance/bulk",
    response_model=ProductFbsStockLimitFromBalanceBulkOut,
)
async def patch_products_fbs_stock_limit_from_balance_bulk(
    body: ProductFbsStockLimitFromBalanceBulkPatch,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductFbsStockLimitFromBalanceBulkOut:
    await assert_seller_permission(session, user, PERM_PRODUCTS)
    if user.role != FULFILLMENT_SELLER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    seller_scope = user.seller_id
    if user_can_manage_seller_shops(user) and effective_seller_id is not None:
        seller_scope = effective_seller_id
    if seller_scope is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="seller_not_linked")

    result = await apply_products_fbs_stock_limit_from_balance(
        session,
        user.tenant_id,
        seller_scope,
        product_ids=body.product_ids,
    )
    return ProductFbsStockLimitFromBalanceBulkOut(
        updated_count=len(result.updated),
        updated=[
            ProductFbsStockLimitFromBalanceUpdatedItem(
                product_id=str(item.product_id),
                fbs_stock_limit=item.fbs_stock_limit,
                reset_warehouses_count=item.reset_warehouses_count,
            )
            for item in result.updated
        ],
        skipped=[
            ProductFbsStockLimitFromBalanceSkippedItem(
                product_id=str(item.product_id),
                reason=item.reason,
            )
            for item in result.skipped
        ],
        pool_reset_products_count=result.reset_products_count,
    )

router.routes.extend(fbs_stock_rule_reset_router.routes)
