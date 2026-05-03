from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.seller import Seller
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
    # CODE128 supports alphanumeric; keep it short and unique.
    # Persisted in DB and used for printing the barcode label.
    for _ in range(5):
        loc = StorageLocation(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            code=code.strip(),
            barcode=f"LOC-{uuid.uuid4().hex[:12].upper()}",
        )
        session.add(loc)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            msg = str(exc.orig).lower() if exc.orig is not None else str(exc).lower()
            if "uq_storage_locations_wh_code" in msg or "storage_locations_wh_code" in msg:
                raise CatalogError("location_code_taken") from exc
            if "uq_storage_locations_tenant_barcode" in msg or "tenant_barcode" in msg:
                # Retry barcode collision (extremely unlikely).
                continue
            raise
        await session.refresh(loc)
        return loc
    raise CatalogError("barcode_collision")


def volume_liters_from_mm(l_mm: int, w_mm: int, h_mm: int) -> float:
    """Объём в литрах: габариты в мм → мм³ / 10⁶ = литры."""
    return float(l_mm * w_mm * h_mm) / 1_000_000.0


async def list_products(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .options(selectinload(Product.seller))
        .order_by(Product.sku_code)
    )
    if seller_id is not None:
        stmt = stmt.where(Product.seller_id == seller_id)
    res = await session.execute(stmt)
    return list(res.scalars().unique().all())


async def list_sellers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    seller_id: uuid.UUID | None = None,
) -> list[Seller]:
    stmt = select(Seller).where(Seller.tenant_id == tenant_id).order_by(Seller.name)
    if seller_id is not None:
        stmt = stmt.where(Seller.id == seller_id)
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def create_seller(
    session: AsyncSession, tenant_id: uuid.UUID, *, name: str
) -> Seller:
    s = Seller(tenant_id=tenant_id, name=name.strip())
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


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
    if seller_id is not None:
        sel = await session.get(Seller, seller_id)
        if sel is None or sel.tenant_id != tenant_id:
            raise CatalogError("seller_not_found")
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
