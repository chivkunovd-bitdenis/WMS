"""Prevent reuse of Chestny Znak codes and physical boxes in FBS shipments.

The migration deliberately refuses existing duplicates.  Clearing links would
silently destroy audit evidence, so an operator must first take the documented
backup, inspect the rows, and perform an approved repair.

Revision ID: 20260804_0072
Revises: 20260804_0071
"""

from alembic import op
from sqlalchemy import text

revision = "20260804_0072"
down_revision = "20260804_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    marking_duplicates = bind.execute(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT marking_code_id
                FROM fbs_order_markings
                WHERE marking_code_id IS NOT NULL
                GROUP BY marking_code_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
            """
        )
    ).scalar_one()
    box_duplicates = bind.execute(
        text(
            """
            SELECT COUNT(*) FROM (
                SELECT packaging_box_id
                FROM fbs_trbxes
                WHERE packaging_box_id IS NOT NULL
                GROUP BY packaging_box_id
                HAVING COUNT(*) > 1
            ) AS duplicate_groups
            """
        )
    ).scalar_one()
    if marking_duplicates or box_duplicates:
        raise RuntimeError(
            "20260804_0072 preflight failed: duplicate marking-code groups="
            f"{marking_duplicates}, packaging-box groups={box_duplicates}. "
            "Do not run this migration until the rows are backed up and repaired."
        )

    op.create_index(
        "uq_fbs_order_markings_marking_code_id",
        "fbs_order_markings",
        ["marking_code_id"],
        unique=True,
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
