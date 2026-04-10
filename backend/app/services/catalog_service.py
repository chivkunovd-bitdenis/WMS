from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse


class CatalogError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def list_warehouses(session: AsyncSession, tenant_id: uuid.UUID) -> list[Warehouse]:
    stmt = (
        select(Warehouse)
        .where(Warehouse.tenant_id == tenant_id)
        .order_by(Warehouse.name)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, *, name: str, code: str
) -> Warehouse:
    wh = Warehouse(tenant_id=tenant_id, name=name.strip(), code=code.strip().lower())
    session.add(wh)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise CatalogError("warehouse_code_taken") from exc
    await session.refresh(wh)
    return wh


async def get_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse | None:
    wh = await session.get(Warehouse, warehouse_id)
    if wh is None or wh.tenant_id != tenant_id:
        return None
    return wh


async def get_storage_location_in_warehouse(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
) -> StorageLocation | None:
    loc = await session.get(StorageLocation, location_id)
    if (
        loc is None
        or loc.tenant_id != tenant_id
        or loc.warehouse_id != warehouse_id
    ):
        return None
    return loc


async def list_locations(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> list[StorageLocation]:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        return []
    stmt = (
        select(StorageLocation)
        .where(
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.tenant_id == tenant_id,
        )
        .order_by(StorageLocation.code)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    *,
    code: str,
) -> StorageLocation:
    wh = await get_warehouse(session, tenant_id, warehouse_id)
    if wh is None:
        raise CatalogError("warehouse_not_found")
    loc = StorageLocation(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        code=code.strip(),
    )
    session.add(loc)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise CatalogError("location_code_taken") from exc
    await session.refresh(loc)
    return loc


def volume_liters_from_mm(l_mm: int, w_mm: int, h_mm: int) -> float:
    """Объём в литрах: габариты в мм → мм³ / 10⁶ = литры."""
    return float(l_mm * w_mm * h_mm) / 1_000_000.0


async def list_products(session: AsyncSession, tenant_id: uuid.UUID) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .order_by(Product.sku_code)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    sku_code: str,
    length_mm: int,
    width_mm: int,
    height_mm: int,
    seller_id: uuid.UUID | None = None,
) -> Product:
    if min(length_mm, width_mm, height_mm) <= 0:
        raise CatalogError("invalid_dimensions")
    p = Product(
        tenant_id=tenant_id,
        seller_id=seller_id,
        name=name.strip(),
        sku_code=sku_code.strip(),
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
    )
    session.add(p)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise CatalogError("sku_taken") from exc
    await session.refresh(p)
    return p
