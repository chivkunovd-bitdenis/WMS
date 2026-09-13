"""WMS-443: real employee names without changing account identity."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0443"
down_revision = "20260911_0304"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("job_title", sa.String(255), nullable=True))
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)


def downgrade() -> None:
    # Refuse rollback before losing accounts created without an email address.
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM users WHERE email IS NULL")):
        raise RuntimeError("WMS-443 rollback requires resolving email-free accounts")
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
    op.drop_column("users", "job_title")
    op.drop_column("users", "full_name")
