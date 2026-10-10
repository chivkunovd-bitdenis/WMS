"""Отсев чужих WB-заказов до записи в локальную FBS-базу."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.services.wb_order_price_service import WB_ORDERS_SOURCE, capture_wb_price_snapshot


@dataclass
class FbsOrderImportStats:
    received: int = 0
    upserted: int = 0
    created: int = 0
    skipped_unserved: int = 0


def _warehouse_id(row: dict[str, Any]) -> int | None:
    value = row.get("warehouseId")
    return int(value) if value is not None else None


async def import_wb_order_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    rows: list[dict[str, Any]],
    stats: FbsOrderImportStats,
    *,
    price_source: str = WB_ORDERS_SOURCE,
) -> None:
    """Импортировать только заказы явно обслуживаемых WB-складов."""
    from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row

    warehouse_ids = {
        warehouse_id for row in rows if (warehouse_id := _warehouse_id(row)) is not None
    }
    scopes: dict[int, bool] = {}
    if warehouse_ids:
        stmt = select(FbsWarehouseBinding).where(
            FbsWarehouseBinding.tenant_id == tenant_id,
            FbsWarehouseBinding.seller_id == seller_id,
            FbsWarehouseBinding.marketplace == "wb",
            FbsWarehouseBinding.wb_warehouse_id.in_(warehouse_ids),
        )
        scopes = {
            int(binding.wb_warehouse_id): bool(binding.is_active and binding.served)
            for binding in (await session.execute(stmt)).scalars().all()
        }

    from app.models.fbs_order import (
        FbsOrder,
        FbsOrderProduct,
        FbsOrderProductReservation,
        FbsOrderReservation,
    )
    from app.services import inventory_service, wb_marketplace_orders_service
    from app.services.fbs_packaging_integration_service import lock_order_batch_packaging_rows

    existing_ids = list((await session.scalars(select(FbsOrder.id).where(
        FbsOrder.tenant_id == tenant_id, FbsOrder.seller_id == seller_id,
        FbsOrder.wb_order_id.in_([
            int(row["id"]) for row in rows
            if row.get("id") is not None
            and (warehouse_id := _warehouse_id(row)) is not None
            and scopes.get(warehouse_id) is True
        ]),
    ))).all())
    await lock_order_batch_packaging_rows(session, tenant_id, existing_ids)
    # Historical fulfilled orders still need price evidence after a warehouse binding
    # becomes inactive. This does not import unserved orders or change their workflow.
    known_order_rows = list((await session.scalars(
        select(FbsOrder).where(
        FbsOrder.tenant_id == tenant_id, FbsOrder.seller_id == seller_id,
        FbsOrder.marketplace == "wb", FbsOrder.wb_order_id.in_([
            int(row["id"]) for row in rows if row.get("id") is not None
        ]),
    ))).all())
    known_orders = {order.wb_order_id: order.id for order in known_order_rows}
    known_orders_by_wb_id = {order.wb_order_id: order for order in known_order_rows}

    # Resolve this transaction's complete stock-lock set before the first
    # per-order reservation. Reservation helpers keep their own row locks until
    # commit, so processing rows in provider order can otherwise invert the
    # order across imported orders.
    stock_product_ids: set[uuid.UUID] = set()
    affected_order_ids: set[uuid.UUID] = set()
    for row in rows:
        warehouse_id = _warehouse_id(row)
        if (
            row.get("id") is None
            or warehouse_id is None
            or scopes.get(warehouse_id) is not True
        ):
            continue
        existing = known_orders_by_wb_id.get(int(row["id"]))
        if existing is not None:
            affected_order_ids.add(existing.id)
            if existing.product_id is not None:
                stock_product_ids.add(existing.product_id)
        if existing is None or existing.product_id is None:
            wb_nm_id = row.get("nmId")
            wb_chrt_id = row.get("chrtId")
            product = await wb_marketplace_orders_service._map_product(
                session,
                tenant_id,
                seller_id,
                wb_barcode=(
                    wb_marketplace_orders_service._first_barcode(row)
                    or (existing.wb_barcode if existing is not None else None)
                ),
                wb_nm_id=int(wb_nm_id) if wb_nm_id is not None else None,
                wb_chrt_id=(
                    int(wb_chrt_id)
                    if wb_chrt_id is not None
                    else (existing.wb_chrt_id if existing is not None else None)
                ),
            )
            if product is not None:
                stock_product_ids.add(product.id)

    if affected_order_ids:
        stock_product_ids.update(
            (await session.scalars(
                select(FbsOrderReservation.product_id).where(
                    FbsOrderReservation.fbs_order_id.in_(affected_order_ids)
                )
            )).all()
        )
        stock_product_ids.update(
            (await session.scalars(
                select(FbsOrderProductReservation.product_id)
                .join(
                    FbsOrderProduct,
                    FbsOrderProduct.id == FbsOrderProductReservation.order_product_id,
                )
                .where(FbsOrderProduct.order_id.in_(affected_order_ids))
            )).all()
        )
    await inventory_service.lock_stock_products(session, tenant_id, stock_product_ids)

    stats.received += len(rows)
    for row in rows:
        warehouse_id = _warehouse_id(row)
        scope = scopes.get(warehouse_id) if warehouse_id is not None else None
        if scope is not True:
            existing_id = known_orders.get(int(row["id"])) if row.get("id") is not None else None
            if existing_id is not None:
                await capture_wb_price_snapshot(
                    session, tenant_id=tenant_id, seller_id=seller_id, order_id=existing_id,
                    row=row, source=price_source,
                )
            stats.skipped_unserved += 1
            continue
        _order, was_created = await upsert_order_from_wb_row(
            session,
            tenant_id,
            seller_id,
            row,
            preserve_unmapped_warehouse=False,
            price_source=price_source,
        )
        stats.upserted += 1
        stats.created += int(was_created)
