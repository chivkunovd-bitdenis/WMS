"""Merge the WMS-469 and WMS-525 migration lines.

Revision ID: 20260924_0526
Revises: 20260920_0307, 20260924_0525

Production received WMS-525 directly after 20260921_0490 as a narrow hotfix.
The integration branch also contains the unreleased WMS-469 migration line.
This no-op revision rejoins both paths without pulling WMS-469 into the hotfix.
"""

from __future__ import annotations

revision = "20260924_0526"
down_revision = ("20260920_0307", "20260924_0525")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
