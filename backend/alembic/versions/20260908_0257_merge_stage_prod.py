"""WMS-351 WMS-058: join independent production and staging migrations.

The merge changes no tables. Downgrading this revision leaves both parent
revisions applied; each parent still owns only its original column changes.
"""

revision = "20260908_0257"
down_revision = ("20260908_0255", "20260908_0256")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
