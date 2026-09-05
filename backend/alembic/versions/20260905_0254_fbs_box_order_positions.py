"""WMS-355: assign whole Ozon positions to boxes, keeping WB orders indivisible."""

import sqlalchemy as sa

from alembic import op

revision = "20260905_0254"
down_revision = "20260905_0253"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.add_column(sa.Column("order_product_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_fbs_box_item_order_product",
            "fbs_order_products",
            ["order_product_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_constraint("uq_fbs_packing_box_items_order", type_="unique")
    op.create_index(
        "uq_fbs_packing_box_items_order_position",
        "fbs_packing_box_items",
        [
            "fbs_order_id",
            sa.text("coalesce(order_product_id, '00000000-0000-0000-0000-000000000000')"),
        ],
        unique=True,
    )
    # Ozon's old automatic mode has no operator-entered membership to preserve.
    op.execute(
        "UPDATE fbs_supplies SET boxes_without_distribution_at = NULL, "
        "boxes_without_distribution_by_user_id = NULL WHERE marketplace = 'ozon'"
    )


def downgrade() -> None:
    # Refuse to collapse several assigned positions into one arbitrary box.
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            "SELECT fbs_order_id FROM fbs_packing_box_items GROUP BY fbs_order_id "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate:
        raise RuntimeError("Remove position assignments before downgrading WMS-355")
    op.drop_index("uq_fbs_packing_box_items_order_position", table_name="fbs_packing_box_items")
    with op.batch_alter_table("fbs_packing_box_items") as batch:
        batch.drop_constraint("fk_fbs_box_item_order_product", type_="foreignkey")
        batch.drop_column("order_product_id")
        batch.create_unique_constraint("uq_fbs_packing_box_items_order", ["fbs_order_id"])
