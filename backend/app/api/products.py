from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import (
    CatalogError,
    create_product,
    list_products,
    volume_liters_from_mm,
)

router = APIRouter(prefix="/products", tags=["products"])


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku_code: str = Field(min_length=1, max_length=128)
    length_mm: int = Field(ge=1, le=10_000_000)
    width_mm: int = Field(ge=1, le=10_000_000)
    height_mm: int = Field(ge=1, le=10_000_000)


class ProductOut(BaseModel):
    id: str
    name: str
    sku_code: str
    length_mm: int
    width_mm: int
    height_mm: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def volume_liters(self) -> float:
        return volume_liters_from_mm(self.length_mm, self.width_mm, self.height_mm)


@router.get("", response_model=list[ProductOut])
async def get_products(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProductOut]:
    rows = await list_products(session, user.tenant_id)
    return [
        ProductOut(
            id=str(p.id),
            name=p.name,
            sku_code=p.sku_code,
            length_mm=p.length_mm,
            width_mm=p.width_mm,
            height_mm=p.height_mm,
        )
        for p in rows
    ]


@router.post("", response_model=ProductOut)
async def post_product(
    body: ProductCreate,
    user: Annotated[User, Depends(get_current_user)],
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
        )
    except CatalogError as exc:
        if exc.code == "invalid_dimensions":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_dimensions",
            ) from None
        if exc.code == "sku_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="sku_taken",
            ) from None
        raise
    return ProductOut(
        id=str(p.id),
        name=p.name,
        sku_code=p.sku_code,
        length_mm=p.length_mm,
        width_mm=p.width_mm,
        height_mm=p.height_mm,
    )
