"""WMS-686: FBO shipment KIZ on the line, INB box identity, pass details.

Three optional columns and one data transfer:

* marking_codes.marketplace_unload_line_id — КИЗ lives on the shipment line;
* marketplace_unload_boxes.inbound_intake_box_id — whole box moved from intake;
* marketplace_unload_requests.pass_details — one pass (driver/car) per shipment.

Revision ID: 20261009_0686
Revises: 20261007_2303
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261009_0686"
down_revision = "20261007_2303"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_codes",
        sa.Column("marketplace_unload_line_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_marking_codes_marketplace_unload_line_id",
        "marking_codes",
        "marketplace_unload_lines",
        ["marketplace_unload_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_marking_codes_marketplace_unload_line_id"),
        "marking_codes",
        ["marketplace_unload_line_id"],
    )

    op.add_column(
        "marketplace_unload_boxes",
        sa.Column("inbound_intake_box_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_marketplace_unload_boxes_inbound_intake_box_id",
        "marketplace_unload_boxes",
        "inbound_intake_boxes",
        ["inbound_intake_box_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_marketplace_unload_boxes_inbound_intake_box_id"),
        "marketplace_unload_boxes",
        ["inbound_intake_box_id"],
    )

    op.add_column(
        "marketplace_unload_requests",
        sa.Column("pass_details", sa.JSON(), nullable=True),
    )

    # Existing FBO codes were tied to packaging-task lines. Link each of them
    # once to the shipment line of the same shipment and the same product.
    op.execute(
        """
        UPDATE marking_codes AS mc
        SET marketplace_unload_line_id = ul.id
        FROM packaging_task_lines AS ptl
        JOIN packaging_tasks AS pt ON pt.id = ptl.task_id
        JOIN marketplace_unload_lines AS ul
          ON ul.request_id = pt.marketplace_unload_request_id
         AND ul.product_id = ptl.product_id
        WHERE mc.packaging_task_line_id = ptl.id
          AND pt.marketplace_unload_request_id IS NOT NULL
          AND mc.marketplace_unload_line_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("marketplace_unload_requests", "pass_details")

    op.drop_index(
        op.f("ix_marketplace_unload_boxes_inbound_intake_box_id"),
        table_name="marketplace_unload_boxes",
    )
    op.drop_constraint(
        "fk_marketplace_unload_boxes_inbound_intake_box_id",
        "marketplace_unload_boxes",
        type_="foreignkey",
    )
    op.drop_column("marketplace_unload_boxes", "inbound_intake_box_id")

    op.drop_index(
        op.f("ix_marking_codes_marketplace_unload_line_id"),
        table_name="marking_codes",
    )
    op.drop_constraint(
        "fk_marking_codes_marketplace_unload_line_id",
        "marking_codes",
        type_="foreignkey",
    )
    op.drop_column("marking_codes", "marketplace_unload_line_id")
