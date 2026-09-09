"""WMS-174: is_damaged flag on inbound boxes.

The flag is a simple boolean marker so the operator can record «этот короб
пришёл битым» right at receiving without inventing a lifecycle: it does not
block stages, does not gate movements, and does not participate in any
counter. Existing rows default to False.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260910_0100"
down_revision = "20260908_0257"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_boxes",
        sa.Column(
            "is_damaged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Server default is only there for the existing rows; the ORM writes an
    # explicit False on inserts, so we can drop the DB-side default to keep
    # the schema honest about who owns the value.
    op.alter_column("inbound_intake_boxes", "is_damaged", server_default=None)


def downgrade() -> None:
    op.drop_column("inbound_intake_boxes", "is_damaged")
