"""Tenant-scoped service warehouse used only for defective return stock."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

DEFECT_WAREHOUSE_CODE = "__DEFECT__"
DEFECT_WAREHOUSE_NAME = "Склад брака"
DEFECT_LOCATION_CODE = "__DEFECT__"

P = ParamSpec("P")
T = TypeVar("T")


def defect_service_write(
    operation: Callable[Concatenate[AsyncSession, uuid.UUID, P], Awaitable[T]],
) -> Callable[Concatenate[AsyncSession, uuid.UUID, P], Awaitable[T]]:
    """Grant defect writes only within a service call; no permission survives it.

    The savepoint restores PostgreSQL's transaction-local setting on exceptions.
    Pending caller writes are flushed before granting the capability.
    """
    @wraps(operation)
    async def wrapped(session: AsyncSession, tenant_id: uuid.UUID,
                      *args: P.args, **kwargs: P.kwargs) -> T:
        await session.flush()
        connection = await session.connection()
        postgres = session.get_bind().dialect.name == "postgresql"
        info = await connection.run_sync(lambda conn: conn.info)
        previous = info.get("wms_defect_tenant")
        try:
            async with session.begin_nested():
                if postgres:
                    old = await session.scalar(text(
                        "SELECT current_setting('wms.defect_tenant', true)"))
                    await session.execute(text(
                        "SELECT set_config('wms.defect_tenant', :tenant, true)"),
                        {"tenant": str(tenant_id)})
                else:
                    info["wms_defect_tenant"] = tenant_id.hex
                result = await operation(session, tenant_id, *args, **kwargs)
                await session.flush()
                if postgres:
                    await session.execute(text(
                        "SELECT set_config('wms.defect_tenant', :old, true)"), {"old": old or ""})
                return result
        finally:
            info["wms_defect_tenant"] = previous

    return cast(Callable[Concatenate[AsyncSession, uuid.UUID, P], Awaitable[T]], wrapped)


@defect_service_write
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
