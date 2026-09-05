"""WMS-375: read-only arithmetic on the dedicated local pre-0252 snapshot.

Print aggregates only. No application import, migrations, writes, or raw rows.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict

SQL = r"""
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '120s';
WITH eligible AS (
 SELECT pool.*, b.seller_id, b.marketplace, b.wms_warehouse_id,
        b.wb_warehouse_id, b.is_active, b.served, b.stock_sync_enabled,
        p.fbs_stock_sync_enabled AS product_enabled
 FROM fbs_binding_stock_pools pool
 JOIN products p ON p.id=pool.product_id
 JOIN fbs_warehouse_bindings b ON b.id=pool.binding_id
 WHERE p.fbs_units_mode=true
), compared AS (
 SELECT e.*,
  COALESCE((SELECT SUM(d.quantity_debited)
    FROM fbs_stock_pool_debits d JOIN fbs_orders o ON o.id=d.order_id
    WHERE d.pool_id=e.id
      AND o.created_at>=COALESCE(e.allocated_at,e.updated_at,e.created_at)
      AND (o.status!='cancelled' OR EXISTS (
        SELECT 1 FROM fbs_shipment_reversal_ledger l
        WHERE l.fbs_order_id=o.id AND l.shipment_movement_id IS NOT NULL))),0) AS spent_old,
  CASE WHEN e.allocated_at IS NOT NULL AND e.marketplace='wb' THEN (
    SELECT COUNT(*) FROM fbs_orders o
    WHERE o.tenant_id=e.tenant_id AND o.seller_id=e.seller_id
      AND o.product_id=e.product_id AND o.wb_warehouse_id=e.wb_warehouse_id
      AND o.created_at>=e.allocated_at
      AND (o.status!='cancelled' OR EXISTS (
        SELECT 1 FROM fbs_shipment_reversal_ledger l
        WHERE l.fbs_order_id=o.id AND l.shipment_movement_id IS NOT NULL)))
    ELSE 0 END AS spent_0252,
  COALESCE((SELECT SUM(i.quantity) FROM inventory_balances i
    JOIN storage_locations loc ON loc.id=i.storage_location_id
    WHERE i.tenant_id=e.tenant_id AND i.product_id=e.product_id
      AND loc.warehouse_id=e.wms_warehouse_id),0) AS physical,
  COALESCE((SELECT SUM(quantity) FROM fbs_order_reservations r
    WHERE r.tenant_id=e.tenant_id AND r.product_id=e.product_id
      AND r.warehouse_id=e.wms_warehouse_id),0)
  + COALESCE((SELECT SUM(quantity) FROM fbs_order_product_reservations r
    WHERE r.tenant_id=e.tenant_id AND r.product_id=e.product_id
      AND r.warehouse_id=e.wms_warehouse_id),0)
  + COALESCE((SELECT SUM(quantity) FROM stock_directions r
    WHERE r.tenant_id=e.tenant_id AND r.product_id=e.product_id),0)
  + COALESCE((SELECT SUM(r.quantity) FROM inventory_reservations r
    JOIN outbound_shipment_lines l ON l.id=r.outbound_shipment_line_id
    JOIN outbound_shipment_requests d ON d.id=l.request_id
    LEFT JOIN storage_locations loc ON loc.id=r.storage_location_id
    WHERE r.tenant_id=e.tenant_id AND r.product_id=e.product_id
      AND d.status IN ('draft','submitted')
      AND ((r.storage_location_id IS NULL AND r.warehouse_id=e.wms_warehouse_id)
        OR loc.warehouse_id=e.wms_warehouse_id)),0)
  + COALESCE((SELECT SUM(r.quantity) FROM marketplace_unload_reservations r
    JOIN marketplace_unload_lines l ON l.id=r.marketplace_unload_line_id
    JOIN marketplace_unload_requests d ON d.id=l.request_id
    WHERE r.tenant_id=e.tenant_id AND r.product_id=e.product_id
      AND r.warehouse_id=e.wms_warehouse_id
      AND d.status IN ('submitted','confirmed','collecting')),0) AS reserved
 FROM eligible e
)
SELECT json_build_object(
 'revision',(SELECT json_agg(version_num ORDER BY version_num) FROM alembic_version),
 'read_only',current_setting('transaction_read_only'),
 'pools',COALESCE((SELECT json_agg(c ORDER BY product_id,wms_warehouse_id,wb_warehouse_id)
                 FROM compared c),'[]'::json),
 'bindings',COALESCE((SELECT json_agg(b) FROM (
   SELECT id,tenant_id,seller_id,wms_warehouse_id,wb_warehouse_id,
          is_active,served,stock_sync_enabled,marketplace
   FROM fbs_warehouse_bindings
 ) b),'[]'::json),
 'cross_tenant_locations',(SELECT COUNT(*) FROM inventory_balances i
    JOIN storage_locations l ON l.id=i.storage_location_id WHERE i.tenant_id!=l.tenant_id),
 'cross_tenant_outbound_locations',(SELECT COUNT(*) FROM inventory_reservations r
    JOIN storage_locations l ON l.id=r.storage_location_id WHERE r.tenant_id!=l.tenant_id)
);
ROLLBACK;
"""


def main() -> None:
    # Explicit local socket, fixed database/user: no remote/production connection.
    result = subprocess.run(
        ["psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-h", "/tmp",
         "-U", "deniscivkunov", "-d", "wms375_a08_pre0252"],
        input=SQL, text=True, capture_output=True, check=True,
    )
    data = json.loads(result.stdout)
    if data["revision"] != ["20260904_0251"] or data["read_only"] != "on":
        raise RuntimeError("Expected pre-0252 snapshot in a read-only transaction")
    rows = data["pools"]
    sort_counts = Counter((r["product_id"], r["wms_warehouse_id"], r["wb_warehouse_id"])
                          for r in rows)
    if any(count > 1 for count in sort_counts.values()):
        raise RuntimeError("Ambiguous migration order: do not invent allocation among ties")
    if data["cross_tenant_locations"] or data["cross_tenant_outbound_locations"]:
        raise RuntimeError("Baseline/migration location scope differs; inspect before comparing")

    old_remaining: dict[tuple[str, str], int] = {}
    new_remaining: dict[tuple[str, str], int] = {}
    original_remaining: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["product_id"], row["wms_warehouse_id"])
        free = max(0, row["physical"] - row["reserved"])
        row["old_raw"] = max(0, row["quantity"] - row["spent_old"])
        row["new_raw"] = max(0, row["quantity"] - row["spent_0252"])
        for name, remaining, desired in (
            ("old_same_cap", old_remaining, row["old_raw"]),
            ("converted", new_remaining, row["new_raw"]),
            ("original_same_cap", original_remaining, row["quantity"]),
        ):
            amount = min(desired, remaining.setdefault(key, free))
            row[name] = amount
            remaining[key] -= amount

    # Literal baseline publication: active/served seller bindings sorted by
    # numeric warehouse ID, with the target warehouse's free quantity. Unlike
    # 0252, the old service did not filter this list to the physical warehouse.
    old_pool = {(r["product_id"], r["binding_id"]): r["old_raw"] for r in rows}
    for row in rows:
        if not (row["is_active"] and row["served"] and row["stock_sync_enabled"]):
            row["old_publication"] = None
            continue
        bindings = sorted((b for b in data["bindings"]
                           if b["tenant_id"] == row["tenant_id"]
                           and b["seller_id"] == row["seller_id"]
                           and b["is_active"] and b["served"]),
                          key=lambda b: b["wb_warehouse_id"])
        if len({b["wb_warehouse_id"] for b in bindings}) != len(bindings):
            raise RuntimeError("Ambiguous baseline binding order")
        remaining = max(0, row["physical"] - row["reserved"])
        for binding in bindings:
            share = old_pool.get((row["product_id"], binding["id"]), 0)
            amount = min(share, remaining) if row["product_enabled"] else 0
            remaining -= amount
            if binding["id"] == row["binding_id"]:
                row["old_publication"] = amount
                break

    def comparison(left: str, right: str, selected: list[dict]) -> dict:
        diffs = [r[right] - r[left] for r in selected]
        return {
            "rows": len(selected), "different_rows": sum(d != 0 for d in diffs),
            "lower_rows": sum(d < 0 for d in diffs), "higher_rows": sum(d > 0 for d in diffs),
            "decrease_units": -sum(d for d in diffs if d < 0),
            "increase_units": sum(d for d in diffs if d > 0),
            "left_total": sum(r[left] for r in selected),
            "right_total": sum(r[right] for r in selected),
        }

    summary = {
        "database": "wms375_a08_pre0252", "revision": data["revision"],
        "transaction_read_only": data["read_only"],
        "units_products": len({r["product_id"] for r in rows}), "pool_rows": len(rows),
        "null_allocated_at_rows": sum(r["allocated_at"] is None for r in rows),
        "migration_sort_ties": 0,
        "spent_difference_rows": sum(r["spent_old"] != r["spent_0252"] for r in rows),
        "old_raw_vs_new_raw": comparison("old_raw", "new_raw", rows),
        "old_counter_with_identical_cap_vs_0252": comparison("old_same_cap", "converted", rows),
        "stored_quantity_vs_0252": comparison("quantity", "converted", rows),
        "stored_quantity_same_cap_vs_0252": comparison("original_same_cap", "converted", rows),
        "baseline_publication_vs_0252_stored_quantity": comparison(
            "old_publication", "converted", [r for r in rows if r["old_publication"] is not None]),
    }
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups["null_cutoff" if row["allocated_at"] is None else "dated_cutoff"].append(row)
    summary["by_cutoff"] = {name: comparison("old_same_cap", "converted", group)
                            for name, group in groups.items()}
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
