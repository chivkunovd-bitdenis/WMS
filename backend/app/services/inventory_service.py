from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.storage_location import StorageLocation


async def list_balances_at_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    storage_location_id: uuid.UUID,
) -> list[tuple[InventoryBalance, Product]] | None:
    loc = await session.get(StorageLocation, storage_location_id)
    if loc is None or loc.tenant_id != tenant_id:
        return None
    stmt = (
        select(InventoryBalance, Product)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.storage_location_id == storage_location_id,
        )
        .order_by(Product.sku_code)
    )
    res = await session.execute(stmt)
    return [(b, p) for b, p in res.all()]
