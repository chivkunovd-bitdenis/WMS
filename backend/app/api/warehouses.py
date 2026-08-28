from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_cells_access, require_fulfillment_admin
from app.db.session import get_db
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import tenant_settings_service as tenant_settings_svc
from app.services.catalog_service import (
    CatalogError,
    create_location,
    create_location_from_rack,
    create_warehouse,
    delete_location,
    delete_warehouse,
    get_warehouse,
    list_racks,
    rename_location,
    rename_warehouse,
    resolve_warehouse_scan,
    suggest_next_location_for_rack,
)
from app.services.catalog_service import (
    list_locations as list_locs_svc,
)
from app.services.catalog_service import (
    list_warehouses as list_wh_svc,
)
from app.services.sorting_location_service import (
    SORTING_LOCATION_LABEL,
    get_or_create_sorting_location,
)

router = APIRouter(prefix="/warehouses", tags=["warehouses"])


async def _require_address_storage(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    if not await tenant_settings_svc.is_address_storage_enabled(session, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="address_storage_disabled",
        )


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class WarehousePatch(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WarehouseOut(BaseModel):
    id: str
    name: str
    code: str
    barcode: str
    is_operational: bool

    model_config = {"from_attributes": False}


class LocationCreate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=64)
    rack_name: str | None = Field(default=None, min_length=1, max_length=32)
    side: int | None = Field(default=None, ge=1, le=2)
    position: int | None = Field(default=None, ge=1, le=9999)


class LocationPatch(BaseModel):
    code: str = Field(min_length=1, max_length=64)


class RackOut(BaseModel):
    name: str


class LocationSuggestOut(BaseModel):
    position: int
    code: str


class LocationOut(BaseModel):
    id: str
    code: str
    warehouse_id: str
    barcode: str


@router.get("", response_model=list[WarehouseOut])
async def list_warehouses(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[WarehouseOut]:
    rows = await list_wh_svc(session, user.tenant_id)
    return [
        WarehouseOut(
            id=str(w.id),
            name=w.name,
            code=w.code,
            barcode=w.barcode,
            is_operational=w.is_operational,
        )
        for w in rows
    ]


@router.post("", response_model=WarehouseOut)
async def post_warehouse(
    body: WarehouseCreate,
    user: Annotated[User, Depends(require_fulfillment_admin)],
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
    return WarehouseOut(
        id=str(w.id), name=w.name, code=w.code, barcode=w.barcode, is_operational=w.is_operational
    )


@router.patch("/{warehouse_id}", response_model=WarehouseOut)
async def patch_warehouse(
    warehouse_id: uuid.UUID,
    body: WarehousePatch,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WarehouseOut:
    try:
        w = await rename_warehouse(
            session,
            user.tenant_id,
            warehouse_id,
            name=body.name,
        )
    except CatalogError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        if exc.code == "invalid_warehouse_name":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_warehouse_name",
            ) from None
        raise
    return WarehouseOut(
        id=str(w.id), name=w.name, code=w.code, barcode=w.barcode, is_operational=w.is_operational
    )


class WarehouseScanOut(BaseModel):
    type: str
    id: str
    warehouse_id: str
    name: str | None = None
    code: str


@router.get("/resolve", response_model=WarehouseScanOut)
async def resolve_scan(
    barcode: Annotated[str, Query(min_length=1)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WarehouseScanOut:
    try:
        kind, item = await resolve_warehouse_scan(session, user.tenant_id, barcode)
    except CatalogError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if exc.code in {"barcode_unknown", "barcode_empty"}
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=exc.code) from None
    if kind == "warehouse" and isinstance(item, Warehouse):
        return WarehouseScanOut(
            type=kind, id=str(item.id), warehouse_id=str(item.id), name=item.name, code=item.code
        )
    assert isinstance(item, StorageLocation)
    await _require_address_storage(session, user.tenant_id)
    return WarehouseScanOut(
        type=kind, id=str(item.id), warehouse_id=str(item.warehouse_id), code=item.code
    )


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_route(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(require_fulfillment_admin)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await delete_warehouse(session, user.tenant_id, warehouse_id)
    except CatalogError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        if exc.code in (
            "warehouse_has_documents",
            "warehouse_has_stock",
            "warehouse_has_locations",
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        raise


@router.get("/{warehouse_id}/sorting-location", response_model=LocationOut)
async def get_sorting_location(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationOut:
    await _require_address_storage(session, user.tenant_id)
    wh = await get_warehouse(session, user.tenant_id, warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="warehouse_not_found",
        )
    loc = await get_or_create_sorting_location(session, user.tenant_id, warehouse_id)
    await session.commit()
    return LocationOut(
        id=str(loc.id),
        code=SORTING_LOCATION_LABEL,
        warehouse_id=str(loc.warehouse_id),
        barcode=loc.barcode,
    )


@router.get("/{warehouse_id}/locations", response_model=list[LocationOut])
async def list_locations(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    exclude_sorting_zone: Annotated[bool, Query()] = False,
) -> list[LocationOut]:
    wh = await get_warehouse(session, user.tenant_id, warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="warehouse_not_found",
        )
    if not await tenant_settings_svc.is_address_storage_enabled(
        session, user.tenant_id
    ):
        return []
    rows = await list_locs_svc(
        session,
        user.tenant_id,
        warehouse_id,
        exclude_sorting_zone=exclude_sorting_zone,
    )
    return [
        LocationOut(
            id=str(x.id),
            code=x.code,
            warehouse_id=str(x.warehouse_id),
            barcode=x.barcode,
        )
        for x in rows
    ]


@router.post("/{warehouse_id}/locations", response_model=LocationOut)
async def post_location(
    warehouse_id: uuid.UUID,
    body: LocationCreate,
    user: Annotated[User, Depends(require_cells_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationOut:
    await _require_address_storage(session, user.tenant_id)
    try:
        if body.rack_name is not None:
            if body.side is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="side_required",
                )
            loc = await create_location_from_rack(
                session,
                user.tenant_id,
                warehouse_id,
                rack_name=body.rack_name,
                side=body.side,
                position=body.position,
            )
        else:
            if body.code is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="code_required",
                )
            loc = await create_location(session, user.tenant_id, warehouse_id, code=body.code)
    except CatalogError as exc:
        if exc.code == "warehouse_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="warehouse_not_found",
            ) from None
        if exc.code == "invalid_side":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_side",
            ) from None
        if exc.code == "invalid_position":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_position",
            ) from None
        if exc.code == "location_code_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="location_code_taken",
            ) from None
        raise
    return LocationOut(
        id=str(loc.id),
        code=loc.code,
        warehouse_id=str(loc.warehouse_id),
        barcode=loc.barcode,
    )


@router.patch("/{warehouse_id}/locations/{location_id}", response_model=LocationOut)
async def patch_location(
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    body: LocationPatch,
    user: Annotated[User, Depends(require_cells_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LocationOut:
    await _require_address_storage(session, user.tenant_id)
    try:
        loc = await rename_location(
            session,
            user.tenant_id,
            warehouse_id,
            location_id,
            code=body.code,
        )
    except CatalogError as exc:
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
            ) from None
        if exc.code == "system_location_locked":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="system_location_locked",
            ) from None
        if exc.code == "invalid_location_code":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_location_code",
            ) from None
        if exc.code == "location_code_taken":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="location_code_taken",
            ) from None
        raise
    return LocationOut(
        id=str(loc.id),
        code=loc.code,
        warehouse_id=str(loc.warehouse_id),
        barcode=loc.barcode,
    )


@router.delete(
    "/{warehouse_id}/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_location_route(
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    user: Annotated[User, Depends(require_cells_access)],
    session: Annotated[AsyncSession, Depends(get_db)],
    move_stock_to: Annotated[str | None, Query()] = None,
) -> None:
    await _require_address_storage(session, user.tenant_id)
    try:
        await delete_location(
            session,
            user.tenant_id,
            warehouse_id,
            location_id,
            move_stock_to=move_stock_to,
        )
    except CatalogError as exc:
        if exc.code == "location_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="location_not_found",
            ) from None
        if exc.code in ("system_location_locked", "location_has_stock"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=exc.code,
            ) from None
        raise


@router.get("/{warehouse_id}/racks", response_model=list[RackOut])
async def get_racks(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[RackOut]:
    await _require_address_storage(session, user.tenant_id)
    wh = await get_warehouse(session, user.tenant_id, warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="warehouse_not_found",
        )
    rows = await list_racks(session, user.tenant_id, warehouse_id)
    return [RackOut(name=x.name) for x in rows]


@router.get("/{warehouse_id}/locations/suggest", response_model=LocationSuggestOut)
async def suggest_location(
    warehouse_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    rack_name: str = Query(min_length=1, max_length=32),
    side: int = Query(ge=1, le=2),
) -> LocationSuggestOut:
    await _require_address_storage(session, user.tenant_id)
    wh = await get_warehouse(session, user.tenant_id, warehouse_id)
    if wh is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="warehouse_not_found",
        )
    try:
        pos, code = await suggest_next_location_for_rack(
            session,
            user.tenant_id,
            warehouse_id,
            rack_name=rack_name,
            side=side,
        )
    except CatalogError as exc:
        if exc.code == "invalid_side":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_side",
            ) from None
        raise
    return LocationSuggestOut(position=pos, code=code)
