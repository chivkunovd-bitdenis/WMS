#!/usr/bin/env python3
"""Cleanup script for FBS stub test orders (stage/production only).

This script identifies and removes test FBS orders with hardcoded wb_order_id values
that exist in the database but have no corresponding entry in the Wildberries cabinet
(e.g., 960000000005, 960000010001, 960000010003). These orders accumulate in the
"Новые" (New) tab with expired assembly deadlines and clutter the queue.

IMPORTANT SAFETY NOTES:
- Running without --apply is a safe, read-only dry-run that only reports findings.
- Running with --apply performs IRREVERSIBLE deletion from the database.
- Before using --apply, operator MUST manually review the report output and verify
  that the listed orders are truly test orders with no counterpart in WB cabinet.
- The script does NOT interact with Wildberries API — it only deletes local database
  records. Operator responsibility: confirm via WB cabinet that orders are fake before
  deleting them locally.
- Related marking codes (fbs_marking_codes table) are NOT deleted — only the
  fbs_order_markings associations are removed. This may leave marking codes in "used"
  state; manual cleanup of the marking pool may be required separately.

USAGE EXAMPLES:

  # Dry-run (safe, only reads and reports):
  python backend/scripts/cleanup_fbs_stub_test_orders.py \\
      --wb-order-id 960000000005 --wb-order-id 960000010001 --wb-order-id 960000010003

  # With optional tenant filter:
  python backend/scripts/cleanup_fbs_stub_test_orders.py \\
      --wb-order-id 960000000005 \\
      --tenant-id 550e8400-e29b-41d4-a716-446655440000

  # ACTUAL DELETION (irreversible!):
  python backend/scripts/cleanup_fbs_stub_test_orders.py \\
      --wb-order-id 960000000005 --wb-order-id 960000010001 --wb-order-id 960000010003 \\
      --apply
"""

# Imports below ROOT setup are intentional: this standalone script must add the backend path first.
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.models.fbs_order import (
    FbsOrder,
    FbsOrderMarking,
    FbsOrderReservation,
)
from app.models.fbs_order_pick import FbsOrderPick
from app.models.fbs_packaging_fulfillment import FbsPackagingFulfillment
from app.models.fbs_packing_box import FbsPackingBoxItem
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger


async def count_related_records(
    session: AsyncSession, fbs_order_ids: list[UUID]
) -> dict[str, int]:
    """Count related records for each FBS order by type."""
    counts = {
        "markings": 0,
        "reservations": 0,
        "reserved_qty": 0,
        "picks": 0,
        "packaging": 0,
        "packing_boxes": 0,
        "reversals": 0,
        "print_assets": 0,
    }

    if not fbs_order_ids:
        return counts

    # Count FbsOrderMarking
    stmt = select(func.count(FbsOrderMarking.id)).where(
        FbsOrderMarking.order_id.in_(fbs_order_ids)
    )
    counts["markings"] = (await session.scalar(stmt)) or 0

    # Count FbsOrderReservation and sum quantity (actual warehouse reserved stock)
    stmt = select(func.count(FbsOrderReservation.id)).where(
        FbsOrderReservation.fbs_order_id.in_(fbs_order_ids)
    )
    counts["reservations"] = (await session.scalar(stmt)) or 0

    stmt = select(func.sum(FbsOrderReservation.quantity)).where(
        FbsOrderReservation.fbs_order_id.in_(fbs_order_ids)
    )
    counts["reserved_qty"] = (await session.scalar(stmt)) or 0

    # Count FbsOrderPick
    stmt = select(func.count(FbsOrderPick.id)).where(
        FbsOrderPick.fbs_order_id.in_(fbs_order_ids)
    )
    counts["picks"] = (await session.scalar(stmt)) or 0

    # Count FbsPackagingFulfillment
    stmt = select(func.count(FbsPackagingFulfillment.id)).where(
        FbsPackagingFulfillment.fbs_order_id.in_(fbs_order_ids)
    )
    counts["packaging"] = (await session.scalar(stmt)) or 0

    # Count FbsPackingBoxItem
    stmt = select(func.count(FbsPackingBoxItem.id)).where(
        FbsPackingBoxItem.fbs_order_id.in_(fbs_order_ids)
    )
    counts["packing_boxes"] = (await session.scalar(stmt)) or 0

    # Count FbsShipmentReversalLedger
    stmt = select(func.count(FbsShipmentReversalLedger.id)).where(
        FbsShipmentReversalLedger.fbs_order_id.in_(fbs_order_ids)
    )
    counts["reversals"] = (await session.scalar(stmt)) or 0

    # Count FbsPrintAsset
    stmt = select(func.count(FbsPrintAsset.id)).where(
        FbsPrintAsset.fbs_order_id.in_(fbs_order_ids)
    )
    counts["print_assets"] = (await session.scalar(stmt)) or 0

    return counts


async def report_orders(
    session: AsyncSession,
    wb_order_ids: list[int],
    tenant_id: UUID | None,
) -> tuple[Sequence[FbsOrder], int]:
    """Find and report FBS orders by wb_order_id.

    Returns:
        Tuple of (found_orders, total_related_records)
    """
    # Build query
    stmt = select(FbsOrder).where(FbsOrder.wb_order_id.in_(wb_order_ids))

    if tenant_id:
        stmt = stmt.where(FbsOrder.tenant_id == tenant_id)

    stmt = stmt.order_by(FbsOrder.tenant_id, FbsOrder.wb_order_id)
    result = await session.execute(stmt)
    found_orders = result.scalars().all()

    if not found_orders:
        print("No FBS orders found matching the provided wb_order_id list.")
        return [], 0

    # Collect order IDs for bulk counting
    found_order_ids = [order.id for order in found_orders]
    related_counts = await count_related_records(session, found_order_ids)

    print(f"\nFound {len(found_orders)} FBS order(s) matching criteria:\n")
    print(
        f"{'Order ID':<38} | "
        f"{'Tenant ID':<38} | "
        f"{'Seller ID':<38} | "
        f"{'WB Order ID':<15} | "
        f"{'Status':<15} | "
        f"{'Deadline':<26} | "
        f"{'Supply ID':<38} | "
        f"{'Markings':<8} | "
        f"{'Reserv.':<8}"
    )
    print("-" * 385)

    for order in found_orders:
        deadline_str = (
            order.deadline_at.isoformat()
            if order.deadline_at
            else "None"
        )
        supply_indicator = "✓" if order.supply_id else "—"

        print(
            f"{order.id!s:<38} | "
            f"{order.tenant_id!s:<38} | "
            f"{order.seller_id!s:<38} | "
            f"{order.wb_order_id:<15} | "
            f"{(order.status or 'unknown'):<15} | "
            f"{deadline_str:<26} | "
            f"{supply_indicator:<38} | "
            f"{related_counts['markings']:<8} | "
            f"{related_counts['reservations']:<8}"
        )

    # Print summary
    print("\n" + "=" * 385)
    print(f"\nRelated records summary (total across all {len(found_orders)} order(s)):")
    print(f"  FbsOrderMarking:                  {related_counts['markings']}")
    print(f"  FbsOrderReservation:              {related_counts['reservations']} "
          f"(qty: {related_counts['reserved_qty']})")
    print("    ⚠️  Warehouse reserve will be freed when these are deleted")
    print(f"  FbsOrderPick:                     {related_counts['picks']}")
    print(f"  FbsPackagingFulfillment:          {related_counts['packaging']}")
    print(f"  FbsPackingBoxItem:                {related_counts['packing_boxes']}")
    print(f"  FbsShipmentReversalLedger:        {related_counts['reversals']}")
    print(f"  FbsPrintAsset:                    {related_counts['print_assets']}")

    # Mark orders with supply_id
    orders_with_supply = [o for o in found_orders if o.supply_id]
    if orders_with_supply:
        print(f"\n⚠️  {len(orders_with_supply)} order(s) are part of an active supply:")
        for order in orders_with_supply:
            print(f"    - WB Order ID {order.wb_order_id} → Supply ID {order.supply_id}")
        print("    Deletion will not fail, but it may break supply accounting.")

    # Check for missing orders
    found_wb_ids = {o.wb_order_id for o in found_orders}
    missing_wb_ids = set(wb_order_ids) - found_wb_ids
    if missing_wb_ids:
        print(f"\n⚠️  {len(missing_wb_ids)} requested wb_order_id(s) NOT found in database:")
        for wb_id in sorted(missing_wb_ids):
            print(f"    - {wb_id}")

    # Marking codes warning
    if related_counts['markings'] > 0:
        print("\n⚠️  Marking code pools will NOT be deleted or freed:")
        print(f"    Only {related_counts['markings']} marking association(s) will be removed.")
        print("    The marking_codes table itself is not touched.")
        print("    Manual cleanup may be needed if codes should not stay in 'used' state.")

    total_related = (
        related_counts['markings']
        + related_counts['reservations']
        + related_counts['picks']
        + related_counts['packaging']
        + related_counts['packing_boxes']
        + related_counts['reversals']
        + related_counts['print_assets']
    )

    return found_orders, total_related


async def delete_orders(
    session: AsyncSession,
    orders: Sequence[FbsOrder],
) -> int:
    """Delete FBS orders and all related records in the correct order.

    Deletion order (respects FK constraints):
    1. FbsPrintAsset
    2. FbsShipmentReversalLedger
    3. FbsPackingBoxItem
    4. FbsPackagingFulfillment
    5. FbsOrderPick
    6. FbsOrderReservation (frees warehouse reserved stock)
    7. FbsOrderMarking
    8. FbsOrder (the parent)

    Args:
        session: Async database session
        orders: List of FbsOrder objects to delete

    Returns:
        Total number of records deleted (including parents and children)
    """
    order_ids = [o.id for o in orders]
    wb_order_ids = [o.wb_order_id for o in orders]

    print("\n" + "=" * 385)
    print(f"\n⚠️  FINAL CONFIRMATION: About to delete {len(orders)} FBS order(s) PERMANENTLY:")
    for wb_id in sorted(wb_order_ids):
        print(f"    - WB Order ID {wb_id}")
    print("\nThis action is IRREVERSIBLE and cannot be undone.")
    print("\nPassage of --apply flag is your explicit confirmation to proceed.")
    print("=" * 385 + "\n")

    try:
        total_deleted = 0

        # 1. Delete FbsPrintAsset
        stmt = delete(FbsPrintAsset).where(FbsPrintAsset.fbs_order_id.in_(order_ids))
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsPrintAsset record(s)")
            total_deleted += count

        # 2. Delete FbsShipmentReversalLedger
        stmt = delete(FbsShipmentReversalLedger).where(
            FbsShipmentReversalLedger.fbs_order_id.in_(order_ids)
        )
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsShipmentReversalLedger record(s)")
            total_deleted += count

        # 3. Delete FbsPackingBoxItem
        stmt = delete(FbsPackingBoxItem).where(
            FbsPackingBoxItem.fbs_order_id.in_(order_ids)
        )
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsPackingBoxItem record(s)")
            total_deleted += count

        # 4. Delete FbsPackagingFulfillment
        stmt = delete(FbsPackagingFulfillment).where(
            FbsPackagingFulfillment.fbs_order_id.in_(order_ids)
        )
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsPackagingFulfillment record(s)")
            total_deleted += count

        # 5. Delete FbsOrderPick
        stmt = delete(FbsOrderPick).where(FbsOrderPick.fbs_order_id.in_(order_ids))
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsOrderPick record(s)")
            total_deleted += count

        # 6. Delete FbsOrderReservation (frees warehouse reserved stock)
        stmt = delete(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id.in_(order_ids)
        )
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsOrderReservation record(s) "
                  f"[warehouse reserves freed]")
            total_deleted += count

        # 7. Delete FbsOrderMarking
        stmt = delete(FbsOrderMarking).where(
            FbsOrderMarking.order_id.in_(order_ids)
        )
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsOrderMarking record(s)")
            total_deleted += count

        # 8. Delete FbsOrder (parent)
        stmt = delete(FbsOrder).where(FbsOrder.id.in_(order_ids))
        result = await session.execute(stmt)
        count = cast(CursorResult[Any], result).rowcount
        if count > 0:
            print(f"  ✓ Deleted {count} FbsOrder record(s)")
            total_deleted += count

        await session.commit()
        print("\n✓ Transaction committed successfully.")
        print(f"  Total records deleted: {total_deleted}")
        print(f"  Orders deleted: {len(orders)}")

        return total_deleted

    except Exception as e:
        await session.rollback()
        print(f"\n✗ Error during deletion: {e}")
        print("  Transaction rolled back. No changes were made.")
        raise


async def main() -> None:
    """Main entry point: parse args, report, and optionally delete."""
    parser = argparse.ArgumentParser(
        description="Cleanup FBS stub test orders from database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "EXAMPLES:\n"
            "  (Dry-run, safe):\n"
            "    python backend/scripts/cleanup_fbs_stub_test_orders.py \\\n"
            "        --wb-order-id 960000000005 --wb-order-id 960000010001\n"
            "\n"
            "  (With tenant filter):\n"
            "    python backend/scripts/cleanup_fbs_stub_test_orders.py \\\n"
            "        --wb-order-id 960000000005 \\\n"
            "        --tenant-id 550e8400-e29b-41d4-a716-446655440000\n"
            "\n"
            "  (ACTUAL DELETION — irreversible):\n"
            "    python backend/scripts/cleanup_fbs_stub_test_orders.py \\\n"
            "        --wb-order-id 960000000005 --wb-order-id 960000010001 \\\n"
            "        --apply\n"
        ),
    )

    parser.add_argument(
        "--wb-order-id",
        type=int,
        action="append",
        required=True,
        help="WB order ID to find and delete (can be used multiple times: "
        "--wb-order-id 960000000005 --wb-order-id 960000010001)",
    )

    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="Optional: filter by tenant UUID. If not provided, searches all tenants.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="ENABLE DELETION. Without this flag, script runs in read-only "
        "dry-run mode and only reports findings. With --apply, orders are "
        "PERMANENTLY deleted from the database.",
    )

    args = parser.parse_args()

    # Parse optional tenant_id
    tenant_id_obj: UUID | None = None
    if args.tenant_id:
        try:
            tenant_id_obj = UUID(args.tenant_id)
        except ValueError:
            print(f"Error: Invalid UUID format for --tenant-id: {args.tenant_id}")
            sys.exit(1)

    # Validate and deduplicate order IDs
    wb_order_ids = list(set(args.wb_order_id))
    if not wb_order_ids:
        print("Error: No valid wb_order_id values provided.")
        sys.exit(1)

    print(f"Starting cleanup process for {len(wb_order_ids)} unique wb_order_id(s)...")
    if tenant_id_obj:
        print(f"Filtered by tenant_id: {tenant_id_obj}")
    print()

    async with SessionLocal() as session:
        # PHASE 1: Report (always run)
        found_orders, _total_related = await report_orders(
            session, wb_order_ids, tenant_id_obj
        )

        if not found_orders:
            print("\n" + "=" * 385)
            print("\nNo orders to delete. Exiting.")
            return

        # PHASE 2: Optional deletion
        if args.apply:
            print("\n✓ --apply flag detected. Proceeding with deletion...\n")
            try:
                await delete_orders(session, found_orders)
                print("\n" + "=" * 385)
                print("\n✓ Cleanup completed successfully.")
            except Exception as e:
                print(f"\n✗ Cleanup failed: {e}")
                sys.exit(1)
        else:
            print("\n" + "=" * 385)
            print("\n✓ This was a DRY-RUN (read-only mode).")
            print("  No changes were made to the database.")
            print(f"\n  To actually delete these {len(found_orders)} order(s), "
                  f"re-run with --apply flag:")
            print("\n  python backend/scripts/cleanup_fbs_stub_test_orders.py \\")
            joined_order_ids = " --wb-order-id ".join(map(str, sorted(wb_order_ids)))
            print(f"      --wb-order-id {joined_order_ids} \\")
            print("      --apply\n")


if __name__ == "__main__":
    asyncio.run(main())
