from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.catalog_service import (
    CatalogError,
    create_location,
    create_warehouse,
    get_warehouse,
)
from app.services.catalog_service import (
    list_locations as list_locs_svc,
)
from app.services.catalog_service import (
    list_warehouses as list_wh_svc,
)

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class WarehouseOut(BaseModel):
    id: str
    name: str
    code: str

    model_config = {"from_attributes": False}


class LocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class LocationOut(BaseModel):
    id: str
    code: str
    warehouse_id: str


@router.get("", response_model=list[WarehouseOut])
async def list_warehouses(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WarehouseOut]:
    rows = await list_wh_svc(session, user.tenant_id)
    return [
        WarehouseOut(id=str(w.id), name=w.name, code=w.code) for w in rows
    ]


@router.post("", response_model=WarehouseOut)
async def post_warehouse(
    body: WarehouseCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WarehouseOut:
    try:
        w = await create_warehouse(
            session,
            user.tenant_id,
            name=body.name,
            code=body.code,
        )
    except CatalogError as exc:
        if exc.code != "warehouse_code_taken":
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="warehouse_code_taken",
        ) from None
    return WarehouseOut(id=str(w.id), name=w.name, code=w.code)


@router.get("/{warehouse_id}/locations", response_model=list[LocationOut])
async def list_locations(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[LocationOut]:
    wh = await get_warehouse(session, user.tenant_id, warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="warehouse_not_found",
        )
    rows = await list_locs_svc(session, user.tenant_id, warehouse_id)
    return [
        LocationOut(
            id=str(x.id), code=x.code, warehouse_id=str(x.warehouse_id)
        )
        for x in rows
    ]


@router.post("/{warehouse_id}/locations", response_model=LocationOut)
async def post_location(
    warehouse_id: uuid.UUID,
    body: LocationCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationOut:
    try:
        loc = await create_location(
            session, user.tenant_id, warehouse_id, code=body.code
        )
    except CatalogError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        if exc.code == "location_code_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="location_code_taken",
            ) from None
        raise
    return LocationOut(
        id=str(loc.id), code=loc.code, warehouse_id=str(loc.warehouse_id)
    )
