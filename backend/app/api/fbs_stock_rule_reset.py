"""Явный второй шаг: сброс старых абсолютных FBS-лимитов."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_seller_permission,
    get_current_user,
    get_effective_seller_id,
)
from app.core.roles import FULFILLMENT_ADMIN, FULFILLMENT_SELLER
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import get_product
from app.services.fbs_stock_rule_service import (
    FbsStockRuleError,
    reset_legacy_limits_for_products,
)
from app.services.seller_shop_service import user_can_manage_seller_shops
from app.services.seller_staff_permissions_service import PERM_PRODUCTS

router = APIRouter(prefix="/products", tags=["products"])


class ProductsLegacyFbsLimitsResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: list[uuid.UUID] = Field(min_length=1)


class ProductsLegacyFbsLimitsResetOut(BaseModel):
    updated_count: int


async def _assert_reset_access(
    session: AsyncSession,
    user: User,
    product_id: uuid.UUID,
    effective_seller_id: uuid.UUID | None,
) -> None:
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


@router.post(
    "/fbs-rule/reset-legacy-limits",
    response_model=ProductsLegacyFbsLimitsResetOut,
)
async def reset_products_legacy_fbs_limits(
    body: ProductsLegacyFbsLimitsResetBody,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    effective_seller_id: Annotated[uuid.UUID | None, Depends(get_effective_seller_id)],
) -> ProductsLegacyFbsLimitsResetOut:
    """Обнулить старые числа только после сохранения процентного правила."""
    for product_id in body.product_ids:
        await _assert_reset_access(session, user, product_id, effective_seller_id)
    try:
        updated_count = await reset_legacy_limits_for_products(
            session, user.tenant_id, body.product_ids
        )
    except FbsStockRuleError as exc:
        code = status.HTTP_404_NOT_FOUND if exc.code == "product_not_found" else 422
        raise HTTPException(status_code=code, detail=exc.message) from None
    return ProductsLegacyFbsLimitsResetOut(updated_count=updated_count)
