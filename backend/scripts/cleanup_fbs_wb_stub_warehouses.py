#!/usr/bin/env python3
"""Report script for identifying FBS WB stub warehouses.

This is a read-only dry-run script that identifies technical stub warehouses
created automatically for FBS sellers (code starts with 'fbs-wb-' OR name starts
with 'FBS WB ') and reports what is bound to them:
- Count of active FbsWarehouseBinding records
- Count of inventory balances

WARNING: This script does NOT modify the database. It only reads and reports.
It is the starting point for future manual cleanup — execute it to get a report,
then decide manually which warehouses to delete. DO NOT run this automatically.
Requires explicit operator review and approval.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.models.warehouse import Warehouse
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation


def is_auto_fbs_wms_warehouse(warehouse: Warehouse) -> bool:
    """Check if warehouse is an auto-generated FBS stub.

    Mirrors the logic from FbsWarehouseBindingService.is_auto_fbs_wms_warehouse
    and frontend isTechnicalWmsWarehouse.
    """
    return (
        warehouse.code.startswith("fbs-wb-")
        or warehouse.name.startswith("FBS WB ")
    )


async def count_active_bindings(
    session: AsyncSession, warehouse_id: UUID
) -> int:
    """Count active FbsWarehouseBinding records for a warehouse."""
    stmt = select(func.count(FbsWarehouseBinding.id)).where(
        FbsWarehouseBinding.wms_warehouse_id == warehouse_id,
        FbsWarehouseBinding.is_active == True,
    )
    result = await session.scalar(stmt)
    return result or 0


async def count_inventory_balances(
    session: AsyncSession, warehouse_id: UUID
) -> int:
    """Count InventoryBalance items on storage locations in this warehouse."""
    stmt = select(func.count(InventoryBalance.id)).select_from(
        InventoryBalance
    ).join(
        StorageLocation,
        InventoryBalance.storage_location_id == StorageLocation.id,
    ).where(
        StorageLocation.warehouse_id == warehouse_id,
    )
    result = await session.scalar(stmt)
    return result or 0


async def main() -> None:
    """Find and report FBS stub warehouses."""
    async with SessionLocal() as session:
        # Find all warehouses matching the stub pattern
        stmt = select(Warehouse).order_by(
            Warehouse.tenant_id,
            Warehouse.created_at,
        )
        result = await session.execute(stmt)
        all_warehouses = result.scalars().all()

        stub_warehouses = [
            wh for wh in all_warehouses if is_auto_fbs_wms_warehouse(wh)
        ]

        if not stub_warehouses:
            print("No FBS stub warehouses found.")
            return

        print(f"Found {len(stub_warehouses)} FBS stub warehouses:\n")
        print(
            f"{'ID':<38} | "
            f"{'Tenant ID':<38} | "
            f"{'Code':<30} | "
            f"{'Name':<30} | "
            f"{'Created At':<26} | "
            f"{'Bindings':<8} | "
            f"{'Balances':<8}"
        )
        print("-" * 215)

        warehouses_with_bindings = 0
        warehouses_orphaned = 0

        for wh in stub_warehouses:
            binding_count = await count_active_bindings(session, wh.id)
            balance_count = await count_inventory_balances(session, wh.id)

            if binding_count > 0:
                warehouses_with_bindings += 1
            elif balance_count == 0:
                warehouses_orphaned += 1

            created_at_str = (
                wh.created_at.isoformat()
                if wh.created_at
                else "None"
            )

            print(
                f"{str(wh.id):<38} | "
                f"{str(wh.tenant_id):<38} | "
                f"{wh.code:<30} | "
                f"{wh.name:<30} | "
                f"{created_at_str:<26} | "
                f"{binding_count:<8} | "
                f"{balance_count:<8}"
            )

        print("\n" + "=" * 215)
        print(f"\nSummary:")
        print(f"  Total FBS stub warehouses:        {len(stub_warehouses)}")
        print(f"  Warehouses with active bindings:  {warehouses_with_bindings}")
        print(
            f"    ⚠️  Cannot be deleted until bindings are reassigned "
            f"to normal warehouses"
        )
        print(f"  Orphaned warehouses (safe):       {warehouses_orphaned}")
        print(
            f"    ✓ No active bindings or inventory — could be candidates "
            f"for deletion"
        )
        print()
        print("⚠️  This is a read-only report. No database changes were made.")
        print(
            "    Review the output above, then decide whether to delete "
            "orphaned warehouses."
        )


if __name__ == "__main__":
    asyncio.run(main())
