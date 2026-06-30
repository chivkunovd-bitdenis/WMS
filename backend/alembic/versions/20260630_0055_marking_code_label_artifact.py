"""marking_code label_artifact_pdf — seller PDF page per CIS from PDF import."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260630_0055"
down_revision = "20260629_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_codes",
            sa.Column("label_artifact_pdf", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marking_codes", "label_artifact_pdf")
