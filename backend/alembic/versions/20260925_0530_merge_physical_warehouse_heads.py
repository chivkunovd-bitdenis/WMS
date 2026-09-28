"""Merge the WMS-516 and WMS-526 migration lines.

Revision ID: 20260925_0530
Revises: 20260923_0516, 20260924_0526

WMS-516 (physical warehouse guard) branched off 20260921_0490 while the
etalon integration line moved on through 20260924_0526. Both are folded into
the WMS-530 "single stock" package. This no-op revision rejoins both paths.
"""

from __future__ import annotations

revision = "20260925_0530"
down_revision = ("20260923_0516", "20260924_0526")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
