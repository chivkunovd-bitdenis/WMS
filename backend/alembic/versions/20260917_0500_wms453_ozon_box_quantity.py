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
        batch.add_column(
            sa.Column("last_idempotency_key", sa.String(length=128), nullable=True)
        )

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
    # Refuse to collapse a position split across several boxes into the
    # single pre-WMS-453 row (same guard style as 0254's downgrade).
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            "SELECT order_product_id FROM fbs_packing_box_items "
            "WHERE order_product_id IS NOT NULL "
            "GROUP BY order_product_id HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError("Remove position assignments before downgrading WMS-453")
    op.drop_index("uq_fbs_packing_box_items_ozon_box_position", table_name="fbs_packing_box_items")
    op.drop_index("uq_fbs_packing_box_items_wb_order", table_name="fbs_packing_box_items")
    # Drop the quantity/last_idempotency_key columns *before* recreating the
    # old expression index: on SQLite, dropping a column rebuilds the table
    # (batch mode) and that rebuild cannot carry an expression-based index
    # across it, so an index created first would silently vanish.
    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.drop_column("quantity")
        batch.drop_column("last_idempotency_key")
    op.create_index(
        "uq_fbs_packing_box_items_order_position",
        "fbs_packing_box_items",
        [
            "fbs_order_id",
            sa.text("coalesce(order_product_id, '00000000-0000-0000-0000-000000000000')"),
        ],
        unique=True,
    )
