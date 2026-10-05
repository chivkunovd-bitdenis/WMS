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
    # provenance from the import name as well as the artifact itself: a
    # damaged/missing legacy artifact must not silently turn a PDF code into a
    # CSV/TXT code that can be regenerated from payload. A mixed legacy batch
    # cannot be classified per row in SQL; exact provenance for those rows is
    # recovered from MarkingCodeImportFile at print time. New mixed imports
    # store the exact per-code flag directly.
    op.execute(
        """
        UPDATE marking_codes
        SET label_artifact_required = true
        WHERE import_batch_id IS NOT NULL
          AND (
              label_artifact_pdf IS NOT NULL
              OR EXISTS (
                  SELECT 1
                  FROM marking_code_imports
                  WHERE marking_code_imports.id = marking_codes.import_batch_id
                    AND lower(marking_code_imports.filename) LIKE '%.pdf%'
                    AND lower(marking_code_imports.filename) NOT LIKE '%.csv%'
                    AND lower(marking_code_imports.filename) NOT LIKE '%.txt%'
                    AND lower(marking_code_imports.filename) NOT LIKE '%.tsv%'
              )
          )
        """
    )


def downgrade() -> None:
    op.drop_column("marking_codes", "label_artifact_required")
