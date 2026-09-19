"""WMS-453: split an Ozon order position's quantity across several boxes.

Before this, one FbsPackingBoxItem row meant "this whole position sits in this
box" (WMS-355) and a position could occupy exactly one box. The owner reversed
that part of WMS-355 on 2026-09-16: an operator may now split a position's
quantity across any number of boxes (10 in box 1, 10 in box 2, ...), so the row
needs its own quantity and the uniqueness rule changes from "one row per
position" to "at most one row per (box, position)" — a position may still
repeat across different boxes, just not twice within the same box.

Backfill: every existing Ozon row held its whole position, so it gets that
position's quantity; every WB row (order_product_id is null, whole order in
one box) gets 1 — WMS-453 does not touch WB's semantics.

Retry recognition for the new "add quantity to a box" call (R6) does not use a
column on this table — it reuses the existing tenant-wide uniqueness on
DocumentEvent(tenant_id, idempotency_key) (see EVENT_BOX_ITEM_ADDED in
app/models/document_event.py and _claim_ozon_assign_idempotency in
fbs_packing_box_service.py). An earlier draft added a last_idempotency_key
column here; cross-review (WMS-453 F1) found it insufficient — it forgets an
earlier key as soon as a later, unrelated add overwrites it on the same row —
so it never shipped and this migration does not add it.

Revision ID: 20260917_0500
Revises: 20260917_0460
Create Date: 2026-09-17 05:00:00.000000

Chained after 20260917_0460 (WMS-455, "общая корзинка" на products) rather than
directly on 20260913_0306: both were drafted in parallel in the shared
wms453-455-night worktree off the same head, touch disjoint tables
(products vs fbs_packing_box_items) and don't depend on each other; chaining
keeps a single alembic head instead of a branch (STAND.md).
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0500"
down_revision: str | None = "20260917_0460"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.add_column(sa.Column("quantity", sa.Integer(), nullable=True))

    # Drop the old expression index before the NOT NULL alter below: on
    # SQLite that alter rebuilds the table (batch mode), and batch mode
    # cannot carry an expression-based index across a rebuild — it would
    # silently vanish instead of being dropped on purpose.
    op.drop_index("uq_fbs_packing_box_items_order_position", table_name="fbs_packing_box_items")

    # Ozon rows used to mean "the whole position is here" — carry that
    # quantity forward so an already fully-assigned order stays fully
    # assigned (readiness/assembly must not regress for orders packed
    # before this release). WB rows never had a per-position quantity; 1
    # keeps their existing "whole order in one box" meaning unchanged.
    op.execute(
        "UPDATE fbs_packing_box_items SET quantity = ("
        "SELECT fbs_order_products.quantity FROM fbs_order_products "
        "WHERE fbs_order_products.id = fbs_packing_box_items.order_product_id"
        ") WHERE order_product_id IS NOT NULL"
    )
    op.execute("UPDATE fbs_packing_box_items SET quantity = 1 WHERE order_product_id IS NULL")

    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.alter_column(
            "quantity",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        )

    op.create_index(
        "uq_fbs_packing_box_items_wb_order",
        "fbs_packing_box_items",
        ["fbs_order_id"],
        unique=True,
        postgresql_where=sa.text("order_product_id IS NULL"),
        sqlite_where=sa.text("order_product_id IS NULL"),
    )
    op.create_index(
        "uq_fbs_packing_box_items_ozon_box_position",
        "fbs_packing_box_items",
        ["box_id", "order_product_id"],
        unique=True,
        postgresql_where=sa.text("order_product_id IS NOT NULL"),
        sqlite_where=sa.text("order_product_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Refuse to collapse a position into the single pre-WMS-453 row unless
    # that row can carry the *exact* old meaning: "this row is the whole
    # position". Two things make that impossible and must both be rejected
    # (same guard style as 0254's downgrade, widened after review WMS-453 F2):
    #   - several boxes hold pieces of one position (COUNT(*) > 1) — obviously
    #     can't collapse into one row;
    #   - a single box holds only *part* of a position, e.g. "10 of 100" —
    #     COUNT(*) = 1 but the old schema has no quantity column, so that one
    #     row would silently become "the whole position" (100), not what is
    #     physically in the box. A plain COUNT(*) > 1 check missed this and
    #     turned 10/100 into 100/100 on downgrade — a real loss of what the
    #     operator actually placed, not just a display change (order_packages
    #     reads this same column for what ships to Ozon).
    connection = op.get_bind()
    unsafe = connection.execute(
        sa.text(
            "SELECT items.order_product_id "
            "FROM fbs_packing_box_items AS items "
            "JOIN fbs_order_products AS positions ON positions.id = items.order_product_id "
            "WHERE items.order_product_id IS NOT NULL "
            "GROUP BY items.order_product_id, positions.quantity "
            "HAVING COUNT(*) > 1 OR SUM(items.quantity) <> MAX(positions.quantity) "
            "LIMIT 1"
        )
    ).first()
    if unsafe:
        raise RuntimeError(
            "Remove partial or multi-box position assignments before downgrading WMS-453"
        )
    op.drop_index("uq_fbs_packing_box_items_ozon_box_position", table_name="fbs_packing_box_items")
    op.drop_index("uq_fbs_packing_box_items_wb_order", table_name="fbs_packing_box_items")
    # Drop the quantity column *before* recreating the old expression index:
    # on SQLite, dropping a column rebuilds the table (batch mode) and that
    # rebuild cannot carry an expression-based index across it, so an index
    # created first would silently vanish.
    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.drop_column("quantity")
    op.create_index(
        "uq_fbs_packing_box_items_order_position",
        "fbs_packing_box_items",
        [
            "fbs_order_id",
            sa.text("coalesce(order_product_id, '00000000-0000-0000-0000-000000000000')"),
        ],
        unique=True,
    )
