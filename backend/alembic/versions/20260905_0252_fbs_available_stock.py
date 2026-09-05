"""WMS-060: migrate the old displayed remainder into available FBS stock.

The old cutoff is read ONLY during this one-time conversion, then removed.
Runtime reservation/shipment processing never scans order history.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260905_0252"
down_revision = "20260904_0251"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT pool.id, pool.tenant_id, pool.product_id, pool.quantity,
               pool.allocated_at, b.wms_warehouse_id, b.wb_warehouse_id, b.marketplace,
               b.seller_id
        FROM fbs_binding_stock_pools pool
        JOIN products p ON p.id = pool.product_id
        JOIN fbs_warehouse_bindings b ON b.id = pool.binding_id
        WHERE p.fbs_units_mode = true
        ORDER BY pool.product_id, b.wms_warehouse_id, b.wb_warehouse_id
    """)).mappings().all()
    remaining: dict[tuple[object, object], int] = {}
    for row in rows:
        params = dict(row)
        key = (row["product_id"], row["wms_warehouse_id"])
        if key not in remaining:
            def total(sql: str) -> int:
                return int(connection.scalar(sa.text(sql), params) or 0)

            physical = total("""
                SELECT SUM(i.quantity) FROM inventory_balances i
                JOIN storage_locations loc ON loc.id = i.storage_location_id
                WHERE i.tenant_id = :tenant_id AND i.product_id = :product_id
                  AND loc.warehouse_id = :wms_warehouse_id
            """)
            reserved = total("""
                SELECT SUM(quantity) FROM fbs_order_reservations
                WHERE tenant_id = :tenant_id AND product_id = :product_id
                  AND warehouse_id = :wms_warehouse_id
            """) + total("""
                SELECT SUM(quantity) FROM fbs_order_product_reservations
                WHERE tenant_id = :tenant_id AND product_id = :product_id
                  AND warehouse_id = :wms_warehouse_id
            """) + total("""
                SELECT SUM(quantity) FROM stock_directions
                WHERE tenant_id = :tenant_id AND product_id = :product_id
            """) + total("""
                SELECT SUM(r.quantity) FROM inventory_reservations r
                JOIN outbound_shipment_lines l ON l.id = r.outbound_shipment_line_id
                JOIN outbound_shipment_requests d ON d.id = l.request_id
                LEFT JOIN storage_locations loc ON loc.id = r.storage_location_id
                WHERE r.tenant_id = :tenant_id AND r.product_id = :product_id
                  AND d.status IN ('draft', 'submitted')
                  AND ((r.storage_location_id IS NULL AND r.warehouse_id = :wms_warehouse_id)
                    OR loc.warehouse_id = :wms_warehouse_id)
            """) + total("""
                SELECT SUM(r.quantity) FROM marketplace_unload_reservations r
                JOIN marketplace_unload_lines l ON l.id = r.marketplace_unload_line_id
                JOIN marketplace_unload_requests d ON d.id = l.request_id
                WHERE r.tenant_id = :tenant_id AND r.product_id = :product_id
                  AND r.warehouse_id = :wms_warehouse_id
                  AND d.status IN ('submitted', 'confirmed', 'collecting')
            """)
            remaining[key] = max(0, physical - reserved)
        spent = 0
        if row["allocated_at"] is not None and row["marketplace"] == "wb":
            spent = int(connection.scalar(sa.text("""
                SELECT COUNT(*) FROM fbs_orders o
                WHERE o.tenant_id = :tenant_id AND o.seller_id = :seller_id
                  AND o.product_id = :product_id AND o.wb_warehouse_id = :wb_warehouse_id
                  AND o.created_at >= :allocated_at
                  AND (o.status != 'cancelled' OR EXISTS (
                    SELECT 1 FROM fbs_shipment_reversal_ledger l
                    WHERE l.fbs_order_id = o.id AND l.shipment_movement_id IS NOT NULL
                  ))
            """), params) or 0)
        available = min(max(0, int(row["quantity"]) - spent), remaining[key])
        remaining[key] -= available
        connection.execute(sa.text(
            "UPDATE fbs_binding_stock_pools SET quantity = :available WHERE id = :id"
        ), {"available": available, "id": row["id"]})
    op.drop_column("fbs_binding_stock_pools", "allocated_at")


def downgrade() -> None:
    # Preserve the converted available number as a fresh operator baseline.
    op.add_column("fbs_binding_stock_pools", sa.Column(
        "allocated_at", sa.DateTime(timezone=True), nullable=True,
    ))
    op.execute("UPDATE fbs_binding_stock_pools SET allocated_at = CURRENT_TIMESTAMP")
