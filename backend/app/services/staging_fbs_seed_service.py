"""Local synthetic FBS orders for the three explicitly prepared staging tenants."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_NEW,
    MAPPING_STATUS_MAPPED,
    RESERVE_STATUS_NO_STOCK,
    RESERVE_STATUS_RESERVED,
    FbsOrder,
    FbsOrderReservation,
)
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.defect_warehouse_service import DEFECT_WAREHOUSE_CODE
from app.services.fbs_stock_availability_service import organization_stock_totals_by_product
from app.services.sorting_location_service import SORTING_LOCATION_CODE

logger = logging.getLogger(__name__)
MOSCOW = ZoneInfo("Europe/Moscow")
STAGING_FBS_TENANT_SLUGS = ("stage-artmaks", "stage-imperiya-lvova", "stage-avpack")
ORDERS_PER_RUN = 10


def staging_fbs_slot_key(slot_hour: int, *, now: datetime | None = None) -> str:
    """Most recent occurrence of one of the two scheduled Moscow hours."""
    if slot_hour not in (9, 18):
        raise ValueError("staging FBS slot hour must be 9 or 18")
    current = (now or datetime.now(MOSCOW)).astimezone(MOSCOW)
    slot = current.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
    if slot > current:
        slot -= timedelta(days=1)
    return slot.isoformat()


async def _seed_tenant(
    session: AsyncSession, tenant: Tenant, slot: datetime
) -> int:
    # Lock the tenant for the entire batch; duplicate workers wait, then see the
    # ten committed deterministic IDs. No separate batch table is necessary.
    await session.execute(select(Tenant.id).where(Tenant.id == tenant.id).with_for_update())
    order_ids = [
        uuid.uuid5(tenant.id, f"staging-fbs:{slot.isoformat()}:{index}")
        for index in range(ORDERS_PER_RUN)
    ]
    existing = set((
        await session.scalars(select(FbsOrder.id).where(
            FbsOrder.tenant_id == tenant.id, FbsOrder.id.in_(order_ids)
        ))
    ).all())
    missing = [
        (index, order_id)
        for index, order_id in enumerate(order_ids)
        if order_id not in existing
    ]
    needed = len(missing)
    if not needed:
        logger.info(
            "staging FBS slot already present: tenant=%s count=%s", tenant.slug, len(existing)
        )
        return 0

    bindings = list((await session.scalars(
        select(FbsWarehouseBinding)
        .join(Seller, Seller.id == FbsWarehouseBinding.seller_id)
        .join(Warehouse, Warehouse.id == FbsWarehouseBinding.wms_warehouse_id)
        .where(
            FbsWarehouseBinding.tenant_id == tenant.id,
            Seller.tenant_id == tenant.id,
            Warehouse.tenant_id == tenant.id,
            FbsWarehouseBinding.marketplace == "wb",
            FbsWarehouseBinding.is_active.is_(True),
            FbsWarehouseBinding.served.is_(True),
            Warehouse.is_operational.is_(True),
            func.lower(Warehouse.code) != DEFECT_WAREHOUSE_CODE.lower(),
        )
        .order_by(FbsWarehouseBinding.seller_id, FbsWarehouseBinding.id)
    )).all())
    if not bindings:
        raise RuntimeError(f"staging FBS tenant has no active WB bindings: {tenant.slug}")

    products = list((await session.scalars(
        select(Product)
        .where(
            Product.tenant_id == tenant.id,
            Product.seller_id.in_({binding.seller_id for binding in bindings}),
            Product.wb_barcode.is_not(None),
            Product.wb_barcode != "",
        )
        .order_by(Product.id)
    )).all())
    if not products:
        raise RuntimeError(f"staging FBS tenant has no WB products: {tenant.slug}")

    # Count actual pickable units on the bound warehouses. Sorting and deleted
    # locations cannot provide a fresh operator picking scenario.
    stock_stmt = (
        select(Product, StorageLocation.warehouse_id, func.sum(InventoryBalance.quantity))
        .join(InventoryBalance, InventoryBalance.product_id == Product.id)
        .join(StorageLocation, StorageLocation.id == InventoryBalance.storage_location_id)
        .where(
            Product.tenant_id == tenant.id,
            InventoryBalance.tenant_id == tenant.id,
            StorageLocation.tenant_id == tenant.id,
            Product.seller_id.in_({binding.seller_id for binding in bindings}),
            Product.wb_barcode.is_not(None),
            Product.wb_barcode != "",
            StorageLocation.warehouse_id.in_({binding.wms_warehouse_id for binding in bindings}),
            StorageLocation.deleted_at.is_(None),
            StorageLocation.code != SORTING_LOCATION_CODE,
        )
        .group_by(Product.id, StorageLocation.warehouse_id)
        .having(func.sum(InventoryBalance.quantity) > 0)
        .order_by(Product.id, StorageLocation.warehouse_id)
    )
    stock_rows = (await session.execute(stock_stmt)).all()
    # The full catalog can exceed PostgreSQL's 65,535 bind parameter limit in
    # organization_stock_totals_by_product. Only products with pickable stock
    # need an availability calculation; every other candidate is no_stock.
    stock_product_ids = {product.id for product, _, _ in stock_rows}
    await session.execute(
        select(Product.id).where(
            Product.tenant_id == tenant.id,
            Product.id.in_(stock_product_ids),
        )
        .order_by(Product.id).with_for_update()
    )
    # Re-read quantities after obtaining locks, as picking/shipment may have
    # committed while this run was waiting for another stock operation.
    stock_rows = (
        await session.execute(stock_stmt.where(Product.id.in_(stock_product_ids)))
    ).all()
    totals = await organization_stock_totals_by_product(
        session, tenant.id, sorted(stock_product_ids)
    )
    remaining = {pid: total.available_for_checks for pid, total in totals.items()}
    physical = {
        (product.id, warehouse_id): int(quantity)
        for product, warehouse_id, quantity in stock_rows
    }
    candidates = [
        (product, binding)
        for product in products
        for binding in bindings
        if binding.seller_id == product.seller_id
        and binding.wms_warehouse_id is not None
    ]
    if not candidates:
        raise RuntimeError(f"staging FBS tenant has no mapped WB products: {tenant.slug}")

    plan: list[tuple[Product, FbsWarehouseBinding, bool]] = []
    for index in range(needed):
        available = [
            (product, binding)
            for product, binding in candidates
            if remaining.get(product.id, 0) > 0
            and physical.get((product.id, binding.wms_warehouse_id), 0) > 0
        ]
        if available:
            product, binding = available[index % len(available)]
            remaining[product.id] -= 1
            stock_key = (product.id, binding.wms_warehouse_id)
            physical[stock_key] -= 1
            plan.append((product, binding, True))
        else:
            # Real marketplace imports still create visible orders when local
            # inventory is short; preserve ten fresh staging examples and let
            # operators see the existing no_stock state instead of skipping the run.
            product, binding = candidates[index % len(candidates)]
            plan.append((product, binding, False))

    reserved_count = sum(1 for _, _, reserved in plan if reserved)
    for (index, order_id), (product, binding, reserved) in zip(missing, plan, strict=True):
        order = FbsOrder(
            id=order_id, tenant_id=tenant.id, seller_id=binding.seller_id,
            warehouse_id=binding.wms_warehouse_id, product_id=product.id,
            marketplace="wb",
            external_order_id=f"stage-fbs:{slot:%Y%m%d}:{slot.hour}:{index}",
            # Positive, numeric and safe to represent in JavaScript. A high
            # synthetic range also avoids normal marketplace order numbers.
            wb_order_id=8_000_000_000_000 + order_id.int % 1_000_000_000_000,
            wb_rid=f"stage-{order_id.hex}", wb_nm_id=product.wb_nm_id,
            wb_chrt_id=product.wb_chrt_id, wb_article=product.wb_vendor_code or product.sku_code,
            wb_barcode=product.wb_barcode, wb_warehouse_id=binding.wb_warehouse_id,
            status=FBS_ORDER_STATUS_NEW, wb_status="new", supplier_status="new",
            created_at_wb=slot, deadline_at=slot + timedelta(hours=48),
            mapping_status=MAPPING_STATUS_MAPPED,
            reserve_status=RESERVE_STATUS_RESERVED if reserved else RESERVE_STATUS_NO_STOCK,
            required_meta_json=["sgtin"] if product.requires_honest_sign else [],
        )
        session.add(order)
        await session.flush()
        if reserved:
            # update_fbs_order_reservation also schedules marketplace publication.
            # Write the same reservation model locally without enqueuing HTTP work.
            session.add(FbsOrderReservation(
                tenant_id=tenant.id, fbs_order_id=order_id, product_id=product.id,
                warehouse_id=binding.wms_warehouse_id, quantity=1,
            ))
    await session.flush()
    logger.info(
        "staging FBS batch: tenant=%s slot=%s created=%s reserved=%s no_stock=%s",
        tenant.slug, slot.isoformat(), len(plan), reserved_count, len(plan) - reserved_count,
    )
    return len(plan)


async def seed_staging_fbs_orders(slot_key: str | None = None) -> dict[str, int]:
    """Create ten local orders per prepared tenant and reserve available units."""
    if settings.app_env != "staging":
        return {}
    current = datetime.now(MOSCOW)
    hour = 9 if 9 <= current.hour < 18 else 18
    key = slot_key or staging_fbs_slot_key(hour, now=current)
    slot = datetime.fromisoformat(key)
    if slot.tzinfo is None:
        raise ValueError("staging FBS slot must include its timezone")
    slot = slot.astimezone(MOSCOW)
    if slot.hour not in (9, 18) or slot.minute or slot.second or slot.microsecond:
        raise ValueError("staging FBS slot must be 09:00 or 18:00 Moscow time")
    results: dict[str, int] = {}
    errors: list[Exception] = []
    for slug in STAGING_FBS_TENANT_SLUGS:
        try:
            async with SessionLocal() as session, session.begin():
                tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
                if tenant is None:
                    logger.warning("staging FBS skipped: tenant=%s reason=tenant_missing", slug)
                    continue
                results[slug] = await _seed_tenant(session, tenant, slot)
            logger.info("staging FBS seed: tenant=%s slot=%s created=%s", slug, key, results[slug])
        except Exception as exc:
            logger.error(
                "staging FBS seed failed: tenant=%s slot=%s error_type=%s",
                slug, key, type(exc).__name__,
            )
            errors.append(exc)
    if errors:
        raise errors[0]
    return results
