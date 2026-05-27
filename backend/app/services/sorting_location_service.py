"""Системная ячейка «Сортировка» на складе — буфер до разкладки по хранению."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_location import StorageLocation
from app.services.catalog_service import get_warehouse

# Код в БД; в UI показываем SORTING_LOCATION_LABEL.
SORTING_LOCATION_CODE = "__SORTING__"
SORTING_LOCATION_LABEL = "Сортировка"


def is_sorting_location(loc: StorageLocation) -> bool:
    return loc.code == SORTING_LOCATION_CODE


async def get_sorting_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> StorageLocation | None:
    stmt = select(StorageLocation).where(
        StorageLocation.tenant_id == tenant_id,
        StorageLocation.warehouse_id == warehouse_id,
        StorageLocation.code == SORTING_LOCATION_CODE,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def get_or_create_sorting_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> StorageLocation:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        msg = "warehouse not found"
        raise ValueError(msg)
    existing = await get_sorting_location(session, tenant_id, warehouse_id)
    if existing is not None:
        return existing
    loc = StorageLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code=SORTING_LOCATION_CODE,
        barcode=f"SORT-{warehouse_id.hex[:12].upper()}",
    )
    session.add(loc)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        again = await get_sorting_location(session, tenant_id, warehouse_id)
        if again is None:
            raise
        return again
    return loc
