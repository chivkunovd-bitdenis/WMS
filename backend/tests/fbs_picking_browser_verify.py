"""Read-only snapshots of the same DB records mutated through the real browser."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderProduct,
    FbsOrderProductPick,
    FbsOrderProductReservation,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from tests.fbs_picking_browser_seed import guard


async def main() -> None:
    guard()
    seed = json.load(sys.stdin)
    tenant = uuid.UUID(seed["tenant_id"])
    async with SessionLocal() as session:
        balances = (
            await session.scalars(
                select(InventoryBalance).where(InventoryBalance.tenant_id == tenant)
            )
        ).all()
        picks = (
            await session.scalars(select(FbsOrderPick).where(FbsOrderPick.tenant_id == tenant))
        ).all()
        ozon = (
            await session.scalars(
                select(FbsOrderProductPick).where(FbsOrderProductPick.tenant_id == tenant)
            )
        ).all()
        reserves = (
            await session.scalars(
                select(FbsOrderReservation).where(FbsOrderReservation.tenant_id == tenant)
            )
        ).all()
        position_reserves = (
            await session.scalars(
                select(FbsOrderProductReservation).where(
                    FbsOrderProductReservation.tenant_id == tenant
                )
            )
        ).all()
        positions = (
            await session.execute(
                select(FbsOrderProduct, FbsOrder)
                .join(FbsOrder, FbsOrder.id == FbsOrderProduct.order_id)
                .where(FbsOrder.tenant_id == tenant)
            )
        ).all()
        supplies = (
            await session.scalars(select(FbsSupply).where(FbsSupply.tenant_id == tenant))
        ).all()
        operations = (
            await session.scalars(select(FbsWbOperation).where(FbsWbOperation.tenant_id == tenant))
        ).all()
        stock = {}
        for b in balances:
            stock[str(b.product_id)] = stock.get(str(b.product_id), 0) + b.quantity

        def one(p):
            return {
                "id": str(p.id),
                "supply": str(p.fbs_supply_id),
                "product": str(p.product_id),
                "order": str(p.fbs_order_id) if isinstance(p, FbsOrderPick) else None,
                "position": str(p.order_product_id) if isinstance(p, FbsOrderProductPick) else None,
                "location": str(p.source_storage_location_id),
                "container": str(p.source_container_id) if p.source_container_id else None,
                "sorting": str(p.sorting_storage_location_id),
                "key": p.scan_idempotency_key,
                "active": p.undone_at is None,
                "movement": str(p.inventory_movement_id) if p.inventory_movement_id else None,
            }

        result = {
            "supplies": [
                {
                    "id": str(s.id),
                    "marketplace": s.marketplace,
                    "warehouse": str(s.warehouse_id),
                    "planned_shipment_date": s.planned_shipment_date.isoformat()
                    if s.planned_shipment_date
                    else None,
                }
                for s in supplies
            ],
            "operations": [
                {
                    "id": str(operation.id),
                    "supply": str(operation.local_entity_id),
                    "kind": operation.operation_kind,
                    "state": operation.state,
                    "request_summary": operation.request_summary_json,
                }
                for operation in operations
            ],
            "stock": stock,
            "unchanged": stock == seed["stock_by_product"],
            "balances": [
                {
                    "product": str(b.product_id),
                    "location": str(b.storage_location_id),
                    "container": str(b.container_id) if b.container_id else None,
                    "quantity": b.quantity,
                    "unpacked": b.quantity_unpacked,
                    "packed": b.quantity_packed,
                }
                for b in balances
            ],
            "picks": [one(p) for p in [*picks, *ozon]],
            "positions": [
                {
                    "id": str(position.id),
                    "order": str(order.id),
                    "product": str(position.product_id),
                    "supply": str(order.supply_id),
                    "warehouse": str(order.warehouse_id),
                    "quantity": position.quantity,
                    "reserved_quantity": position.reserved_quantity,
                    "picked_quantity": position.picked_quantity,
                }
                for position, order in positions
            ],
            "position_reserves": [
                {
                    "position": str(r.order_product_id),
                    "product": str(r.product_id),
                    "warehouse": str(r.warehouse_id),
                    "quantity": r.quantity,
                }
                for r in position_reserves
            ],
            "reserves": [
                {"order": str(r.fbs_order_id), "product": str(r.product_id), "quantity": r.quantity}
                for r in reserves
            ],
        }
        sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
