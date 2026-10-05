"""WMS-658: retain whether an imported code requires its original PDF label.

Revision ID: 20261005_0658
Revises: 20261001_2301
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261005_0658"
down_revision = "20261001_2301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_codes",
        sa.Column(
            "label_artifact_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Before this migration only PDF imports stored a label artifact. Preserve
    # that provenance so a later damaged artifact cannot be replaced with a
    # newly generated label, while CSV/TXT codes remain printable from payload.
    op.execute(
        """
        UPDATE marking_codes
        SET label_artifact_required = true
        WHERE import_batch_id IS NOT NULL AND label_artifact_pdf IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("marking_codes", "label_artifact_required")
