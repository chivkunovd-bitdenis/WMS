"""Prevent reuse of Chestny Znak codes and physical boxes in FBS shipments.

Revision ID: 20260803_0071
Revises: 20260803_0070
"""

from alembic import op

revision = "20260803_0071"
down_revision = "20260803_0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Old versions did not enforce either relationship.  Keep the oldest link
    # deterministically, and detach the later duplicates before adding indexes.
    # This makes the migration safe on an already populated production database.
    op.execute(
        """
        WITH duplicates AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY marking_code_id
                       ORDER BY id ASC
                   ) AS row_num
            FROM fbs_order_markings
            WHERE marking_code_id IS NOT NULL
        )
        UPDATE fbs_order_markings
        SET marking_code_id = NULL
        WHERE id IN (SELECT id FROM duplicates WHERE row_num > 1)
        """
    )
    op.create_index(
        "uq_fbs_order_markings_marking_code_id",
        "fbs_order_markings",
        ["marking_code_id"],
        unique=True,
    )
    op.execute(
        """
        WITH duplicates AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY packaging_box_id
                       ORDER BY created_at ASC, id ASC
                   ) AS row_num
            FROM fbs_trbxes
            WHERE packaging_box_id IS NOT NULL
        )
        UPDATE fbs_trbxes
        SET packaging_box_id = NULL
        WHERE id IN (SELECT id FROM duplicates WHERE row_num > 1)
        """
    )
    op.create_index(
        "uq_fbs_trbxes_packaging_box_id",
        "fbs_trbxes",
        ["packaging_box_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_fbs_trbxes_packaging_box_id",
        table_name="fbs_trbxes",
    )
    op.drop_index(
        "uq_fbs_order_markings_marking_code_id",
        table_name="fbs_order_markings",
    )
