"""WMS-488: merge shop grants with the production WMS-483 migration.

Both parent revisions remain unchanged. Upgrading from production 20260920_0255
runs only the missing shop-grant conversion, then joins the revision graph.
"""

revision = "20260921_0489"
down_revision = ("20260920_0255", "20260921_0488")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
