"""Tenant-scoped service warehouse used only for defective return stock."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

DEFECT_WAREHOUSE_CODE = "__DEFECT__"
DEFECT_WAREHOUSE_NAME = "Склад брака"
DEFECT_LOCATION_CODE = "__DEFECT__"


async def get_or_create_defect_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> StorageLocation:
    existing = await session.scalar(
        select(StorageLocation)
        .join(Warehouse, Warehouse.id == StorageLocation.warehouse_id)
        .where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.code == DEFECT_WAREHOUSE_CODE,
            StorageLocation.code == DEFECT_LOCATION_CODE,
        )
    )
    if existing is not None:
        return existing

    warehouse = await session.scalar(
        select(Warehouse).where(
            Warehouse.tenant_id == tenant_id,
            Warehouse.code == DEFECT_WAREHOUSE_CODE,
        )
    )
    if warehouse is None:
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name=DEFECT_WAREHOUSE_NAME,
            code=DEFECT_WAREHOUSE_CODE,
            is_operational=False,
            barcode=f"DEFECT-WH-{tenant_id.hex.upper()}",
        )
        session.add(warehouse)
        await session.flush()

    location = StorageLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse.id,
        code=DEFECT_LOCATION_CODE,
        barcode=f"DEFECT-{tenant_id.hex.upper()}",
    )
    session.add(location)
    await session.flush()
    return location
