"""Reconcile delivered FBS units that have no physical stock write-off."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import case, func, select, text

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_FBS_SHIPMENT, InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.services import inventory_service, stock_direction_service

RECONCILIATION_NAMESPACE = uuid.UUID("d4ccb65a-40eb-4bc9-a5cd-2dfb6d43ef43")
RECONCILIATION_VERSION = "delivered-fbs-20260826-v1"

MISSING_SQL = text(
    """
    WITH expected AS (
        SELECT l.tenant_id, l.product_id, l.storage_location_id, l.created_at,
               count(*)::int AS expected_units
        FROM fbs_shipment_reversal_ledger l
        JOIN fbs_orders o ON o.id = l.fbs_order_id
        JOIN fbs_supplies fs ON fs.id = o.supply_id
        WHERE fs.delivered_at IS NOT NULL
          AND o.status NOT IN ('cancelled', 'defect')
          AND l.reversed_at IS NULL
        GROUP BY 1, 2, 3, 4
    ), actual AS (
        SELECT tenant_id, product_id, storage_location_id, created_at,
               sum(-quantity_delta)::int AS actual_units
        FROM inventory_movements
        WHERE movement_type = 'fbs_shipment' AND quantity_delta < 0
          AND transfer_group_id IS NULL
        GROUP BY 1, 2, 3, 4
    ), ledger_missing AS (
        SELECT e.tenant_id, e.product_id,
               sum(greatest(e.expected_units - coalesce(a.actual_units, 0), 0))::int AS missing
        FROM expected e
        LEFT JOIN actual a USING (tenant_id, product_id, storage_location_id, created_at)
        GROUP BY 1, 2
        HAVING sum(greatest(e.expected_units - coalesce(a.actual_units, 0), 0)) > 0
    ), no_ledger AS (
        SELECT o.tenant_id, o.product_id, count(*)::int AS missing
        FROM fbs_orders o
        JOIN fbs_supplies fs ON fs.id = o.supply_id
        LEFT JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id = o.id
        WHERE fs.delivered_at IS NOT NULL
          AND o.product_id IS NOT NULL
          AND o.status NOT IN ('cancelled', 'defect')
          AND l.id IS NULL
        GROUP BY 1, 2
    )
    SELECT tenant_id, product_id, sum(missing)::int AS missing
    FROM (
        SELECT * FROM ledger_missing
        UNION ALL
        SELECT * FROM no_ledger
    ) combined
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
)


@dataclass(frozen=True)
class ProductReconciliation:
    tenant_id: str
    product_id: str
    seller_name: str | None
    sku_code: str
    historical_missing: int
    already_corrected: int
    pending: int
    available: int
    applied: int
    unavailable: int


def correction_group_id(tenant_id: uuid.UUID, product_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(
        RECONCILIATION_NAMESPACE,
        f"{RECONCILIATION_VERSION}:{tenant_id}:{product_id}",
    )


async def reconcile(*, apply: bool) -> dict[str, object]:
    results: list[ProductReconciliation] = []
    async with SessionLocal() as session:
        missing_rows = (await session.execute(MISSING_SQL)).all()
        for tenant_id, product_id, historical_missing in missing_rows:
            group_id = correction_group_id(tenant_id, product_id)
            already_corrected = int(
                await session.scalar(
                    select(func.coalesce(func.sum(-InventoryMovement.quantity_delta), 0)).where(
                        InventoryMovement.tenant_id == tenant_id,
                        InventoryMovement.product_id == product_id,
                        InventoryMovement.movement_type == MOVEMENT_TYPE_FBS_SHIPMENT,
                        InventoryMovement.quantity_delta < 0,
                        InventoryMovement.transfer_group_id == group_id,
                    )
                )
                or 0
            )
            pending = max(0, int(historical_missing) - already_corrected)
            product_row = (
                await session.execute(
                    select(Product.sku_code, Seller.name)
                    .outerjoin(Seller, Seller.id == Product.seller_id)
                    .where(Product.id == product_id, Product.tenant_id == tenant_id)
                )
            ).one()
            balances = list(
                (
                    await session.execute(
                        select(InventoryBalance)
                        .join(
                            StorageLocation,
                            StorageLocation.id == InventoryBalance.storage_location_id,
                        )
                        .where(
                            InventoryBalance.tenant_id == tenant_id,
                            InventoryBalance.product_id == product_id,
                            InventoryBalance.quantity > 0,
                        )
                        .order_by(
                            case((StorageLocation.code == "__SORTING__", 0), else_=1),
                            StorageLocation.code,
                        )
                        .with_for_update()
                    )
                ).scalars()
            )
            available = sum(
                max(0, int(row.quantity_unpacked) + int(row.quantity_packed))
                for row in balances
            )
            apply_qty = min(pending, available) if apply else 0
            if apply_qty > 0:
                await stock_direction_service.consume_fbs_pool(
                    session,
                    tenant_id,
                    product_id,
                    apply_qty,
                )
                remaining = apply_qty
                for balance in balances:
                    if remaining <= 0:
                        break
                    at_location = max(
                        0,
                        int(balance.quantity_unpacked) + int(balance.quantity_packed),
                    )
                    deduct = min(remaining, at_location)
                    if deduct <= 0:
                        continue
                    await inventory_service.record_movement_and_adjust_balance(
                        session,
                        tenant_id=tenant_id,
                        product_id=product_id,
                        storage_location_id=balance.storage_location_id,
                        quantity_delta=-deduct,
                        movement_type=MOVEMENT_TYPE_FBS_SHIPMENT,
                        transfer_group_id=group_id,
                        deduct_prefer="packed",
                        # Сверочный скрипт запускают из консоли: пользователя
                        # системы здесь нет, автора выдумывать нельзя.
                        actor_user_id=None,
                    )
                    remaining -= deduct
                if remaining != 0:
                    raise RuntimeError("locked FBS reconciliation balance changed unexpectedly")
            results.append(
                ProductReconciliation(
                    tenant_id=str(tenant_id),
                    product_id=str(product_id),
                    seller_name=product_row.name,
                    sku_code=product_row.sku_code,
                    historical_missing=int(historical_missing),
                    already_corrected=already_corrected,
                    pending=pending,
                    available=available,
                    applied=apply_qty,
                    unavailable=max(0, pending - available),
                )
            )
        if apply:
            await session.commit()
        else:
            await session.rollback()

    return {
        "mode": "apply" if apply else "check",
        "version": RECONCILIATION_VERSION,
        "products": len(results),
        "historical_missing": sum(row.historical_missing for row in results),
        "already_corrected": sum(row.already_corrected for row in results),
        "pending": sum(row.pending for row in results),
        "available": sum(min(row.pending, row.available) for row in results),
        "applied": sum(row.applied for row in results),
        "unavailable": sum(row.unavailable for row in results),
        "rows": [asdict(row) for row in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write idempotent correction movements; default is read-only check",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(reconcile(apply=args.apply)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
