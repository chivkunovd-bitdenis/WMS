"""WMS-658: distinguish complete per-code label provenance from legacy imports.

Revision ID: 20261005_0658b
Revises: 20261005_0658
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261005_0658b"
down_revision = "20261005_0658"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "marking_code_imports",
        sa.Column(
            "label_artifact_provenance_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # Existing imports predate the per-code label_artifact_required contract.
    # New imports retain the true server default and persist exact row-level
    # provenance; legacy imports use conservative source-artifact recovery.
    op.execute(
        """
        UPDATE marking_code_imports
        SET label_artifact_provenance_complete = false
        """
    )


def downgrade() -> None:
    op.drop_column("marking_code_imports", "label_artifact_provenance_complete")
