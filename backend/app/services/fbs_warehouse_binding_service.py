"""CRUD for FBS seller WB warehouse → WMS warehouse bindings."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services.catalog_service import get_warehouse

AUTO_FBS_WAREHOUSE_CODE_PREFIX = "fbs-wb"


class FbsWarehouseBindingError(Exception):
    def __init__(self, code: str, context: dict | None = None, message: str | None = None) -> None:
        self.code = code
        self.context = context
        self.message = message
        super().__init__(code)


def is_auto_fbs_wms_warehouse(warehouse: Warehouse) -> bool:
    return warehouse.code.startswith(f"{AUTO_FBS_WAREHOUSE_CODE_PREFIX}-") or (
        warehouse.name.startswith("FBS WB ")
    )


async def _seller_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> Seller | None:
    seller = await session.get(Seller, seller_id)
    if seller is None or seller.tenant_id != tenant_id:
        return None
    return seller


async def _get_binding_row(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    *,
    for_update: bool = False,
) -> FbsWarehouseBinding | None:
    stmt = select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == tenant_id,
        FbsWarehouseBinding.seller_id == seller_id,
        FbsWarehouseBinding.wb_warehouse_id == wb_warehouse_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def _has_active_fbs_reservations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> bool:
    stmt = (
        select(FbsOrderReservation.id)
        .join(FbsOrder, FbsOrderReservation.fbs_order_id == FbsOrder.id)
        .where(
            FbsOrderReservation.tenant_id == tenant_id,
            FbsOrderReservation.warehouse_id == warehouse_id,
            FbsOrder.seller_id == seller_id,
        )
        .limit(1)
        .with_for_update()
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def list_bindings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
) -> list[FbsWarehouseBinding]:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    stmt = (
        select(FbsWarehouseBinding)
        .where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
        )
        .order_by(FbsWarehouseBinding.wb_warehouse_id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    if wb_warehouse_id <= 0:
        raise FbsWarehouseBindingError("invalid_wb_warehouse_id")
    row = await _get_binding_row(session, tenant_id, seller_id, wb_warehouse_id)
    if row is None:
        raise FbsWarehouseBindingError("binding_not_found")
    return row


async def upsert_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
    *,
    wms_warehouse_id: uuid.UUID,
    stock_sync_enabled: bool,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    if wb_warehouse_id <= 0:
        raise FbsWarehouseBindingError("invalid_wb_warehouse_id")
    warehouse = await get_warehouse(session, tenant_id, wms_warehouse_id)
    if warehouse is None:
        raise FbsWarehouseBindingError("warehouse_not_found")
    if not warehouse.is_operational:
        raise FbsWarehouseBindingError("warehouse_not_operational")

    existing = await _get_binding_row(
        session, tenant_id, seller_id, wb_warehouse_id, for_update=True
    )
    if existing is not None:
        old_wms = existing.wms_warehouse_id
        if old_wms != wms_warehouse_id:
            if await _has_active_fbs_reservations(
                session, tenant_id, seller_id, old_wms
            ):
                raise FbsWarehouseBindingError("active_fbs_reservations")
            existing.wms_warehouse_id = wms_warehouse_id
        existing.stock_sync_enabled = stock_sync_enabled
        existing.is_active = True
        await session.commit()
        await session.refresh(existing)
        return existing

    row = FbsWarehouseBinding(
        tenant_id=tenant_id,
        seller_id=seller_id,
        wb_warehouse_id=wb_warehouse_id,
        wms_warehouse_id=wms_warehouse_id,
        stock_sync_enabled=stock_sync_enabled,
        is_active=True,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        # One WMS warehouse binding many WB warehouses is now allowed (pool 1,
        # item 5 of docs/agent-orders/HANDOFF-POLISH.md) — the DB no longer has
        # a uniqueness constraint on (seller_id, wms_warehouse_id). The only
        # constraint that can still fire on this insert is
        # uq_fbs_warehouse_bindings_seller_wb_warehouse, from a concurrent
        # duplicate PUT racing on the same brand-new wb_warehouse_id.
        await session.rollback()
        raise FbsWarehouseBindingError("wb_warehouse_already_bound") from exc
    await session.refresh(row)
    return row


async def disable_binding(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    wb_warehouse_id: int,
) -> FbsWarehouseBinding:
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    row = await _get_binding_row(
        session, tenant_id, seller_id, wb_warehouse_id, for_update=True
    )
    if row is None:
        raise FbsWarehouseBindingError("binding_not_found")
    if await _has_active_fbs_reservations(
        session, tenant_id, seller_id, row.wms_warehouse_id
    ):
        raise FbsWarehouseBindingError("active_fbs_reservations")
    row.is_active = False
    await session.commit()
    await session.refresh(row)
    return row


async def set_binding_stock_pool_quantity(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    binding_id: uuid.UUID,
    product_id: uuid.UUID,
    quantity: int,
    *,
    updated_by: uuid.UUID | None = None,
) -> FbsBindingStockPool:
    """Set manual FBS stock pool quantity allocated to a specific WB warehouse.

    The operator manually decides how to distribute the product's FBS pool across
    WB warehouses. This function validates that the total quantity allocated across
    all bindings of this product for this seller does not exceed product.fbs_stock_limit
    (where None is treated as 0).
    """
    if await _seller_in_tenant(session, tenant_id, seller_id) is None:
        raise FbsWarehouseBindingError("seller_not_found")
    if quantity < 0:
        raise FbsWarehouseBindingError("invalid_quantity")

    binding = await session.get(FbsWarehouseBinding, binding_id)
    if binding is None or binding.tenant_id != tenant_id or binding.seller_id != seller_id:
        raise FbsWarehouseBindingError("binding_not_found")

    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id or product.seller_id != seller_id:
        raise FbsWarehouseBindingError("product_not_found")

    limit = int(product.fbs_stock_limit) if product.fbs_stock_limit is not None else 0

    # Sum of quantities allocated to other bindings of this product for this seller
    # (excluding the current binding_id).
    stmt = (
        select(func.coalesce(func.sum(FbsBindingStockPool.quantity), 0))
        .select_from(FbsBindingStockPool)
        .join(FbsWarehouseBinding, FbsBindingStockPool.binding_id == FbsWarehouseBinding.id)
        .where(
            FbsBindingStockPool.product_id == product_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsBindingStockPool.binding_id != binding_id,
        )
    )
    res = await session.execute(stmt)
    allocated_elsewhere = int(res.scalar_one())

    if allocated_elsewhere + quantity > limit:
        available = max(limit - allocated_elsewhere, 0)
        raise FbsWarehouseBindingError(
            "pool_quota_exceeded",
            context={
                "limit": limit,
                "allocated_elsewhere": allocated_elsewhere,
                "requested": quantity,
            },
            message=(
                f"Пул {limit}, на другие склады уже разложено {allocated_elsewhere}, "
                f"свободно {available}. Запрошено {quantity} — уменьшите количество."
            ),
        )

    # Get or create the stock pool entry for this binding and product.
    stmt_existing = select(FbsBindingStockPool).where(
        FbsBindingStockPool.binding_id == binding_id,
        FbsBindingStockPool.product_id == product_id,
    )
    existing = (await session.execute(stmt_existing)).scalar_one_or_none()
    if existing is not None:
        existing.quantity = quantity
        existing.updated_by = updated_by
    else:
        existing = FbsBindingStockPool(
            tenant_id=tenant_id,
            binding_id=binding_id,
            product_id=product_id,
            quantity=quantity,
            updated_by=updated_by,
        )
        session.add(existing)
    await session.commit()
    await session.refresh(existing)
    return existing


async def get_binding_stock_pool_summary(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    product_id: uuid.UUID,
) -> dict:
    """Get FBS stock pool summary: limit, total allocated, available, and per-binding breakdown.

    Returns a dictionary with:
    - limit: the product's fbs_stock_limit (0 if None)
    - allocated_total: total quantity allocated across all bindings
    - available: remaining capacity (limit - allocated_total, never negative)
    - by_binding: dict of {binding_id -> quantity} for all bindings of this product
    """
    product = await session.get(Product, product_id)
    if product is None or product.tenant_id != tenant_id or product.seller_id != seller_id:
        raise FbsWarehouseBindingError("product_not_found")
    limit = int(product.fbs_stock_limit) if product.fbs_stock_limit is not None else 0

    stmt = (
        select(FbsBindingStockPool.binding_id, FbsBindingStockPool.quantity)
        .select_from(FbsBindingStockPool)
        .join(FbsWarehouseBinding, FbsBindingStockPool.binding_id == FbsWarehouseBinding.id)
        .where(
            FbsBindingStockPool.product_id == product_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.tenant_id == tenant_id,
        )
    )
    res = await session.execute(stmt)
    rows = res.all()
    allocated_total = sum(int(row.quantity) for row in rows)
    return {
        "limit": limit,
        "allocated_total": allocated_total,
        "available": max(limit - allocated_total, 0),
        "by_binding": {row.binding_id: int(row.quantity) for row in rows},
    }
