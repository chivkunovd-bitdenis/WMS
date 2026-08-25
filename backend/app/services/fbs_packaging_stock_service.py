from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service as inv_svc
from app.services import sorting_location_service as sorting_loc_svc


async def insufficient_stock_message(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    line: PackagingTaskLine,
) -> str:
    """Name the missing product and the physical location for the operator."""
    product = await session.get(Product, line.product_id)
    location = await session.get(StorageLocation, line.storage_location_id)
    product_label = (
        f"«{product.name}» (арт. {product.sku_code})" if product is not None else "товара"
    )
    if location is not None and sorting_loc_svc.is_sorting_location(location):
        location_label = f"ячейке сортировки склада (код {location.barcode})"
    elif location is not None:
        location_label = f"ячейке «{location.code}»"
    else:
        location_label = "указанной ячейке"
    on_hand = await session.scalar(
        select(InventoryBalance.quantity).where(
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == line.product_id,
            InventoryBalance.storage_location_id == line.storage_location_id,
        )
    )
    return (
        f"Недостаточно {product_label} в {location_label}: по остатку числится "
        f"{int(on_hand or 0)} шт., а нужна как минимум 1. Проверьте фактическое наличие "
        "товара на складе — возможно, он лежит в другой ячейке или ещё не подобран."
    )


async def try_deduct_from_alternative_sorting_location(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    primary_location_id: uuid.UUID,
) -> tuple[bool, str | None]:
    """Deduct one unit from another warehouse sorting cell of the same tenant."""
    primary_location = await session.get(StorageLocation, primary_location_id)
    if primary_location is None:
        return False, None
    sorting_locations = await session.execute(
        select(
            StorageLocation.id,
            StorageLocation.barcode,
            InventoryBalance.quantity,
        )
        .join(
            InventoryBalance,
            InventoryBalance.storage_location_id == StorageLocation.id,
        )
        .where(
            StorageLocation.tenant_id == tenant_id,
            StorageLocation.warehouse_id != primary_location.warehouse_id,
            StorageLocation.code == sorting_loc_svc.SORTING_LOCATION_CODE,
            InventoryBalance.tenant_id == tenant_id,
            InventoryBalance.product_id == product_id,
            InventoryBalance.quantity > 0,
        )
        .order_by(InventoryBalance.quantity.desc())
    )
    for alternative_id, alternative_barcode, _ in sorting_locations.all():
        try:
            await inv_svc.apply_packaging_convert(
                session,
                tenant_id=tenant_id,
                product_id=product_id,
                storage_location_id=alternative_id,
                quantity=1,
                require_unpacked=False,
            )
            return True, str(alternative_barcode)
        except ValueError as exc:
            if str(exc) != "insufficient_stock":
                raise
    return False, None
